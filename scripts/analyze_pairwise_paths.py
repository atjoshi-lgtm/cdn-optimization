"""
analyze_pairwise_paths.py

Analyzes the physical latency path for Client -> Edge -> Parent routes.
Evaluates how the cache disk size at the Edge impacts the TTFB p50 and p95.

This script acts as the "glue" layer, connecting data access, topology, and math models,
and is the ONLY place where visualization (matplotlib) and CSV writing occur.
"""

import csv
import json
from pathlib import Path
import matplotlib.pyplot as plt

from cdn_optimizer.core.config_loader import load_config
from cdn_optimizer.data_access.csv_parser import load_metro_maps
from cdn_optimizer.core.exceptions import MissingDataError
from cdn_optimizer.topology.network_map import MetroResolver
from cdn_optimizer.data_access.sqlite_client import SQLiteClient
from cdn_optimizer.data_access.fds_loader import load_footprint_descriptor
from cdn_optimizer.models.latency_path import PairwiseLatencyModel

# Constants for the sweep
TB_IN_MB = 1024 * 1024
DISK_STEP_TB = 100.0
PARENT_DISK_TB = 1000.0
EDGE_TRAFFIC_SHARE = 0.10


def _slug(value: str) -> str:
    return value.replace(" ", "_")


def analyze_pairwise_path(
    client_metro_name: str,
    edge_metro_code: str,
    edge_metro_name: str,
    parent_metro_name: str,
    resolver: MetroResolver,
    db_client: SQLiteClient,
    config,
    output_dir: Path,
) -> bool:
    print(f"Initializing Pairwise Analysis: {client_metro_name} -> {edge_metro_name} -> {parent_metro_name}")

    # 1. Load the Footprint Descriptor (Cache Efficiency Curve)
    fds_path = config.fds_dir / f"{edge_metro_code.lower()}.txt"
    descriptor = load_footprint_descriptor(fds_path)

    # 2. Fetch the Physical Latency PDFs from the Database
    client_id = resolver.get_id(client_metro_name)

    edge_rtt_pdf = db_client.get_edge_rtt_pdf(edge_metro_name, client_id)
    edge_tat_pdf = db_client.get_edge_tat_pdf(edge_metro_name, cache_hit_type=1)
    midgress_rtt_pdf = db_client.get_midgress_rtt_pdf(parent_metro_name, edge_metro_name)
    parent_tat_hit_pdf = db_client.get_parent_tat_pdf(parent_metro_name, cache_hit_type=1)
    parent_tat_miss_pdf = db_client.get_parent_tat_pdf(parent_metro_name, cache_hit_type=0)

    # 3. Initialize the Latency Physics Model
    latency_model = PairwiseLatencyModel(
        edge_rtt_pdf=edge_rtt_pdf,
        edge_tat_hit_pdf=edge_tat_pdf,
        midgress_rtt_pdf=midgress_rtt_pdf,
        parent_tat_hit_pdf=parent_tat_hit_pdf,
        parent_tat_miss_pdf=parent_tat_miss_pdf,
    )

    # 4. Computation Sweep
    min_disk_mb = min(p.cache_space for p in descriptor._points_sorted_by_cache)
    max_disk_mb = max(p.cache_space for p in descriptor._points_sorted_by_cache)

    results = []
    current_disk_mb = min_disk_mb
    step_mb = DISK_STEP_TB * TB_IN_MB

    print(f"Sweeping disk sizes from {min_disk_mb / TB_IN_MB:.1f} TB to {max_disk_mb / TB_IN_MB:.1f} TB...")

    while current_disk_mb <= max_disk_mb:
        # Under perfect exclusion, edge and parent caches contribute distinct hit mass.
        edge_hitrate = descriptor.hitrate_for_cache(current_disk_mb)
        effective_parent_mb = (PARENT_DISK_TB * TB_IN_MB) * EDGE_TRAFFIC_SHARE
        global_hitrate = descriptor.hitrate_for_cache(current_disk_mb + effective_parent_mb)

        if edge_hitrate >= 100.0:
            parent_hitrate = 0.0
        else:
            parent_hitrate = ((global_hitrate - edge_hitrate) / (100.0 - edge_hitrate)) * 100.0
            parent_hitrate = max(0.0, min(100.0, parent_hitrate))
        
        # Get TTFB PDF mixture for edge and parent hit rates.
        ttfb_pdf = latency_model.get_ttfb_pdf(
            edge_hitrate_percentage=edge_hitrate,
            parent_hitrate_percentage=parent_hitrate,
        )
        
        # Extract human-readable metrics (converted to milliseconds)
        micro_pdf = ttfb_pdf.to_microsecond_pdf(step_us=10)
        
        p50_ms = micro_pdf.millisecond_at_percentile(50) / 1000.0 if micro_pdf.total_count() > 0 else 0.0
        p95_ms = micro_pdf.millisecond_at_percentile(95) / 1000.0 if micro_pdf.total_count() > 0 else 0.0

        results.append({
            "disk_tb": current_disk_mb / TB_IN_MB,
            "edge_hitrate_percent": edge_hitrate,
            "parent_hitrate_percent": parent_hitrate,
            "p50_ms": p50_ms,
            "p95_ms": p95_ms,
        })

        current_disk_mb += step_mb

    # 5. Output: Write CSV
    csv_filename = output_dir / (
        f"pairwise_{_slug(client_metro_name)}_to_{_slug(edge_metro_name)}_via_{_slug(parent_metro_name)}.csv"
    )
    with open(csv_filename, mode='w', newline='') as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["disk_tb", "edge_hitrate_percent", "parent_hitrate_percent", "p50_ms", "p95_ms"],
        )
        writer.writeheader()
        writer.writerows(results)
    print(f"Data saved to {csv_filename}")

    # 6. Output: Visualization
    disk_tb_vals = [r["disk_tb"] for r in results]
    edge_hitrate_vals = [r["edge_hitrate_percent"] for r in results]
    parent_hitrate_vals = [r["parent_hitrate_percent"] for r in results]
    p50_vals = [r["p50_ms"] for r in results]
    p95_vals = [r["p95_ms"] for r in results]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Plot 1: Disk vs Hitrate
    ax1.plot(disk_tb_vals, edge_hitrate_vals, color='blue', marker='.', linestyle='-', label='Edge Hitrate')
    ax1.plot(disk_tb_vals, parent_hitrate_vals, color='orange', marker='.', linestyle='-', label='Parent Hitrate')
    ax1.set_title(f"Cache Efficiency: {edge_metro_name}")
    ax1.set_xlabel("Provisioned Disk (TB)")
    ax1.set_ylabel("Hitrate (%)")
    ax1.legend()
    ax1.grid(True, linestyle="--", alpha=0.6)

    # Plot 2: Disk vs Latency
    ax2.plot(disk_tb_vals, p50_vals, color='green', marker='.', linestyle='-', label='p50 TTFB')
    ax2.plot(disk_tb_vals, p95_vals, color='red', marker='.', linestyle='-', label='p95 TTFB')
    ax2.set_title(f"Client Latency: {client_metro_name} -> {edge_metro_name}")
    ax2.set_xlabel("Provisioned Disk (TB)")
    ax2.set_ylabel("Latency (ms)")
    ax2.legend()
    ax2.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    plot_filename = output_dir / (
        f"pairwise_plot_{_slug(client_metro_name)}_to_{_slug(edge_metro_name)}_via_{_slug(parent_metro_name)}.png"
    )
    plt.savefig(plot_filename, dpi=150)
    plt.close(fig)
    print(f"Plot saved to {plot_filename}")
    return True


