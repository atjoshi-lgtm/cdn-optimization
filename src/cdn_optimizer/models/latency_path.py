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
        parent_tat_pdf: ProbabilityDensityFunction,
    ) -> None:
        """
        Initialize the latency model with the four fundamental physical distributions.
        
        Args:
            edge_rtt_pdf: Network latency from Client to Edge.
            edge_tat_hit_pdf: Processing time at the Edge on a cache hit.
            midgress_rtt_pdf: Network latency from Edge to Parent on a cache miss.
            parent_tat_pdf: Processing time at the Parent on a cache miss.
        """
        # Validate that no empty PDFs were passed
        if any(pdf.probability_series.empty for pdf in [
            edge_rtt_pdf, edge_tat_hit_pdf, midgress_rtt_pdf, parent_tat_pdf
        ]):
            raise ValueError(
                "Cannot initialize PairwiseLatencyModel with empty probability distributions."
            )

        self.edge_rtt = edge_rtt_pdf
        self.edge_tat = edge_tat_hit_pdf
        self.midgress_rtt = midgress_rtt_pdf
        self.parent_tat = parent_tat_pdf
        self._conn = Convolution()

    def get_ttfb_pdf(self, hitrate_percentage: float) -> ProbabilityDensityFunction:
        """
        Calculate the expected TTFB distribution given a specific cache hit rate.
        
        The TTFB is a finite mixture model of two distinct paths:
        1. Pure Hit Path: Edge RTT + Edge TAT
        2. Pure Miss Path: Edge RTT + Midgress RTT + Parent TAT
        
        Args:
            hitrate_percentage: The cache hit rate (0.0 to 100.0).
            
        Returns:
            A new ProbabilityDensityFunction representing the combined TTFB.
        """
        if not 0.0 <= hitrate_percentage <= 100.0:
            raise ValueError("Hit rate must be a percentage between 0 and 100.")

        hit_fraction = hitrate_percentage / 100.0
        miss_fraction = 1.0 - hit_fraction

        # 1. Pure Hit Path: Client -> Edge -> Client
        hit_path_pdf = self._conn.convolve(self.edge_rtt, self.edge_tat)

        # 2. Pure Miss Path: Client -> Edge -> Parent -> Edge -> Client
        # First convolve the network legs, then add the parent processing time
        network_leg_pdf = self._conn.convolve(self.edge_rtt, self.midgress_rtt)
        miss_path_pdf = self._conn.convolve(network_leg_pdf, self.parent_tat)

        # 3. Mix the distributions based on the cache hit/miss probabilities
        return weighted_pdf_sum(
            pdfs=[hit_path_pdf, miss_path_pdf],
            weights=[hit_fraction, miss_fraction]
        )