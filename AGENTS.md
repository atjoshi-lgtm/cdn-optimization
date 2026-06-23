# Agent Directives: CDN Optimization Codebase

This repository has been explicitly architected to enforce strict separation of concerns. Do not break these boundaries.

## Architecture Philosophy

1. **`src/cdn_optimizer/models/`**: Pure math and business logic. 
   - *Rule*: NO data fetching, NO file I/O, NO database connections, and NO plotting libraries (`matplotlib`). These classes accept standard data structures (e.g., Pandas DataFrames, basic Python types) and return mathematical results.
2. **`src/cdn_optimizer/data_access/`**: The ONLY place that speaks to the outside world.
   - *Rule*: This layer parses text files (`fds_loader.py`) and executes SQLite queries (`sqlite_client.py`). It returns pure mathematical objects (like `ProbabilityDensityFunction` or `FootprintDescriptor`) to the higher layers.
3. **`src/cdn_optimizer/topology/`**: Network and geographic logic.
   - *Rule*: Used to figure out which client metros map to which edge metros, and calculating Haversine distances. 
4. **`scripts/`**: The glue.
   - *Rule*: Scripts connect `data_access` to `models`. Scripts are allowed to contain plotting logic and write to CSVs for user analysis.
   - *Current pairwise analysis entry points*: `scripts/analyze_pairwise_paths.py` (disk-size sweep with footprint descriptors) and `scripts/analyze_pairwise_hitrate_heatmaps.py` (direct edge/parent hit-rate sweep with heatmaps).

## Core Directives for Generating Code
- **Minimalism**: Write minimal, robust code. Do not add bloated `try/except` wrappers unless handling a highly specific, expected failure.
- **Data Encapsulation**: Never pass a file path to a `models/` class. Pass the loaded data structure.

## Codebase Structure & Context Guide

If you are tasked with debugging or extending this codebase, use the following map to find the relevant context. Do not guess; read the docs.

### 1. Domain Theory & Mathematics (`docs/theory/`)
Before touching the codebase, ensure you understand the math:
* **`terms_and_examples.md`**: Defines CDN-specific jargon (e.g., ASN Metro vs. BW Metro). Read this if you are confused about traffic routing variables.
* **`perf_model_and_fd.md`**: Explains the conceptual split between Cache Efficiency (FD) and Latency Physics.

### 2. Software Architecture (`docs/`)
If you need to know how the math is implemented in Python, refer to:
* **`models_probability.md`**: Explains the `PdfBucket` ingestion vs. `pandas.Series` transformation logic.
* **`models_footprint.md`**: Explains the tie-breaking and plateau-flattening algorithms for cache efficiency.
* **`models_latency_path.md`**: Explains the finite mixture model for TTFB, including explicit edge-hit and conditional parent-hit semantics used by the heatmap script.
* **`data_access_sqlite.md` & `data_access_fds_loader.md`**: Explains the strict "Fail Fast" file I/O and database boundaries.
* **`core_and_topology.md`**: Explains how string names map to network IDs.

### 3. Debugging Protocol
1. Identify the layer where the bug occurs (Data Access, Topology, or Math Models).
2. Read the corresponding architectural doc.
3. If the bug involves a mathematical calculation, cross-reference the Python code with `docs/theory/mathematical_formulation.md`.
4. For pairwise latency analysis issues, check both `scripts/analyze_pairwise_paths.py` and `scripts/analyze_pairwise_hitrate_heatmaps.py` to determine whether the behavior comes from a footprint-derived sweep or an explicit hit-rate sweep.