def _parse_edge_key(edge_key: str) -> tuple[str, str]:
    edge_name, edge_code_with_paren = edge_key.rsplit("(", 1)
    return edge_name.strip(), edge_code_with_paren.rstrip(")").strip()


def main():
    # 1. Configuration & Setup
    config = load_config()
    output_dir = Path(f"latency_vs_cache_size_pairwise_parent_{PARENT_DISK_TB:.0f}TB")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Topology & Data Access Clients
    name_to_id, id_to_name, name_to_airport = load_metro_maps(config.metro_areas_csv)
    resolver = MetroResolver(name_to_id, id_to_name)
    db_client = SQLiteClient(config.db_path)

    # 3. Load all analyzable Client -> Edge -> Parent routes
    analyzable_paths_file = Path("data/analyzable_paths.json")
    with analyzable_paths_file.open("r", encoding="utf-8") as f:
        paths_by_edge = json.load(f)

    total_paths = 0
    successful_paths = 0

    # 4. Iterate over all route combinations and analyze each one
    for edge_key, edge_data in paths_by_edge.items():
        edge_metro_name, edge_metro_code = _parse_edge_key(edge_key)
        parent_metro_name = edge_data.get("active_parent", "UNKNOWN")

        if parent_metro_name == "UNKNOWN":
            print(f"Skipping {edge_key}: parent metro is UNKNOWN")
            continue

        for client_info in edge_data.get("serves_clients", []):
            client_metro_name = client_info["client_name"]
            total_paths += 1

            try:
                if analyze_pairwise_path(
                    client_metro_name=client_metro_name,
                    edge_metro_code=edge_metro_code,
                    edge_metro_name=edge_metro_name,
                    parent_metro_name=parent_metro_name,
                    resolver=resolver,
                    db_client=db_client,
                    config=config,
                    output_dir=output_dir,
                ):
                    successful_paths += 1
            except (MissingDataError, ValueError, FileNotFoundError) as e:
                print(
                    f"Skipping path {client_metro_name} -> {edge_metro_name} -> {parent_metro_name}: {e}"
                )

    print(f"Completed pairwise analysis for {successful_paths}/{total_paths} paths.")


if __name__ == "__main__":
    main()