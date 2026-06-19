# Footprint Models (`src.cdn_optimizer.models.footprint`)

This module defines the cache efficiency curve for a metro. It maps provisioned disk space (in MB) to expected cache hit rates (in %).

## Core Concepts

### 1. `FootprintPoint`
A lightweight, immutable dataclass representing a single observation on the cache efficiency curve.
* **`cache_space`** (`int`): The provisioned disk size in Megabytes (MB).
* **`hitrate`** (`float`): The expected hit rate as a percentage ($0.0$ to $100.0$).

### 2. `FootprintDescriptor`
The mathematical representation of a metro's cache efficiency. It ingests a collection of `FootprintPoint`s and provides fast, nearest-neighbor lookups to translate between disk size and hit rate.

## How `FootprintDescriptor` Works: Internal Mechanics

When a `FootprintDescriptor` is initialized, it does not just store the points. It optimizes them for rapid mathematical querying:
1. **Deduplication**: If multiple points have the exact same `cache_space`, it inherently deduplicates them during dictionary mapping.
2. **Dual-Sorting**: It maintains two separate, sorted internal lists:
   * `_points_sorted_by_cache`: Used for finding hit rates when disk size is the known variable.
   * `_points_sorted_by_hitrate`: Used for finding required disk space when a target hit rate is the known variable.

Because these lists are pre-sorted, the class uses `bisect_left` (binary search) to achieve $O(\log n)$ time complexity for all nearest-neighbor lookups.

## Important Methods

### `hitrate_for_cache(cache_space: int) -> float`
Finds the expected hit rate for a given disk size. If an exact match is not found, it falls back to `nearest_point_for_cache`.
* **Tie-breaker math**: If the requested `cache_space` sits exactly halfway between two known points, the algorithm conservatively favors the **smaller** cache space.

### `nearest_cache_for_hitrate(hitrate: float) -> int`
The inverse function. Answers the question: *"How much disk do I need to achieve an $X\%$ hit rate?"*
* **Tie-breaker math**: If the requested `hitrate` is equidistant from two known points, it favors the **lower** hit rate (pessimistic estimation). If the hit rates are identical, it returns the point requiring the **smaller** cache space (cost efficiency).

### `smooth_by_cache_bucket(bucket_size_mb: int = 10240) -> FootprintDescriptor`
Raw footprint data is often noisy. This method generates a new, smoothed `FootprintDescriptor` using three rules:
1. **Bucketing**: Points are grouped into discrete buckets (default 10 GB). If multiple points fall in one bucket, the *lowest* hit rate is retained (conservative).
2. **Gap Interpolation**: If there is a missing bucket between two populated buckets, the algorithm fills it using linear interpolation.
3. **Plateau Flattening**: If consecutive buckets have the exact same hit rate (a plateau), the algorithm assumes steady marginal gains and spreads the delta evenly across the plateau, ensuring a strictly monotonically increasing curve where possible. Instead of allowing a sudden jump in hit rate followed by a flat line, the algorithm takes that sudden jump (the delta) and slices it into smaller, equal steps, creating a ramp. This results in a more realistic curve that reflects gradual improvements rather than unrealistic plateaus.

## Usage Example

```python
from cdn_optimizer.models.footprint import FootprintPoint, FootprintDescriptor

# 1. Provide raw data points (usually done by the data_access layer)
raw_points = [
    FootprintPoint(cache_space=10000, hitrate=45.0),
    FootprintPoint(cache_space=20000, hitrate=60.0),
    FootprintPoint(cache_space=40000, hitrate=80.0),
]

# 2. Initialize the descriptor
descriptor = FootprintDescriptor(raw_points)

# 3. Query exact or nearest values
hitrate = descriptor.hitrate_for_cache(20000)      # Returns 60.0
hitrate_est = descriptor.hitrate_for_cache(14000)  # Returns 45.0 (nearest neighbor)

required_disk = descriptor.nearest_cache_for_hitrate(75.0) # Returns 40000
```

## Agent Rules
- No File I/O: The FootprintDescriptor must remain purely mathematical. It does not know what a "file" or a "path" is. File parsing belongs entirely to `src.cdn_optimizer.data_access.fds_loader`. The loader reads the file and returns instantiated `FootprintDescriptor` objects.
- Unit Expectations: Always assume cache_space is passed in Megabytes (MB) and hitrate is a percentage ($0.0$ to $100.0$), unless explicitly scaling fractions for convolutions.