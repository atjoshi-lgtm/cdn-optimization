# Latency Path Models (`src.cdn_optimizer.models.latency_path`)

This module is responsible for calculating the Time-To-First-Byte (TTFB) distributions.

## Core Concepts
- **`PairwiseLatencyModel`**: Replaces the legacy `MetroPerformanceWithMCH` and `MCHPerformanceModel` classes. It evaluates a single, isolated path: `Client -> Edge -> Parent`.
- **The Mixture Model**: It calculates TTFB by convolving the base PDFs into a "Pure Hit Path" and a "Pure Miss Path", and then merging them into a single distribution using `weighted_pdf_sum` based on the provided cache hit rate.

## Agent Rules
- **Fail Fast**: The legacy code used `_create_dummy_pdf()` to silently inject fake data if a database query failed. **This is strictly forbidden.** If a PDF is empty, the model must raise a `ValueError` immediately. Missing data must be handled at the `data_access` layer, never masked by the mathematical models.

## Detailed Explanation of the Physics
In our mathematical model, predicting the Time-To-First-Byte (TTFB) requires breaking a network request down into its physical, temporal components. These four properties represent the probability distributions (PDFs) of time spent at each step of the journey.

Here is the breakdown of the four fundamental physical properties defining a pairwise routing path:

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

### 4. Parent TAT (`parent_tat_pdf` / $A_m^{\rm mch}$)

* **What it is:** The upstream service-time distribution at the parent tier.
* **The Physics:** Just like the Edge TAT, this is the hardware processing time, but at the parent data center. It is the time the parent server spends looking up the object in its massive storage arrays and writing it to the outbound socket back to the edge.

---

### The Big Picture: Combining the Physics

By using the mathematical convolution class (`Convolution`), we add these independent random variables together to simulate the two possible realities a request can face:

* **The Cache Hit Reality:** Edge RTT + Edge TAT
* **The Cache Miss Reality:** Edge RTT + Midgress RTT + Parent TAT

We then mix these two realities together based on the expected cache hit rate to get the final, user-perceived TTFB.