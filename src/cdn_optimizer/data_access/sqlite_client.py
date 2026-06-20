"""
sqlite_client.py

Handles all SQLite database connections and queries.
Transforms raw database rows into ProbabilityDensityFunction models.
"""

import sqlite3
import re
from pathlib import Path
import pandas as pd

from cdn_optimizer.models.probability import ProbabilityDensityFunction, PdfBucket
from cdn_optimizer.core.exceptions import MissingDataError


class SQLiteClient:
    """Client for fetching latency metrics from the performance database."""

    def __init__(self, db_path: str | Path) -> None:
        """
        Initialize the SQLite client.
        
        Args:
            db_path: Path to the SQLite database file (e.g., perf_data.db).
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at {self.db_path}")

        # Default dates used in the legacy analytical queries
        self.default_dates = ('2026-02-07', '2026-02-08', '2026-02-09')

        # Regex to extract latency bounds from DB columns (e.g., 'rtt_0_5_ms' -> lower: 0, upper: 5)
        self.bucket_pattern = re.compile(r"(?:[A-Za-z0-9]+_)?(?P<lower>\d+)_(?P<upper>\d+)_ms")

    def _fetch_pdf(self, query: str, params: tuple, context: str) -> ProbabilityDensityFunction:
        """
        Helper method to execute a query, parse latency buckets, and return a PDF.
        """
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(query, conn, params=params)

        if df.empty:
            raise MissingDataError(f"No data found for {context}.")

        buckets = []
        for column in df.columns:
            match = self.bucket_pattern.fullmatch(column)
            if not match:
                continue
            
            lower_ms = int(match.group("lower"))
            upper_ms = int(match.group("upper"))
            count = float(df[column].sum(skipna=True))
            
            if count > 0 and upper_ms > lower_ms:
                buckets.append(PdfBucket(lower_ms=lower_ms, upper_ms=upper_ms, count=count))

        # Create the mathematical PDF
        pdf = ProbabilityDensityFunction(buckets)
        
        # Normalize the PDF so the total mass equals 1.0 (retaining legacy behavior)
        total = float(pdf.probability_series.sum())
        if total > 0:
            pdf._probability_series /= total # type: ignore
            
        return pdf

    def get_edge_rtt_pdf(self, metro_name: str, client_metro_id: int) -> ProbabilityDensityFunction:
        """Fetch the network RTT distribution from a client metro to an edge metro."""
        query = f"""
            SELECT * FROM netopt_perf_edge_rtt_ansabni
            WHERE region_metro = ? AND client_metro = ?
            AND pdate IN {self.default_dates}
        """
        context = f"Edge RTT (Client ID: {client_metro_id} -> Edge: {metro_name})"
        return self._fetch_pdf(query, (metro_name, str(client_metro_id)), context)

    def get_edge_tat_pdf(self, metro_name: str, cache_hit_type: int = 1) -> ProbabilityDensityFunction:
        """Fetch the processing TAT distribution at the edge metro (default: cache hits)."""
        query = f"""
            SELECT * FROM netopt_perf_edge_ecor_tat_ansabni
            WHERE edge_metro = ? AND cache_hit_type = ?
            AND pdate IN {self.default_dates}
        """
        context = f"Edge TAT (Edge: {metro_name}, Hit Type: {cache_hit_type})"
        return self._fetch_pdf(query, (metro_name, cache_hit_type), context)

    def get_midgress_rtt_pdf(self, parent_metro: str, child_metro: str) -> ProbabilityDensityFunction:
        """Fetch the network RTT distribution from an edge metro to its parent MCH."""
        query = f"""
            SELECT * FROM netopt_perf_midgress_rtt_ansabni
            WHERE parent_metro = ? AND child_metro = ?
            AND pdate IN {self.default_dates}
        """
        context = f"Midgress RTT (Edge: {child_metro} -> Parent: {parent_metro})"
        return self._fetch_pdf(query, (parent_metro, child_metro), context)

    def get_parent_tat_pdf(self, metro_name: str) -> ProbabilityDensityFunction:
        """
        Fetch the processing TAT distribution at the parent MCH.
        Excludes cache_hit_type 2 (ICP cache hits) as per legacy logic.
        """
        query = f"""
            SELECT * FROM netopt_perf_midgress_ecor_tat_ansabni
            WHERE edge_metro = ? AND cache_hit_type != 2
            AND pdate IN {self.default_dates}
        """
        context = f"Parent TAT (Parent assigned to Edge: {metro_name})"
        return self._fetch_pdf(query, (metro_name,), context)
    
    def get_active_parent_for_edge(self, edge_metro_name: str) -> str:
        """
        Dynamically determine the assigned parent (MCH) metro for an edge metro
        by finding which parent handled the highest volume of midgress requests.
        
        Args:
            edge_metro_name: The name of the edge/child metro (e.g., 'Houston').
            
        Returns:
            The name of the parent metro (e.g., 'Dallas').
            
        Raises:
            MissingDataError: If no midgress data exists for this edge metro.
        """
        query = f"""
            SELECT parent_metro, SUM(total_requests) as total_vol
            FROM netopt_perf_midgress_rtt_ansabni
            WHERE child_metro = ?
            AND pdate IN {self.default_dates}
            GROUP BY parent_metro
            ORDER BY total_vol DESC
            LIMIT 1
        """
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (edge_metro_name,))
            row = cursor.fetchone()
            
        if not row:
            raise MissingDataError(f"Could not determine active parent for edge: {edge_metro_name}")
            
        return row[0]