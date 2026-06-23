# CDN Optimization

CDN Optimization is a small Python project for analyzing CDN latency and cache allocation behavior. It separates pure mathematical models from data access and keeps all file I/O, plotting, and CSV generation in top-level scripts.

The codebase currently focuses on pairwise Client -> Edge -> Parent paths and supports two complementary analysis modes:
- cache-efficiency sweeps driven by footprint descriptors
- direct edge/parent hit-rate heatmaps that bypass footprint descriptors entirely

## Project Structure

```text
config/                     YAML configuration for database and data paths
data/                       Input datasets and generated analyzable path JSON
docs/                       Architecture and model documentation
scripts/                    Top-level analysis scripts and utilities
src/cdn_optimizer/          Installable Python package
tests/                      Automated tests
```

The most important package layers are:

- `src/cdn_optimizer/models/`: pure math and business logic
- `src/cdn_optimizer/data_access/`: SQLite and file-system access
- `src/cdn_optimizer/topology/`: metro-name and metro-ID mapping logic
- `scripts/`: orchestration, plotting, CSV export, and batch analysis

## Core Concepts

### Latency model

`PairwiseLatencyModel` computes TTFB for a single Client -> Edge -> Parent path using a 3-path mixture:

- edge hit: edge RTT + edge TAT
- parent hit: edge RTT + midgress RTT + parent hit TAT
- parent miss: edge RTT + midgress RTT + parent miss TAT

The model accepts explicit edge hit rate and parent hit rate inputs. The parent hit rate is conditional on edge misses, so the effective weights are:

- edge hit: $h_e$
- parent hit: $(1-h_e)h_p$
- parent miss: $(1-h_e)(1-h_p)$

### Data flow

The repository keeps the following separation of concerns:

- `data_access` loads PDFs, metro mappings, and traffic/topology data
- `models` only perform mathematical transformations
- `scripts` combine the data and models, then write CSVs and plots

## Configuration

Default settings live in [config/default_config.yaml](config/default_config.yaml).

Important keys:

- `bucket`: selects the data bucket name used in path templates
- `traffic_threshold_mbps`: minimum traffic volume for a path to be considered analyzable
- `data_paths.db_path`: SQLite database location
- `data_paths.metro_areas_csv`: metro mapping CSV
- `data_paths.fds_dir`: footprint descriptor directory
- `data_paths.served_from_csv`: traffic matrix CSV

The config loader expands these values into a typed configuration object used by the scripts.

## Installation

Requirements:

- Python 3.10 or newer
- `numpy`
- `pandas`
- `matplotlib`
- `pyyaml`

Install dependencies with your existing virtual environment:

```bash
/Users/atjoshi/cdn-optimization/venv/bin/python -m pip install -e .
```

If you need to create a new environment first, use any standard Python environment manager, then install the package in editable mode.

## Data Preparation

The analysis scripts expect the repository data files to exist in the locations defined by the config:

- `data/PERF/perf_data.db`
- `data/PERF/metro_areas_original.csv`
- `data/FDS_<bucket>/`
- `data/SERVEDFROM_DATA/served_from_<bucket>.csv`

The batch discovery flow produces [data/analyzable_paths.json](data/analyzable_paths.json), which is the source of truth for the pairwise analysis scripts.

## Scripts

### Discover analyzable paths

This script scans the database, traffic matrix, metro mappings, and footprint descriptor availability to generate the analyzable path inventory.

```bash
/Users/atjoshi/cdn-optimization/venv/bin/python scripts/discover_analyzable_paths.py
```

Output:

- [data/analyzable_paths.json](data/analyzable_paths.json)

### Pairwise disk-sweep analysis

This script analyzes each analyzable path by sweeping edge disk size and deriving edge/parent hit rates from footprint descriptors.

```bash
/Users/atjoshi/cdn-optimization/venv/bin/python scripts/analyze_pairwise_paths.py
```

Outputs:

- `latency_vs_cache_size_pairwise_parent_<parent_tb>TB/`
- per-path CSV files with disk size, hit rates, p50, and p95
- per-path plots showing cache efficiency and latency trends

### Pairwise hit-rate heatmaps

This script bypasses footprint descriptors and directly sweeps edge and parent hit rates for each path in [data/analyzable_paths.json](data/analyzable_paths.json).

```bash
/Users/atjoshi/cdn-optimization/venv/bin/python scripts/analyze_pairwise_hitrate_heatmaps.py
```

Default outputs:

- `latency_heatmaps_pairwise_hitrate_5pct/`
- `heatmap_<client>_to_<edge>_via_<parent>.png`
- `heatmap_p50_<client>_to_<edge>_via_<parent>.csv`
- `heatmap_p95_<client>_to_<edge>_via_<parent>.csv`

The default sweep uses a 5% grid step for both edge and parent hit rates, producing a 21 x 21 matrix per path.

## Output Conventions

CSV and plot filenames use slugged metro names, with spaces replaced by underscores.

For the heatmap workflow:

- rows correspond to parent hit rate
- columns correspond to edge hit rate
- latency values are reported in milliseconds

## Code Organization

### Models

Key model files:

- [src/cdn_optimizer/models/probability.py](src/cdn_optimizer/models/probability.py)
- [src/cdn_optimizer/models/latency_path.py](src/cdn_optimizer/models/latency_path.py)
- [src/cdn_optimizer/models/footprint.py](src/cdn_optimizer/models/footprint.py)

These modules are intentionally free of file I/O and plotting.

### Data access

Key access files:

- [src/cdn_optimizer/data_access/sqlite_client.py](src/cdn_optimizer/data_access/sqlite_client.py)
- [src/cdn_optimizer/data_access/csv_parser.py](src/cdn_optimizer/data_access/csv_parser.py)
- [src/cdn_optimizer/data_access/fds_loader.py](src/cdn_optimizer/data_access/fds_loader.py)

These modules load data and return pure objects for the model layer.

### Topology

Key topology files:

- [src/cdn_optimizer/topology/network_map.py](src/cdn_optimizer/topology/network_map.py)

This layer handles metro-name resolution and related mapping logic.

## Development Notes

- Models should not perform file or database operations.
- Scripts are allowed to plot and write files.
- Missing data should fail fast with explicit errors.
- Pairwise latency analysis now has two separate flows:
	- footprint-derived disk sweeps in [scripts/analyze_pairwise_paths.py](scripts/analyze_pairwise_paths.py)
	- direct hit-rate sweeps in [scripts/analyze_pairwise_hitrate_heatmaps.py](scripts/analyze_pairwise_hitrate_heatmaps.py)

## Documentation

Additional architecture details are in [docs/](docs), especially:

- [docs/models_latency_path.md](docs/models_latency_path.md)
- [docs/models_probability.md](docs/models_probability.md)
- [docs/models_footprint.md](docs/models_footprint.md)
- [docs/data_access_sqlite.md](docs/data_access_sqlite.md)
- [docs/data_access_fds_loader.md](docs/data_access_fds_loader.md)
- [docs/core_and_topology.md](docs/core_and_topology.md)
- [docs/refactoring_report.md](docs/refactoring_report.md)

## Reproducibility

The repository is designed so that rerunning the discovery and analysis scripts against the same inputs should reproduce the same CSV and plot outputs, aside from any changes in the underlying data files or configuration.
