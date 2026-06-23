# Data Access: SQLite Client (`src.cdn_optimizer.data_access.sqlite_client`)

This module isolates the application from the underlying SQLite performance database.

## Core Concepts
- **`SQLiteClient`**: A data-fetching class that executes SQL queries against `perf_data.db` and immediately maps the resulting `pandas.DataFrame` into mathematical `ProbabilityDensityFunction` models.
- **Fail Fast Principle**: If a database query yields zero rows, the client immediately raises a `MissingDataError`. It does not return empty PDFs.

## Key Query Methods
- **`get_edge_rtt_pdf(metro_name, client_metro_id)`**: Fetches Client->Edge RTT PDF.
- **`get_edge_tat_pdf(metro_name, cache_hit_type=1)`**: Fetches edge TAT PDF, typically edge-hit type.
- **`get_midgress_rtt_pdf(parent_metro, child_metro)`**: Fetches Edge->Parent RTT PDF.
- **`get_parent_tat_pdf(metro_name, cache_hit_type=None)`**: Fetches parent TAT PDF with two modes:
	- `cache_hit_type=None`: Legacy behavior (`cache_hit_type != 2`).
	- `cache_hit_type=1` or `cache_hit_type=0`: Explicitly fetch parent-hit or parent-miss TAT PDFs.

This explicit parent TAT split supports the 3-path pairwise latency model where parent-hit and parent-miss service times are modeled separately.

## Agent Rules
- **No Math Here**: Do not perform PDF scaling, convoluting, or percentile extraction in this module. This module strictly handles `SELECT` statements and data type mapping.
- **Dependency Injection**: The database path is injected via the `__init__` constructor. Do not hardcode `PERF/perf_data.db` inside this class.
