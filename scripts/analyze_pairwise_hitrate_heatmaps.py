"""
analyze_pairwise_hitrate_heatmaps.py

Analyzes Client -> Edge -> Parent routes by sweeping explicit edge and parent
cache hit rates on a 2D grid and plotting p50/p95 TTFB heatmaps.

This script bypasses footprint descriptors and uses PairwiseLatencyModel directly.
"""

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt

from cdn_optimizer.core.config_loader import load_config
from cdn_optimizer.core.exceptions import MissingDataError
from cdn_optimizer.data_access.csv_parser import load_metro_maps
from cdn_optimizer.data_access.sqlite_client import SQLiteClient
from cdn_optimizer.models.latency_path import PairwiseLatencyModel
from cdn_optimizer.topology.network_map import MetroResolver

EDGE_HITRATE_STEP = 5
PARENT_HITRATE_STEP = 5
OUTPUT_DIR = Path("latency_heatmaps_pairwise_hitrate_5pct")


def _slug(value: str) -> str:
    return value.replace(" ", "_")


def _parse_edge_key(edge_key: str) -> tuple[str, str]:
    edge_name, edge_code_with_paren = edge_key.rsplit("(", 1)
    return edge_name.strip(), edge_code_with_paren.rstrip(")").strip()


def _write_matrix_csv(
    output_file: Path,
    edge_hitrates: list[int],
    parent_hitrates: list[int],
    matrix: list[list[float]],
) -> None:
    with output_file.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["parent_hitrate_percent", *[f"edge_{value}" for value in edge_hitrates]])
        for parent_hitrate, row in zip(parent_hitrates, matrix, strict=True):
            writer.writerow([parent_hitrate, *row])


def _plot_heatmaps(
    output_file: Path,
    client_metro_name: str,
    edge_metro_name: str,
    parent_metro_name: str,
    edge_hitrates: list[int],
    parent_hitrates: list[int],
    p50_matrix: list[list[float]],
    p95_matrix: list[list[float]],
) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    extent = [
        float(min(edge_hitrates)),
        float(max(edge_hitrates)),
        float(min(parent_hitrates)),
        float(max(parent_hitrates)),
    ]

    p50_img = ax1.imshow(
        p50_matrix,
        origin="lower",
        aspect="auto",
        cmap="viridis",
        extent=extent,
    )
    ax1.set_title(f"P50 TTFB: {client_metro_name} -> {edge_metro_name} -> {parent_metro_name}")
    ax1.set_xlabel("Edge Cache Hit Rate (%)")
    ax1.set_ylabel("Parent Cache Hit Rate (%)")
    ax1.set_xticks(edge_hitrates)
    ax1.set_yticks(parent_hitrates)
    fig.colorbar(p50_img, ax=ax1, label="Latency (ms)")

    p95_img = ax2.imshow(
        p95_matrix,
        origin="lower",
        aspect="auto",
        cmap="viridis",
        extent=extent,
    )
    ax2.set_title(f"P95 TTFB: {client_metro_name} -> {edge_metro_name} -> {parent_metro_name}")
    ax2.set_xlabel("Edge Cache Hit Rate (%)")
    ax2.set_ylabel("Parent Cache Hit Rate (%)")
    ax2.set_xticks(edge_hitrates)
    ax2.set_yticks(parent_hitrates)
    fig.colorbar(p95_img, ax=ax2, label="Latency (ms)")

    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    plt.close(fig)


