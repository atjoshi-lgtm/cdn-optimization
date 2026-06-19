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

## Core Directives for Generating Code
- **Minimalism**: Write minimal, robust code. Do not add bloated `try/except` wrappers unless handling a highly specific, expected failure.
- **Data Encapsulation**: Never pass a file path to a `models/` class. Pass the loaded data structure.