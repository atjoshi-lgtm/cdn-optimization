# Probability Models (`src.cdn_optimizer.models.probability`)

This module provides the mathematical bedrock for latency predictions.

## Core Concepts
- **`PdfBucket`**: A simple dataclass mapping a latency range `[lower_ms, upper_ms)` to an occurrence count.
- **`Convolution`**: Uses Fast Fourier Transform (FFT) via `numpy` to sum independent random variables (e.g., Network RTT + Server TAT).

## How `ProbabilityDensityFunction` Works: Ingestion vs. Transformation

The `ProbabilityDensityFunction` represents a latency distribution and bridges the gap between raw database buckets and complex math through two distinct pathways:

**1. The Ingestion Path (`__init__` and Lazy Evaluation)**
When fetching data from the database, we receive wide latency buckets (e.g., 500 requests between 0ms and 5ms). 
* These are passed into `__init__` as a list of `PdfBucket` objects. 
* The `__init__` method simply stores them without performing any math. 
* The math happens **lazily** when the `@property probability_series` is accessed. It "smears" the bucket counts evenly across each millisecond and caches the result as a pandas `Series` at millisecond resolution.

**2. The Transformation Path (`from_millisecond_series`)**
During mathematical operations (like convolutions or applying `with_fraction_at` to simulate cache hits), the class generates raw pandas `Series` arrays. 
* To avoid the CPU overhead of reverse-engineering these arrays back into wide `PdfBucket`s, the class uses the `from_millisecond_series` factory method. 
* This method takes the computed pandas `Series`, generates dummy 1-millisecond-wide `PdfBucket`s to maintain a legal internal state, and directly injects the series into the `_probability_series` cache.

*Note:* `with_fraction_at(ms, fraction)` is heavily used to represent "Cache Hits" (by taking $1 - h$ of the curve and dumping the remaining mass $h$ at exactly 0ms, or vice versa).

## Agent Rules
- Do not import `matplotlib` here. Visualization belongs strictly in the `scripts/` directory.
- Use `__init__` for raw database rows and `from_millisecond_series` for internal mathematical transformations.