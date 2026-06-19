"""
analyze_pairwise_paths.py

Analyzes the physical latency path for a specific Client -> Edge -> Parent route.
Evaluates how the cache disk size at the Edge impacts the TTFB p50 and p95.

This script acts as the "glue" layer, connecting data access, topology, and math models,
and is the ONLY place where visualization (matplotlib) and CSV writing occur.
"""

import csv
from pathlib import Path
import matplotlib.pyplot as plt

from cdn_optimizer.core.config_loader import load_config
from cdn_optimizer.data_access.csv_parser import load_metro_maps
from cdn_optimizer.topology.network_map import MetroResolver
from cdn_optimizer.data_access.sqlite_client import SQLiteClient
from cdn_optimizer.data_access.fds_loader import load_footprint_descriptor
from cdn_optimizer.models.latency_path import PairwiseLatencyModel

# Constants for the sweep
TB_IN_MB = 1024 * 1024
DISK_STEP_TB = 100.0


def main():
    # 1. Configuration & Setup
    config = load_config()
    output_dir = Path("latency_vs_cache_size_pairwise")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define the isolated path to analyze
    CLIENT_METRO_NAME = "Dallas"  # This is the client metro we want to analyze (e.g., "Seattle")
    EDGE_METRO_CODE = "DFW" # This is the edge metro we want to analyze (e.g., "SEA")
    EDGE_METRO_NAME = "Dallas" # This is the edge metro we want to analyze (e.g., "Dallas")
    PARENT_METRO_NAME = "Dallas" # This is the parent metro we want to analyze (e.g., "Dallas")

    print(f"Initializing Pairwise Analysis: {CLIENT_METRO_NAME} -> {EDGE_METRO_NAME} -> {PARENT_METRO_NAME}")

    # 2. Topology & Data Access Clients
    name_to_id, id_to_name = load_metro_maps(config.metro_areas_csv)
    resolver = MetroResolver(name_to_id, id_to_name)
    db_client = SQLiteClient(config.db_path)

    # 3. Load the Footprint Descriptor (Cache Efficiency Curve)
    fds_path = config.fds_dir / f"{EDGE_METRO_CODE.lower()}.txt"
    descriptor = load_footprint_descriptor(fds_path)

    # 4. Fetch the Physical Latency PDFs from the Database
    client_id = resolver.get_id(CLIENT_METRO_NAME)
    
    edge_rtt_pdf = db_client.get_edge_rtt_pdf(EDGE_METRO_NAME, client_id)
    edge_tat_pdf = db_client.get_edge_tat_pdf(EDGE_METRO_NAME, cache_hit_type=1)
    midgress_rtt_pdf = db_client.get_midgress_rtt_pdf(PARENT_METRO_NAME, EDGE_METRO_NAME)
    parent_tat_pdf = db_client.get_parent_tat_pdf(PARENT_METRO_NAME)

    # 5. Initialize the Latency Physics Model
    latency_model = PairwiseLatencyModel(
        edge_rtt_pdf=edge_rtt_pdf,
        edge_tat_hit_pdf=edge_tat_pdf,
        midgress_rtt_pdf=midgress_rtt_pdf,
        parent_tat_pdf=parent_tat_pdf
    )

    # 6. Computation Sweep
    min_disk_mb = min(p.cache_space for p in descriptor._points_sorted_by_cache)
    max_disk_mb = max(p.cache_space for p in descriptor._points_sorted_by_cache)
    
    results = []
    current_disk_mb = min_disk_mb
    step_mb = DISK_STEP_TB * TB_IN_MB

    print(f"Sweeping disk sizes from {min_disk_mb / TB_IN_MB:.1f} TB to {max_disk_mb / TB_IN_MB:.1f} TB...")

    while current_disk_mb <= max_disk_mb:
        # Get hitrate for this specific disk size
        hitrate_percent = descriptor.hitrate_for_cache(current_disk_mb)
        
        # Get TTFB PDF mixture for this hitrate
        ttfb_pdf = latency_model.get_ttfb_pdf(hitrate_percentage=hitrate_percent)
        
        # Extract human-readable metrics (converted to milliseconds)
        micro_pdf = ttfb_pdf.to_microsecond_pdf(step_us=10)
        
        p50_ms = micro_pdf.millisecond_at_percentile(50) / 1000.0 if micro_pdf.total_count() > 0 else 0.0
        p95_ms = micro_pdf.millisecond_at_percentile(95) / 1000.0 if micro_pdf.total_count() > 0 else 0.0

        results.append({
            "disk_tb": current_disk_mb / TB_IN_MB,
            "hitrate_percent": hitrate_percent,
            "p50_ms": p50_ms,
            "p95_ms": p95_ms
        })
        
        current_disk_mb += step_mb

    # 7. Output: Write CSV
    csv_filename = output_dir / f"pairwise_{CLIENT_METRO_NAME}_to_{EDGE_METRO_NAME}.csv"
    with open(csv_filename, mode='w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["disk_tb", "hitrate_percent", "p50_ms", "p95_ms"])
        writer.writeheader()
        writer.writerows(results)
    print(f"Data saved to {csv_filename}")

    # 8. Output: Visualization
    disk_tb_vals = [r["disk_tb"] for r in results]
    hitrate_vals = [r["hitrate_percent"] for r in results]
    p50_vals = [r["p50_ms"] for r in results]
    p95_vals = [r["p95_ms"] for r in results]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Plot 1: Disk vs Hitrate
    ax1.plot(disk_tb_vals, hitrate_vals, color='blue', marker='.', linestyle='-')
    ax1.set_title(f"Cache Efficiency: {EDGE_METRO_NAME}")
    ax1.set_xlabel("Provisioned Disk (TB)")
    ax1.set_ylabel("Hitrate (%)")
    ax1.grid(True, linestyle="--", alpha=0.6)

    # Plot 2: Disk vs Latency
    ax2.plot(disk_tb_vals, p50_vals, color='green', marker='.', linestyle='-', label='p50 TTFB')
    ax2.plot(disk_tb_vals, p95_vals, color='red', marker='.', linestyle='-', label='p95 TTFB')
    ax2.set_title(f"Client Latency: {CLIENT_METRO_NAME} -> {EDGE_METRO_NAME}")
    ax2.set_xlabel("Provisioned Disk (TB)")
    ax2.set_ylabel("Latency (ms)")
    ax2.legend()
    ax2.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    plot_filename = output_dir / f"pairwise_plot_{CLIENT_METRO_NAME}_to_{EDGE_METRO_NAME}.png"
    plt.savefig(plot_filename, dpi=150)
    print(f"Plot saved to {plot_filename}")


if __name__ == "__main__":
    main()