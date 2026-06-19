# Data Access: FDS Loader (`src.cdn_optimizer.data_access.fds_loader`)

This module isolates the application from the underlying `.txt` Footprint Descriptor files on disk.

## Core Concepts
- **`load_footprint_descriptor`**: Opens a text file, skips the header, ignores comments, and parses the whitespace-separated values. It extracts `cache_space` from column 0 and `hitrate` from column 4, packaging them into `FootprintPoint` objects.

## Agent Rules
- **No Math Here**: Do not perform cache-bucket smoothing, plateau flattening, or nearest-neighbor lookups in this module. This module strictly handles `open()`, string splitting, and type casting. 
- **Decoupling**: It returns an instantiated `FootprintDescriptor` to the caller, ensuring the mathematical models never have to interact with the file system.