# CDN Optimization Codebase: Refactoring Report

This document tracks the ongoing migration from the legacy, monolithic script-based architecture into the clean, modular `cdn-optimization` repository. 

## Architectural Goals
1. **Strict Separation of Concerns:** Math models never touch the file system or databases. Data access layers never perform complex math.
2. **Fail Fast:** Missing data throws explicit errors (e.g., `MissingDataError`) instead of failing silently or using dummy data.
3. **No Side Effects in Models:** Plotting (`matplotlib`) and writing files are strictly reserved for top-level scripts.

---

## Refactoring Map (What we have done so far)

### 1. Probability & Mathematics
* **Old File:** `probability.py`
* **New File:** `src/cdn_optimizer/models/probability.py`
* **Changes:** * Retained core convolution (FFT) and PDF structures.
  * Stripped all `matplotlib` plotting functions.
  * Removed defensive import checks for `pandas` and `numpy` (now enforced via `pyproject.toml`).

### 2. Footprint Descriptors (Cache Efficiency)
* **Old File:** `fds.py`
* **New Files:** * `src/cdn_optimizer/models/footprint.py` (Pure Math)
  * `src/cdn_optimizer/data_access/fds_loader.py` (File I/O)
* **Changes:**
  * Separated the mathematical representation (`FootprintDescriptor`) from the file reading logic.
  * `FootprintDescriptor` now only accepts raw data objects, no longer knowing about file paths or `.txt` formats.

### 3. Latency & Physics Path
* **Old File:** `perf_with_mch.py`
* **New File:** `src/cdn_optimizer/models/latency_path.py`
* **Changes:**
  * Collapsed the confusing and coupled `MetroPerformanceWithMCH` and `MCHPerformanceModel` into a single, elegant `PairwiseLatencyModel`.
  * Removed `_create_dummy_pdf()` which silently masked database failures. The model now strictly enforces valid input PDFs.
  * **Update (3-Path TTFB):** Upgraded from a 2-path hit/miss mixture to a 3-path model with explicit parent-hit and parent-miss branches.
  * **API Update:** `PairwiseLatencyModel.__init__` now accepts `parent_tat_hit_pdf` and `parent_tat_miss_pdf` separately.
  * **API Update:** `get_ttfb_pdf` now accepts `edge_hitrate_percentage` and `parent_hitrate_percentage` with weights:
    * $w_1 = h_e$
    * $w_2 = (1-h_e)h_p$
    * $w_3 = (1-h_e)(1-h_p)$

### 4. Database Access & Topography (The Monolith)
* **Old File:** `analyse.py`
* **New Files:**
  * `src/cdn_optimizer/data_access/sqlite_client.py` (DB Queries)
  * `src/cdn_optimizer/data_access/csv_parser.py` (CSV Reading)
  * `src/cdn_optimizer/topology/network_map.py` (Metro ID Resolution)
  * `src/cdn_optimizer/core/exceptions.py` (Custom Errors)
* **Changes:**
  * Replaced the sprawling global state and raw f-string SQL queries with a safe, parameterized `SQLiteClient`.
  * RTT and TAT database fetches now explicitly raise `MissingDataError` if the database returns empty sets.
  * Segregated the parsing of `metro_areas.csv` into a dedicated topological mapping layer.
  * **Update**: Expanded `csv_parser.py` and `network_map.py` to support bidirectional mapping (Name $\leftrightarrow$ ID) to replace the old `client_metro_ids` and `client_metros` global dictionaries.
  * **Bugfix (SQLite Parsing)**: Moved the regex parsing logic (`rtt_0_5_ms`, etc.) out of the mathematical `ProbabilityDensityFunction` class and into `sqlite_client.py`. This ensures the database schema logic is fully contained within the data layer, passing clean `PdfBucket` instances into the mathematical models.
  * **Feature (Dynamic Topography)**: Added `get_active_parent_for_edge` to `sqlite_client.py`. It dynamically derives parent-child MCH relationships by aggregating `total_requests` from the `netopt_perf_midgress_rtt_ansabni` table, eliminating the need for hardcoded parent mappings.
  * **Bugfix (Data-Join Mismatch)**: Updated `csv_parser.py` to extract `airport_code` from column 4 of `metro_areas.csv`. This provides a crucial translation layer between the SQLite database (which logs by City Name) and the File System (which names FDS files by Airport Code).d
  * **Feature (Traffic Matrix Filter)**: Implemented parsing of `served_from.csv` to map $(u,m)$ traffic volumes. Integrated the `_TRAFFIC_THRESHOLD` parameter ($\theta$) into `discover_analyzable_paths.py` to filter out negligible traffic and expose only the mathematically significant topological relationships.
  * **Update (Parent TAT Querying):** Extended `get_parent_tat_pdf` with optional `cache_hit_type`.
    * `None`: preserves legacy behavior (`cache_hit_type != 2`).
    * `1`: parent-hit TAT only.
    * `0`: parent-miss TAT only.

