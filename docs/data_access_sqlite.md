# Data Access: SQLite Client (`src.cdn_optimizer.data_access.sqlite_client`)

This module isolates the application from the underlying SQLite performance database.

## Core Concepts
- **`SQLiteClient`**: A data-fetching class that executes SQL queries against `perf_data.db` and immediately maps the resulting `pandas.DataFrame` into mathematical `ProbabilityDensityFunction` models.
- **Fail Fast Principle**: If a database query yields zero rows, the client immediately raises a `MissingDataError`. It does not return empty PDFs.

## Agent Rules
- **No Math Here**: Do not perform PDF scaling, convoluting, or percentile extraction in this module. This module strictly handles `SELECT` statements and data type mapping.
- **Dependency Injection**: The database path is injected via the `__init__` constructor. Do not hardcode `PERF/perf_data.db` inside this class.