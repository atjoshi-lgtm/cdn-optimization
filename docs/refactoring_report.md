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