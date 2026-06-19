# Performance Model and FD for metros

A **metro performance model** predicts **latency behavior** for requests served through a metro. A **footprint descriptor** predicts **cache hit rate as a function of cache size**. They are related, but they model different things.

## Short version

- **Footprint descriptor (FD):**
  “If metro $m$ gets cache size $S_m$, what hit rate do we expect?”

- **Metro performance model:**
  “Given a request path through metro $m$ and a hit rate, what TTFB distribution do we expect?”

So:

- FD maps **disk $\to$ hit rate**
- Performance model maps **hit rate + network/service PDFs $\to$ latency distribution**

---

## 1. What a footprint descriptor is

In this repo, a footprint descriptor is a set of points:

$$
(s, r)
$$

where:

- $s$ = cache size
- $r$ = hit rate

For a metro $m$, the FD gives a function like:

$$
H_m(S_m)
$$

meaning: if we provision cache size $S_m$, what hit-rate percentage do we get?

In code, this is represented by `FootprintDescriptor` in `fds.py`.

It supports functions like:

- `hitrate_for_cache(cache_space)`
- `nearest_cache_for_hitrate(hitrate)`

So the FD is fundamentally a **cache-efficiency curve**.

### Intuition

If you give a metro more disk, more objects stay cached, so hit rate usually goes up.

That is all the FD is trying to capture.

It does **not** directly model latency.

---

## 2. What a metro performance model is

A metro performance model in this repo is built in `perf_with_mch.py` as `MetroPerformanceWithMCH`.

It stores latency distributions relevant to serving traffic through a metro, including:

- edge RTT from a client metro to this serving metro,
- edge TAT at the serving metro,
- midgress RTT from the serving metro to its parent/MCH,
- parent/MCH TAT at the upstream parent.

Using these PDFs plus a hit rate, it constructs a **TTFB PDF**.

So for serving metro $m$ and client metro $u$, it produces something like:

$$
L_{u,m}
$$

which is a full probability distribution of TTFB, not just a scalar.

From that PDF, the code extracts:

- p50
- p95

### Intuition

The performance model answers:

- How fast is a cache hit at this metro?
- How much slower is a miss?
- What network delay does the client see?
- What parent/MCH delay is incurred on misses?

So it is a **latency-path model**.

---

## 3. The key conceptual difference

### Footprint descriptor

A footprint descriptor is about **cache economics/efficiency**:

$$
S_m \mapsto h_m(S_m)
$$

It tells you how much disk is needed to achieve a certain hit rate.

### Performance model

A performance model is about **request latency**:

$$
h_m(S_m), \text{ path PDFs } \mapsto \text{TTFB distribution}
$$

It tells you how the chosen hit rate affects user-visible performance.

---

## 4. Why both are needed

The optimization needs both because disk allocation affects latency only indirectly.

The chain is:

$$
S_m
\to
h_m(S_m)
\to
\text{miss rate}
\to
\text{TTFB distribution}
\to
p50/p95 penalty
$$

So:

1. The FD tells you what hit rate a given cache size gives.
2. The performance model tells you what that hit rate means for latency.

Without the FD, you don’t know how disk changes hit rate.

Without the performance model, you don’t know how hit rate changes user performance.

---

## 5. What data each one uses

### Footprint descriptor uses

The FD comes from the `FDS_<bucket>/*.txt` files and is parsed by `FootprintDescriptor.from_text(...)`.

It uses cache-space/hit-rate observations, then smooths them.

So it is based on **cache behavior data**.

### Performance model uses

The performance model uses latency PDFs loaded from the performance database via functions in `analyse.py`:

- `get_rtt_pdf(...)`
- `get_edge_tat_pdf(...)`
- `get_midgress_rtt_pdf(...)`
- `get_parent_tat_pdf(...)`

So it is based on **network and service latency data**.

---

## 6. Objects in code

### Footprint descriptor object

`fds.py`:

- `FootprintDescriptor`
- stores points like cache size and hit rate
- supports nearest lookup and smoothing

### Metro performance model object

`perf_with_mch.py`:

- `MetroPerformanceWithMCH`
- contains:
  - `descriptor`
  - `edge_rtt`
  - `edge_tat_hit`
  - `mch_rtt`
  - `mch` parent model

and provides:

- `get_ttfb_pdf(from_metro, hitrate, conn)`

So the performance model is a larger object that uses latency PDFs and also references the FD-owning metro.

---

## 7. Does the performance model include the FD?

In code, `MetroPerformanceWithMCH` does store a `descriptor`, but conceptually they are still different.

Why?

Because the descriptor is only one ingredient. The performance model also needs:

- edge RTT PDFs,
- edge TAT PDF,
- MCH RTT PDF,
- parent TAT PDF.

So the FD is about **cache-hit probability**, while the performance model is about **latency consequences** of hit vs miss behavior.

You can think of the FD as an input to the broader performance story.

---

## 8. Example

Suppose metro $m$ has two candidate cache sizes:

- $S_m = 20$ TB gives hit rate $70\%$
- $S_m = 40$ TB gives hit rate $85\%$

The FD tells you exactly that:

$$
20 \text{ TB} \to 70\%
$$

$$
40 \text{ TB} \to 85\%
$$

But it does not tell you what this means for user latency.

The performance model then says:

- with 70% hits, 30% of requests pay miss-path latency,
- with 85% hits, only 15% pay miss-path latency,

so the TTFB distribution improves, and p50/p95 may drop.

That second step is the performance model.

---

## 9. In optimization terms

The FD contributes to the **cost side** and indirectly to performance because miss traffic depends on hit rate:

$$
\text{miss}_m = 1 - h_m(S_m)
$$

The performance model contributes to the **penalty side** because it determines:

$$
p50_u(\mathbf{S}), \quad p95_u(\mathbf{S})
$$

So:

- FD = “how much cache effectiveness do I buy with disk?”
- Performance model = “what latency do users experience because of that effectiveness?”

---

## 10. Summary table

| Concept           | Footprint Descriptor                               | Metro Performance Model                             |
| ----------------- | -------------------------------------------------- | --------------------------------------------------- |
| Main purpose      | Map cache size to hit rate                         | Map hit rate and latency PDFs to TTFB distribution  |
| Output            | Hit-rate percentage                                | TTFB PDF, then p50/p95                              |
| Depends on        | FD text files                                      | RTT/TAT PDFs + parent assignment + hit rate         |
| Question answered | “How much hit rate do I get from this cache size?” | “What latency does traffic see through this metro?” |
| Used for          | Cost and miss-rate calculations                    | Performance penalty calculations                    |
| Code              | `FootprintDescriptor` in `fds.py`                  | `MetroPerformanceWithMCH` in `perf_with_mch.py`     |

## Final distinction

A **footprint descriptor** models the **cache response curve** of a metro.

A **metro performance model** models the **latency response curve** of requests involving that metro.

The FD says how disk changes hit probability.  
The performance model says how hit probability changes user-perceived TTFB.