def analyze_pairwise_path_hitrate_heatmaps(
    client_metro_name: str,
    edge_metro_name: str,
    parent_metro_name: str,
    resolver: MetroResolver,
    db_client: SQLiteClient,
    output_dir: Path,
) -> bool:
    print(
        f"Initializing Heatmap Analysis: {client_metro_name} -> {edge_metro_name} -> {parent_metro_name}"
    )

    client_id = resolver.get_id(client_metro_name)

    edge_rtt_pdf = db_client.get_edge_rtt_pdf(edge_metro_name, client_id)
    edge_tat_pdf = db_client.get_edge_tat_pdf(edge_metro_name, cache_hit_type=1)
    midgress_rtt_pdf = db_client.get_midgress_rtt_pdf(parent_metro_name, edge_metro_name)
    parent_tat_hit_pdf = db_client.get_parent_tat_pdf(parent_metro_name, cache_hit_type=1)
    parent_tat_miss_pdf = db_client.get_parent_tat_pdf(parent_metro_name, cache_hit_type=0)

    latency_model = PairwiseLatencyModel(
        edge_rtt_pdf=edge_rtt_pdf,
        edge_tat_hit_pdf=edge_tat_pdf,
        midgress_rtt_pdf=midgress_rtt_pdf,
        parent_tat_hit_pdf=parent_tat_hit_pdf,
        parent_tat_miss_pdf=parent_tat_miss_pdf,
    )

    edge_hitrates = list(range(0, 101, EDGE_HITRATE_STEP))
    parent_hitrates = list(range(0, 101, PARENT_HITRATE_STEP))

    p50_matrix: list[list[float]] = []
    p95_matrix: list[list[float]] = []

    for parent_hitrate in parent_hitrates:
        p50_row: list[float] = []
        p95_row: list[float] = []

        for edge_hitrate in edge_hitrates:
            ttfb_pdf = latency_model.get_ttfb_pdf(
                edge_hitrate_percentage=float(edge_hitrate),
                parent_hitrate_percentage=float(parent_hitrate),
            )
            micro_pdf = ttfb_pdf.to_microsecond_pdf(step_us=10)

            if micro_pdf.total_count() <= 0:
                raise ValueError(
                    "Cannot compute heatmap cell metrics for empty TTFB distribution."
                )

            p50_ms = micro_pdf.millisecond_at_percentile(50) / 1000.0
            p95_ms = micro_pdf.millisecond_at_percentile(95) / 1000.0

            if p95_ms < p50_ms:
                raise ValueError(
                    "Invalid percentile ordering encountered (p95 < p50)."
                )

            p50_row.append(p50_ms)
            p95_row.append(p95_ms)

        p50_matrix.append(p50_row)
        p95_matrix.append(p95_row)

    path_stub = (
        f"{_slug(client_metro_name)}_to_{_slug(edge_metro_name)}_via_{_slug(parent_metro_name)}"
    )

    p50_csv = output_dir / f"heatmap_p50_{path_stub}.csv"
    p95_csv = output_dir / f"heatmap_p95_{path_stub}.csv"
    _write_matrix_csv(p50_csv, edge_hitrates, parent_hitrates, p50_matrix)
    _write_matrix_csv(p95_csv, edge_hitrates, parent_hitrates, p95_matrix)

    plot_file = output_dir / f"heatmap_{path_stub}.png"
    _plot_heatmaps(
        output_file=plot_file,
        client_metro_name=client_metro_name,
        edge_metro_name=edge_metro_name,
        parent_metro_name=parent_metro_name,
        edge_hitrates=edge_hitrates,
        parent_hitrates=parent_hitrates,
        p50_matrix=p50_matrix,
        p95_matrix=p95_matrix,
    )

    print(f"Saved p50 matrix CSV: {p50_csv}")
    print(f"Saved p95 matrix CSV: {p95_csv}")
    print(f"Saved heatmap plot: {plot_file}")
    return True


def main() -> None:
    config = load_config()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    name_to_id, id_to_name, name_to_airport = load_metro_maps(config.metro_areas_csv)
    resolver = MetroResolver(name_to_id, id_to_name)
    db_client = SQLiteClient(config.db_path)

    analyzable_paths_file = Path("data/analyzable_paths.json")
    with analyzable_paths_file.open("r", encoding="utf-8") as path_file:
        paths_by_edge = json.load(path_file)

    total_paths = 0
    successful_paths = 0

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
                if analyze_pairwise_path_hitrate_heatmaps(
                    client_metro_name=client_metro_name,
                    edge_metro_name=edge_metro_name,
                    parent_metro_name=parent_metro_name,
                    resolver=resolver,
                    db_client=db_client,
                    output_dir=OUTPUT_DIR,
                ):
                    successful_paths += 1
            except (MissingDataError, ValueError, FileNotFoundError) as exc:
                print(
                    f"Skipping path {client_metro_name} -> {edge_metro_name} -> {parent_metro_name}: {exc}"
                )

    print(f"Completed pairwise heatmap analysis for {successful_paths}/{total_paths} paths.")


if __name__ == "__main__":
    main()
