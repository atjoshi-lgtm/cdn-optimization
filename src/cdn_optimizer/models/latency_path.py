"""
latency_path.py

Models the Time-To-First-Byte (TTFB) probability distribution for a specific 
pairwise routing path: Client -> Edge -> Parent.
Strictly decoupled from data fetching and topology maps.
"""

from cdn_optimizer.models.probability import (
    ProbabilityDensityFunction,
    Convolution,
    weighted_pdf_sum,
)

class PairwiseLatencyModel:
    """
    Computes the TTFB distribution for a specific client-to-serving-to-parent path.
    """

    def __init__(
        self,
        edge_rtt_pdf: ProbabilityDensityFunction,
        edge_tat_hit_pdf: ProbabilityDensityFunction,
        midgress_rtt_pdf: ProbabilityDensityFunction,
        parent_tat_hit_pdf: ProbabilityDensityFunction,
        parent_tat_miss_pdf: ProbabilityDensityFunction,
    ) -> None:
        """
        Initialize the latency model with the five fundamental physical distributions.
        
        Args:
            edge_rtt_pdf: Network latency from Client to Edge.
            edge_tat_hit_pdf: Processing time at the Edge on a cache hit.
            midgress_rtt_pdf: Network latency from Edge to Parent on a cache miss.
            parent_tat_hit_pdf: Processing time at the Parent on a parent cache hit.
            parent_tat_miss_pdf: Processing time at the Parent on a parent cache miss.
        """
        # Validate that no empty PDFs were passed
        if any(pdf.probability_series.empty for pdf in [
            edge_rtt_pdf,
            edge_tat_hit_pdf,
            midgress_rtt_pdf,
            parent_tat_hit_pdf,
            parent_tat_miss_pdf,
        ]):
            raise ValueError(
                "Cannot initialize PairwiseLatencyModel with empty probability distributions."
            )

        self.edge_rtt = edge_rtt_pdf
        self.edge_tat = edge_tat_hit_pdf
        self.midgress_rtt = midgress_rtt_pdf
        self.parent_tat_hit = parent_tat_hit_pdf
        self.parent_tat_miss = parent_tat_miss_pdf
        self._conn = Convolution()

    def get_ttfb_pdf(
        self,
        edge_hitrate_percentage: float,
        parent_hitrate_percentage: float,
    ) -> ProbabilityDensityFunction:
        """
        Calculate the expected TTFB distribution given edge and parent hit rates.
        
        The TTFB is a finite mixture model of three distinct paths:
        1. Edge Hit Path: Edge RTT + Edge Hit TAT
        2. Parent Hit Path: Edge RTT + Midgress RTT + Parent Hit TAT
        3. Parent Miss Path: Edge RTT + Midgress RTT + Parent Miss TAT
        
        Args:
            edge_hitrate_percentage: The edge hit rate (0.0 to 100.0).
            parent_hitrate_percentage: The parent hit rate conditioned on edge misses (0.0 to 100.0).
            
        Returns:
            A new ProbabilityDensityFunction representing the combined TTFB.
        """
        if not 0.0 <= edge_hitrate_percentage <= 100.0:
            raise ValueError("Edge hit rate must be a percentage between 0 and 100.")
        if not 0.0 <= parent_hitrate_percentage <= 100.0:
            raise ValueError("Parent hit rate must be a percentage between 0 and 100.")

        edge_hit_fraction = edge_hitrate_percentage / 100.0
        edge_miss_fraction = 1.0 - edge_hit_fraction
        parent_hit_fraction = parent_hitrate_percentage / 100.0
        parent_miss_fraction = 1.0 - parent_hit_fraction

        weight_edge_hit = edge_hit_fraction
        weight_parent_hit = edge_miss_fraction * parent_hit_fraction
        weight_parent_miss = edge_miss_fraction * parent_miss_fraction

        total_weight = weight_edge_hit + weight_parent_hit + weight_parent_miss
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError("3-path mixture weights must sum to 1.0.")

        # 1. Edge Hit Path: Client -> Edge -> Client
        edge_hit_path_pdf = self._conn.convolve(self.edge_rtt, self.edge_tat)

        # Build shared network leg once for parent paths.
        network_leg_pdf = self._conn.convolve(self.edge_rtt, self.midgress_rtt)

        # 2. Parent Hit Path: Client -> Edge -> Parent(hit) -> Edge -> Client
        parent_hit_path_pdf = self._conn.convolve(network_leg_pdf, self.parent_tat_hit)

        # 3. Parent Miss Path: Client -> Edge -> Parent(miss) -> Edge -> Client
        parent_miss_path_pdf = self._conn.convolve(network_leg_pdf, self.parent_tat_miss)

        # 4. Mix the three path distributions based on edge/parent hit probabilities.
        return weighted_pdf_sum(
            pdfs=[edge_hit_path_pdf, parent_hit_path_pdf, parent_miss_path_pdf],
            weights=[weight_edge_hit, weight_parent_hit, weight_parent_miss],
        )