### 5. Configuration Management
* **Old Implementation:** Hardcoded globals scattered across `analyse.py`, `solve_for_US.py`, and `example_4.py`.
* **New Files:**
  * `config/default_config.yaml`
  * `src/cdn_optimizer/core/config_loader.py`
* **Changes:**
  * Centralized environment paths, bucket configurations, and default settings into a standard YAML format parsed into a strictly-typed Python dataclass.

### 6. Pairwise Analysis Script (The Glue Layer)
* **Old File:** `analyze_pairwise_path.py`
* **New File:** `scripts/analyze_pairwise_paths.py`
* **Changes:**
  * Script now solely acts as the orchestrator. It loads config, uses `data_access` clients to fetch pure mathematical objects, passes them to `models`, and handles the visual output.
  * Explicitly imports `matplotlib` and `csv` here, confirming that no side-effect libraries have polluted the mathematical and data layers.
  * **Update (Parent Hit/Miss Inputs):** Fetches parent TAT PDFs separately via `cache_hit_type=1` (hit) and `cache_hit_type=0` (miss).
  * **Update (Perfect Exclusion):** Adds constants `PARENT_DISK_TB` and `EDGE_TRAFFIC_SHARE`, then computes:
    * `effective_parent_mb = (PARENT_DISK_TB * 1024 * 1024) * EDGE_TRAFFIC_SHARE`
    * `global_hitrate = descriptor.hitrate_for_cache(current_disk_mb + effective_parent_mb)`
    * `parent_hitrate = ((global_hitrate - edge_hitrate) / (100.0 - edge_hitrate)) * 100.0` with a 100% edge-hitrate safeguard.
  * **Update (Outputs):** CSV and plots now include both `edge_hitrate_percent` and `parent_hitrate_percent`.

### 6.1 Pairwise Hit-Rate Heatmap Script (The Glue Layer)
* **New File:** `scripts/analyze_pairwise_hitrate_heatmaps.py`
* **Purpose:** Analyze each `Client -> Edge -> Parent` route by directly sweeping cache hit rates instead of deriving them from footprint descriptors.
* **Changes:**
  * Loads all analyzable paths from `data/analyzable_paths.json` and iterates path-by-path.
  * Reuses `SQLiteClient`, `MetroResolver`, and `PairwiseLatencyModel` orchestration patterns from the pairwise script.
  * Sweeps an explicit 2D hit-rate grid for each path:
    * `edge_hitrate_percentage`: 0 to 100 in 5% steps.
    * `parent_hitrate_percentage`: 0 to 100 in 5% steps.
  * Computes TTFB per grid cell via `PairwiseLatencyModel.get_ttfb_pdf(...)` and extracts p50/p95.
  * Writes per-path outputs:
    * `heatmap_p50_<client>_to_<edge>_via_<parent>.csv`
    * `heatmap_p95_<client>_to_<edge>_via_<parent>.csv`
    * `heatmap_<client>_to_<edge>_via_<parent>.png`
  * Keeps fail-fast behavior by skipping paths on `MissingDataError`, `ValueError`, or `FileNotFoundError`.

### 7. Utility Scripts
* **New File:** `scripts/discover_analyzable_paths.py`
* **Purpose:** A diagnostic tool that intersects the SQLite database records, the CSV topology mappings, and the FDS file system to dynamically discover which pairwise routing paths contain sufficient data for analysis.
* **Update**: Enhanced `discover_analyzable_paths.py` to dynamically resolve and cache the active parent metro for each edge using the `SQLiteClient`. Changed the output mechanism from standard console printing to generating a structured `analyzable_paths.json` file for easier programmatic and manual consumption.