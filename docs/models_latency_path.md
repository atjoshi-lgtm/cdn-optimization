# Latency Path Models (`src.cdn_optimizer.models.latency_path`)

This module is responsible for calculating the Time-To-First-Byte (TTFB) distributions.

## Core Concepts
- **`PairwiseLatencyModel`**: Replaces the legacy `MetroPerformanceWithMCH` and `MCHPerformanceModel` classes. It evaluates a single, isolated path: `Client -> Edge -> Parent`.
- **The Mixture Model**: It calculates TTFB using three convolved paths and merges them with `weighted_pdf_sum`.
	- Path 1 (Edge Hit): `Edge RTT + Edge Hit TAT`, weight $h_e$
	- Path 2 (Parent Hit): `Edge RTT + Midgress RTT + Parent Hit TAT`, weight $(1-h_e)h_p$
	- Path 3 (Parent Miss): `Edge RTT + Midgress RTT + Parent Miss TAT`, weight $(1-h_e)(1-h_p)$
	- The model validates that path weights sum to $1.0$.

## Hit-Rate Semantics
- `edge_hitrate_percentage` is the unconditional edge hit rate.
- `parent_hitrate_percentage` is interpreted as the parent hit rate **conditioned on edge misses**.
- The resulting mixture weights are:
  - $w_{\rm edge\ hit} = h_e$
  - $w_{\rm parent\ hit} = (1-h_e)h_p$
  - $w_{\rm parent\ miss} = (1-h_e)(1-h_p)$
- Operational implication: when edge hit rate approaches $100\%$, parent hit rate has negligible or zero effect on final TTFB because the parent branches are weighted by $(1-h_e)$.

## Script Integration Notes
- `scripts/analyze_pairwise_paths.py` derives edge and parent hit rates from footprint descriptors and effective parent capacity assumptions.
- `scripts/analyze_pairwise_hitrate_heatmaps.py` bypasses footprint descriptors entirely and directly sweeps explicit edge/parent hit-rate inputs over a 2D grid to generate p50/p95 heatmaps for each analyzable `Client -> Edge -> Parent` path.

## Agent Rules
- **Fail Fast**: The legacy code used `_create_dummy_pdf()` to silently inject fake data if a database query failed. **This is strictly forbidden.** If a PDF is empty, the model must raise a `ValueError` immediately. Missing data must be handled at the `data_access` layer, never masked by the mathematical models.

## Detailed Explanation of the Physics
In our mathematical model, predicting the Time-To-First-Byte (TTFB) requires breaking a network request down into its physical, temporal components. These five properties represent the probability distributions (PDFs) of time spent at each step of the journey.

Here is the breakdown of the five fundamental physical properties defining a pairwise routing path:

### 1. Edge RTT (`edge_rtt_pdf` / $R^{\rm edge}_{u,m}$)

* **What it is:** The network round-trip latency between end users in a specific client metro ($u$) and the serving edge metro ($m$).
* **The Physics:** This is the time spent in transit over the "last mile" and public internet. It represents how long it takes for a user's request packet to travel across fiber optics to the edge server, plus the time it takes for the first byte of the payload to travel back to their device.
* **Always Paid:** Every single request, whether a cache hit or a miss, must pay this latency penalty.

### 2. Edge TAT (`edge_tat_hit_pdf` / $A_m^{\rm edge}$)

* **What it is:** The service-time or processing-time distribution at the serving metro for handling an edge request.
* **The Physics:** "TAT" stands for Turnaround Time. This is the hardware latency of the edge server itself. It measures the milliseconds the CPU and disk controller spend parsing the HTTP request, looking up the object in the cache directory, reading the file from the local SSD/HDD, and pushing it to the network socket.

### 3. Midgress RTT (`midgress_rtt_pdf` / $R_m^{\rm mch}$)

* **What it is:** The network latency incurred when a request misses at the edge and must go upstream to the parent/MCH metro.
* **The Physics:** If the edge server does not have the file, it must ask the larger regional parent cache. This is the transit time across the CDN's internal backbone connecting the edge city to the parent city (e.g., from an edge in Seattle to a parent cache in Los Angeles).

### 4. Parent Hit TAT (`parent_tat_hit_pdf` / $A_{m,\mathrm{hit}}^{\rm mch}$)

* **What it is:** The upstream service-time distribution at the parent tier when the parent cache hits.
* **The Physics:** This captures parent processing time when the object is found at the parent layer.

### 5. Parent Miss TAT (`parent_tat_miss_pdf` / $A_{m,\mathrm{miss}}^{\rm mch}$)

* **What it is:** The upstream service-time distribution at the parent tier when the parent cache misses.
* **The Physics:** This captures parent processing time on misses, which can differ from parent-hit behavior due to different backend handling.

---

### The Big Picture: Combining the Physics

By using the mathematical convolution class (`Convolution`), we add these independent random variables together to simulate the three possible realities a request can face:

* **The Edge Hit Reality:** Edge RTT + Edge Hit TAT
* **The Parent Hit Reality:** Edge RTT + Midgress RTT + Parent Hit TAT
* **The Parent Miss Reality:** Edge RTT + Midgress RTT + Parent Miss TAT

We then mix these three realities together based on edge and parent hit rates to get the final, user-perceived TTFB.
