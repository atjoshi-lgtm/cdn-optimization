# Mathematical Formulation of the Optimization Problem Implemented in `solve_for_US.py` (OUTDATED)

This document states the optimization problem represented by the current implementation of `solve_for_US.py` and its directly used modules:

- `fds.py`
- `cost.py`
- `perf_with_mch.py`
- `probability.py`
- `analyse.py`

The formulation below is intended to match the code as implemented, not an idealized CDN optimization model.

---

## 1. High-Level Summary

The code evaluates an objective of the form:

$$
\sum_{m \in \mathcal{A}} C_m(S_m)
+
\sum_{u \in \mathcal{A}} P_u(\mathbf{S})
$$

where:

- $S_m$ is the provisioned cache size for metro $m$.
- $C_m(S_m)$ is the monthly cost for metro $m$.
- $P_u(\mathbf{S})$ is the performance penalty for client/end-user metro $u$.
- $\mathcal{A}$ is the set of active metros for which both a footprint descriptor and a performance model are available.

Important corrections relative to earlier formulations:

1. There is **no explicit egress cost** term in the code.
2. The cost model includes:
   - depreciation cost,
   - colocation cost,
   - midgress cost,
   - parent-service cost.
3. Parent-service cost is computed from a metro’s own aggregate miss traffic, not from traffic served as a parent for other metros.
4. Traffic costs are based on aggregate incoming traffic to a serving metro, not on per-neighbor parent-service edges.
5. Cache sizes are represented in MB in the optimization state and footprint descriptors.
6. Hit rates are stored as percentages in footprint descriptors and converted to fractions for cost calculations.
7. There is no global disk-budget constraint in the evaluated optimization problem. The code only uses an iteration-level update budget inside the search heuristic.
8. Replication factor is a fixed parameter determined by metro tier, not a decision variable.

---

## 2. Sets and Indices

Let:

- $\mathcal{M}$ be the set of all metros selected for the requested geo.
- $\mathcal{A} \subseteq \mathcal{M}$ be the set of active metros, i.e. metros for which the code has both:
  - a smoothed footprint descriptor, and
  - a performance model.

The code’s active set is:

$$
\mathcal{A}
=
\{m \in \mathcal{M}: m \in \texttt{FDS\_BY\_METRO} \text{ and } m \in \texttt{PERFORMANCE\_MODELS}\}
$$

Use:

- $u$ for a client, end-user, or ASN metro.
- $m$ for a serving, bandwidth, or edge metro.

The served-from data contains rows of the form:

$$
(\text{asn\_metro}, \text{bw\_metro}, \text{traffic\_mbps})
$$

After conversion from metro-area names to airport codes:

- $u$ corresponds to `asn_metro`.
- $m$ corresponds to `bw_metro`.

Define:

$$
\mathcal{B}_u
=
\{m \in \mathcal{M}: Q_{u,m} > \theta\}
$$

as the set of serving metros used by client metro $u$ after applying the traffic threshold $\theta$.

In code:

$$
\mathcal{B}_u
=
\texttt{neighborhood\_to[u]}
$$

Define:

$$
\mathcal{U}_m
=
\{u \in \mathcal{M}: Q_{u,m} > \theta\}
$$

as the set of client metros served by serving metro $m$ after applying the traffic threshold.

In code:

$$
\mathcal{U}_m
=
\texttt{neighborhood\_from[m]}
$$

---

## 3. Traffic Parameters

Let:

$$
Q_{u,m} \ge 0
$$

be the traffic in Mbps from client metro $u$ to serving metro $m$.

In code:

$$
Q_{u,m}
=
\texttt{traffic\_lookup\_by\_airport[(u,m)]}
$$

where `traffic_lookup_by_airport` is derived from `SERVEDFROM_DATA/served_from_<bucket>.csv`.

### 3.1 Aggregate Incoming Traffic at a Serving Metro

For each serving metro $m$, define:

$$
T_m^{\rm in}
=
\sum_{u \in \mathcal{U}_m} Q_{u,m}
$$

This is the aggregate traffic, in Mbps, arriving at serving metro $m$ from client metros.

In code:

$$
T_m^{\rm in}
=
\texttt{INCOMING\_TRAFFIC[m]}
$$

This quantity is used by the cost model.

### 3.2 Aggregate Traffic Originating from a Client Metro

For each client metro $u$, define:

$$
T_u^{\rm from}
=
\sum_{m \in \mathcal{B}_u} Q_{u,m}
$$

This is the aggregate traffic, in Mbps, originating from client metro $u$ and served by its serving metros.

In code:

$$
T_u^{\rm from}
=
\texttt{TRAFFIC\_FROM[u]}
$$

This quantity is used to scale the performance penalty.

---

## 4. Decision Variables

For each active metro $m \in \mathcal{A}$, the decision variable is:

$$
S_m
$$

where:

- $S_m$ is the provisioned cache size for metro $m$.
- $S_m$ is represented in MB in the code.
- $S_m$ corresponds to `DISK_PROVISIONED[m]`.

The decision vector is:

$$
\mathbf{S}
=
(S_m)_{m \in \mathcal{A}}
$$

---

## 5. Footprint Descriptors and Hit-Rate Function

Each metro $m$ has a footprint descriptor consisting of cache-size and hit-rate observations.

After parsing and smoothing, define the descriptor as:

$$
\mathcal{F}_m
=
\{(s_{m,k}, r_{m,k})\}_{k \in K_m}
$$

where:

- $s_{m,k}$ is a cache size in MB.
- $r_{m,k}$ is a hit rate in percent.
- $r_{m,k} \in [0,100]$.

In code, this is represented by:

$$
\texttt{FDS\_BY\_METRO[m]}
$$

or an individual `FootprintDescriptor`.

---

## 6. Footprint Descriptor Parsing

`FootprintDescriptor.from_text(...)` parses an FD text file as follows:

1. The first line is skipped.
2. Each remaining nonempty, non-comment line is split into whitespace-separated columns.
3. The cache size is parsed from column `0`.
4. The hit rate is parsed from column `4`.

Thus, mathematically, an FD row contributes:

$$
s = \text{column}_0
$$

$$
r = \text{column}_4
$$

The cache size $s$ is in MB, and the hit rate $r$ is a percentage.

---

## 7. FD Smoothing

The code applies:

$$
\texttt{smooth\_by\_cache\_bucket(bucket\_size\_mb)}
$$

with default bucket size:

$$
B = 10 \cdot 1024
$$

MB.

The smoothing procedure is:

1. Each raw cache size $s$ is floored to a bucket boundary:

$$
\bar{s}
=
B \left\lfloor \frac{s}{B} \right\rfloor
$$

2. If multiple raw FD points fall into the same cache bucket, the lowest hit rate in that bucket is retained:

$$
\bar{r}_{m,b}
=
\min \{r_{m,k}: \bar{s}_{m,k} = b\}
$$

3. Missing buckets between consecutive populated buckets are filled by linear interpolation of hit rate.

4. Runs of consecutive buckets with equal hit rate are adjusted by spreading the increase from the immediately previous hit rate across the plateau.

The result is a smoothed discrete set of cache/hit-rate points:

$$
\mathcal{F}_m
=
\{(s_{m,k}, r_{m,k})\}_{k \in K_m}
$$

---

## 8. Cache-to-Hit-Rate Function

The implemented hit-rate lookup is nearest-neighbor, not continuous interpolation.

For any provisioned cache size $S_m$, define:

$$
k^\star(S_m)
\in
\arg\min_{k \in K_m}
|S_m - s_{m,k}|
$$

with tie-breaking toward the smaller cache size.

The hit rate as a percentage is:

$$
H_m(S_m)
=
r_{m,k^\star(S_m)}
$$

In code:

$$
H_m(S_m)
=
\texttt{descriptor.hitrate\_for\_cache(S\_m)}
$$

The hit-rate fraction used in cost calculations is:

$$
h_m(S_m)
=
\frac{H_m(S_m)}{100}
$$

Thus:

$$
h_m(S_m) \in [0,1]
$$

The miss fraction is:

$$
\mu_m(S_m)
=
1 - h_m(S_m)
$$

Because the code uses nearest-neighbor lookup over a smoothed FD grid, $H_m(S_m)$ is best modeled as a stepwise nearest-neighbor function, not as a smooth continuous function.

---

## 9. Cache Bounds

For each active metro $m$, define:

$$
S_m^{\min}
=
\min_{k \in K_m} s_{m,k}
$$

and:

$$
S_m^{\max}
=
\max_{k \in K_m} s_{m,k}
$$

The code enforces the bounds:

$$
S_m^{\min}
\le
S_m
\le
S_m^{\max}
\qquad
\forall m \in \mathcal{A}
$$

during update steps.

There is no global disk budget constraint in the evaluated objective.

---

## 10. Replication Factor

Each metro has a fixed replication factor:

$$
R_m \in \{2,3,5\}
$$

determined by metro tier.

The implemented rule is:

$$
R_m =
\begin{cases}
5, & \text{if tier}(m) = 0, \\
3, & \text{if tier}(m) = 1, \\
2, & \text{otherwise.}
\end{cases}
$$

In code:

$$
R_m
=
\texttt{replication\_factor\_for\_metro(metro, metro\_tiers, airport\_to\_metro)}
$$

The replication factor is a fixed parameter, not a decision variable.

---

## 11. Cost Model

The cost model is implemented by `CaribouCostCalculator.compute_monthly_cost(...)` and wrapped by `compute_replicated_total_cost_model_b(...)`.

There is no explicit egress cost term.

The implemented cost components are:

1. Depreciation cost.
2. Colocation cost.
3. Midgress cost.
4. Parent-service cost.

---

## 12. Cost Constants

Let:

- $K = 35$ be the Caribou disk capacity in TB per machine.
- $c^{\rm dep}$ be monthly disk depreciation cost per machine.
- $c^{\rm colo}$ be monthly colocation cost per machine.
- $c^{\rm par}$ be monthly parent-service cost per machine.
- $E_{\gamma,b}$ be effective capacity in Mbps for geo $\gamma$ and traffic class or bucket $b$.
- $\rho_m$ be the midgress cost per Mbps-month for metro $m$.

In code:

$$
K
=
\texttt{CARIBOU\_DISK\_CAPACITY\_TB}
=
35
$$

The monthly disk depreciation per machine is:

$$
c^{\rm dep}
=
\frac{
\texttt{CARIBOU\_MACHINE\_COST\_USD}
\cdot
\texttt{CARIBOU\_DISK\_COST\_RATIO}
}{
\texttt{CARIBOU\_DEPRECIATION\_MONTHS}
}
$$

The monthly parent-service cost per machine is:

$$
c^{\rm par}
=
\frac{
\texttt{CARIBOU\_MACHINE\_COST\_USD}
\cdot
(1-\texttt{CARIBOU\_DISK\_COST\_RATIO})
}{
\texttt{CARIBOU\_DEPRECIATION\_MONTHS}
}
$$

The monthly colocation cost per machine is:

$$
c^{\rm colo}
=
c^{\rm infra}
+
c^{\rm power}
$$

where:

$$
c^{\rm infra}
=
\frac{\texttt{CARIBOU\_POWER\_RATING\_WATTS}}{1000}
\cdot
\texttt{KW\_INFRA\_COST\_PER\_KW\_MONTH}
$$

and:

$$
c^{\rm power}
=
\frac{\texttt{CARIBOU\_AVERAGE\_POWER\_USAGE\_WATTS}}{1000}
\cdot
\texttt{hours\_per\_month}
\cdot
\texttt{metered\_power\_rate\_per\_kwh}
$$

The effective capacity is:

$$
E_{\gamma,b}
=
\texttt{get\_effcap(geo, traffic\_class)}
$$

with fallback:

$$
E_{\gamma,b}
=
24966
$$

Mbps if no table entry is found.

---

## 13. Disk Unit Conversion in Cost Model

Although the cost function argument is named `total_disk_required_tb`, `solve_for_US.py` passes cache sizes in MB.

The cost model converts MB to TB-like units using:

$$
D_m(S_m)
=
\frac{S_m}{1024^2}
$$

where:

- $S_m$ is in MB.
- $D_m(S_m)$ is the disk quantity used for machine-capacity calculations.

The number of Caribou machines required is:

$$
N_m(S_m)
=
\begin{cases}
\frac{D_m(S_m)}{K}, & S_m > 0, \\
0, & S_m = 0.
\end{cases}
$$

The implementation does not round this value up; it allows fractional `machines_required`.

---

## 14. Per-Replica Cost

`compute_replicated_total_cost_model_b(...)` first splits traffic evenly across replicas.

Define per-replica traffic:

$$
T_m^{\rm rep}
=
\frac{T_m^{\rm in}}{R_m}
$$

The per-replica miss traffic is:

$$
M_m^{\rm rep}(S_m)
=
\mu_m(S_m)T_m^{\rm rep}
=
(1-h_m(S_m))\frac{T_m^{\rm in}}{R_m}
$$

The per-replica depreciation cost is:

$$
C_m^{\rm dep,rep}(S_m)
=
N_m(S_m)c^{\rm dep}
$$

The per-replica colocation cost is:

$$
C_m^{\rm colo,rep}(S_m)
=
N_m(S_m)c^{\rm colo}
$$

The per-replica midgress cost is:

$$
C_m^{\rm midg,rep}(S_m)
=
\rho_m M_m^{\rm rep}(S_m)
$$

The per-replica parent-service cost is:

$$
C_m^{\rm par,rep}(S_m)
=
c^{\rm par}
\frac{M_m^{\rm rep}(S_m)}{E_{\gamma,b}}
$$

The per-replica total is:

$$
C_m^{\rm rep}(S_m)
=
C_m^{\rm dep,rep}(S_m)
+
C_m^{\rm colo,rep}(S_m)
+
C_m^{\rm midg,rep}(S_m)
+
C_m^{\rm par,rep}(S_m)
$$

---

## 15. Replicated Total Cost

The implemented replicated cost is:

$$
C_m(S_m)
=
R_m C_m^{\rm rep}(S_m)
$$

Substituting the per-replica terms:

$$
C_m(S_m)
=
R_m
\left[
N_m(S_m)(c^{\rm dep}+c^{\rm colo})
+
\rho_m(1-h_m(S_m))\frac{T_m^{\rm in}}{R_m}
+
c^{\rm par}
\frac{(1-h_m(S_m))T_m^{\rm in}}{R_m E_{\gamma,b}}
\right]
$$

Equivalently:

$$
C_m(S_m)
=
R_m N_m(S_m)(c^{\rm dep}+c^{\rm colo})
+
\rho_m(1-h_m(S_m))T_m^{\rm in}
+
c^{\rm par}
\frac{(1-h_m(S_m))T_m^{\rm in}}{E_{\gamma,b}}
$$

This shows that:

- fixed disk and colocation costs scale with replication factor $R_m$;
- traffic costs are computed using split traffic and then multiplied by $R_m$, which algebraically cancels the traffic split.

---

## 16. No Explicit Egress Cost

The implemented cost model does not contain a separate egress cost.

There is no term:

$$
c_m^{\rm egress}T_m h_m(S_m)
$$

The only traffic-dependent costs are based on miss traffic:

$$
(1-h_m(S_m))T_m^{\rm in}
$$

These traffic-dependent costs are:

1. Midgress cost.
2. Parent-service cost.

Therefore, any mathematical formulation of this code should not include a separate egress-bandwidth cost.

---

## 17. Parent-Service Cost Interpretation

The implemented parent-service cost is not an inbound cost for traffic that metro $m$ serves as a parent for other metros.

Instead, for each metro $m$, parent-service cost is computed from $m$’s own miss traffic:

$$
(1-h_m(S_m))T_m^{\rm in}
$$

The parent-service machines required are:

$$
N_m^{\rm par}(S_m)
=
\frac{(1-h_m(S_m))T_m^{\rm in}}{E_{\gamma,b}}
$$

The parent-service cost is:

$$
C_m^{\rm par}(S_m)
=
c^{\rm par}
N_m^{\rm par}(S_m)
$$

Thus, the code does not implement:

$$
\sum_{u:(u,m)} Q_{u,m}(1-h_u(S_u))
$$

as a cost term for metro $m$.

---

## 18. Performance Model Overview

The performance model computes, for each client metro $u$, a traffic-weighted TTFB distribution over the serving metros $m \in \mathcal{B}_u$.

The resulting p50 and p95 values are penalized if they exceed target thresholds.

The performance model uses PDFs for:

1. Edge RTT from client metro $u$ to serving metro $m$.
2. Edge TAT at serving metro $m$.
3. Midgress RTT from serving metro $m$ to its assigned MCH parent.
4. Parent/MCH TAT at the MCH parent.

The PDFs are combined by convolution.

---

## 19. PDF Notation

Let $*$ denote convolution of probability density functions.

Let $Z(p,X)$ denote the zero-inflation operation implemented by `with_fraction_at(0,p)`:

$$
Z(p,X)
=
p\delta_0
+
(1-p)X
$$

where:

- $\delta_0$ is a point mass at zero milliseconds.
- $X$ is the original PDF.
- $p \in [0,1]$.

This corresponds to the code operation:

$$
\texttt{X.with\_fraction\_at(0,p)}
$$

---

## 20. Pairwise TTFB Distribution

For client metro $u$ and serving metro $m \in \mathcal{B}_u$, define:

- $R_{u,m}^{\rm edge}$ as the edge RTT PDF from client $u$ to serving metro $m$.
- $A_m^{\rm edge}$ as the edge TAT PDF for cache hits at serving metro $m$.
- $R_m^{\rm mch}$ as the midgress RTT PDF between serving metro $m$ and its assigned MCH parent.
- $A_m^{\rm mch}$ as the parent/MCH TAT PDF for that parent MCH.
- $h_m(S_m)$ as the hit-rate fraction at serving metro $m$.

The code constructs the pairwise TTFB PDF as:

$$
L_{u,m}(\mathbf{S})
=
R_{u,m}^{\rm edge}
*
Z(1-h_m(S_m), A_m^{\rm edge})
*
Z(h_m(S_m), R_m^{\rm mch})
*
Z(h_m(S_m), A_m^{\rm mch})
$$

This mirrors the implementation:

1. Edge TAT PDF gets mass $1-h_m(S_m)$ at zero.
2. MCH RTT PDF gets mass $h_m(S_m)$ at zero.
3. Parent/MCH TAT PDF gets mass $h_m(S_m)$ at zero.
4. The resulting PDFs are convolved.

This is a faithful description of the code. It should not be replaced by a simpler Bernoulli hit/miss branch unless the implementation is changed.

---

## 21. Client-Level TTFB Distribution

For each client metro $u$, the code computes a weighted mixture of pairwise TTFB PDFs over serving metros.

If at least one serving PDF exists and the total traffic weight is positive, define:

$$
L_u(\mathbf{S})
=
\frac{
\sum_{m \in \mathcal{B}_u} Q_{u,m} L_{u,m}(\mathbf{S})
}{
\sum_{m \in \mathcal{B}_u} Q_{u,m}
}
$$

The weights are:

$$
Q_{u,m}
=
\texttt{traffic\_lookup\_by\_airport[(u,m)]}
$$

This is implemented by:

$$
\texttt{weighted\_pdf\_sum(ttfb\_pdfs, weights)}
$$

If no valid PDFs exist or all weights are zero, the code returns:

$$
p50_u(\mathbf{S}) = 0
$$

and:

$$
p95_u(\mathbf{S}) = 0
$$

---

## 22. Percentile Extraction

The code converts each pairwise TTFB PDF to a microsecond-resolution PDF before combining:

$$
L_{u,m}
\mapsto
\texttt{L\_{u,m}.to\_microsecond\_pdf(step\_us=10)}
$$

Then it extracts percentiles from the combined PDF.

Let:

$$
p50_u(\mathbf{S})
=
\operatorname{Percentile}_{50}(L_u(\mathbf{S}))
$$

and:

$$
p95_u(\mathbf{S})
=
\operatorname{Percentile}_{95}(L_u(\mathbf{S}))
$$

The code divides the percentile output by $1000$ before returning, so the reported values are in milliseconds:

$$
p50_u(\mathbf{S})
=
\frac{
\texttt{combined\_pdf.millisecond\_at\_percentile(50)}
}{1000}
$$

$$
p95_u(\mathbf{S})
=
\frac{
\texttt{combined\_pdf.millisecond\_at\_percentile(95)}
}{1000}
$$

Despite the method name `millisecond_at_percentile`, after conversion to microsecond-resolution indices the division by $1000$ yields milliseconds.

---

## 23. Performance Thresholds

Each client metro $u$ has latency thresholds:

$$
\tau_u^{50}
$$

and:

$$
\tau_u^{95}
$$

The default thresholds are:

$$
(\tau_u^{50},\tau_u^{95}) = (24,105)
$$

For EMEA, the code applies overrides:

1. Country-level overrides first.
2. Region-level overrides second.
3. Defaults otherwise.

The configured EMEA region thresholds are:

$$
(\tau^{50},\tau^{95}) =
\begin{cases}
(24,105), & \text{Europe}, \\
(45,180), & \text{Middle East}, \\
(75,220), & \text{Africa}.
\end{cases}
$$

The configured country override is:

$$
(\tau^{50},\tau^{95}) = (35,200)
$$

for South Africa.

---

## 24. Performance Penalty

Define client traffic in Gbps:

$$
G_u
=
\frac{T_u^{\rm from}}{1000}
$$

The implemented penalty is:

$$
P_u(\mathbf{S})
=
2G_u
\left[
\max(p50_u(\mathbf{S})-\tau_u^{50},0)^2
+
\max(p95_u(\mathbf{S})-\tau_u^{95},0)
\right]
$$

Equivalently:

$$
P_u(\mathbf{S})
=
2G_u\max(p50_u(\mathbf{S})-\tau_u^{50},0)^2
+
2G_u\max(p95_u(\mathbf{S})-\tau_u^{95},0)
$$

The p50 excess is squared. The p95 excess is not squared.

---

## 25. Objective Function

The evaluated objective is:

$$
\operatorname{Objective}(\mathbf{S})
=
\sum_{m \in \mathcal{A}} C_m(S_m)
+
\sum_{u \in \mathcal{A}} P_u(\mathbf{S})
$$

Substituting the cost expression:

$$
\operatorname{Objective}(\mathbf{S})
=
\sum_{m \in \mathcal{A}}
\left[
R_m N_m(S_m)(c^{\rm dep}+c^{\rm colo})
+
\rho_m(1-h_m(S_m))T_m^{\rm in}
+
c^{\rm par}
\frac{(1-h_m(S_m))T_m^{\rm in}}{E_{\gamma,b}}
\right]
+
\sum_{u \in \mathcal{A}}
P_u(\mathbf{S})
$$

where:

$$
P_u(\mathbf{S})
=
2G_u
\left[
\max(p50_u(\mathbf{S})-\tau_u^{50},0)^2
+
\max(p95_u(\mathbf{S})-\tau_u^{95},0)
\right]
$$

---

## 26. Optimization Problem

The optimization problem represented by the evaluated objective is:

$$
\min_{\{S_m\}_{m \in \mathcal{A}}}
\quad
\sum_{m \in \mathcal{A}} C_m(S_m)
+
\sum_{u \in \mathcal{A}} P_u(\mathbf{S})
$$

subject to:

$$
S_m^{\min}
\le
S_m
\le
S_m^{\max}
\qquad
\forall m \in \mathcal{A}
$$

and with fixed replication factor:

$$
R_m =
\begin{cases}
5, & \text{if tier}(m)=0, \\
3, & \text{if tier}(m)=1, \\
2, & \text{otherwise.}
\end{cases}
$$

There is no constraint of the form:

$$
\sum_{m \in \mathcal{A}} S_m \le B
$$

in the evaluated objective.

The code does use an iteration-level update budget during the heuristic search, but that is part of the optimization algorithm, not a mathematical constraint on feasible solutions.

---

## 27. Initial State

The active optimization starts from a cost-optimal point for each metro.

For each metro $m$, the code searches over integer hit-rate targets:

$$
q \in \{1,2,\dots,100\}
$$

It maps each target hit rate to the nearest FD cache size:

$$
S_m(q)
=
\texttt{descriptor.nearest\_cache\_for\_hitrate(q)}
$$

and evaluates:

$$
C_m(S_m(q))
$$

The selected initial point is:

$$
S_m^{0}
=
S_m(q_m^\star)
$$

where:

$$
q_m^\star
\in
\arg\min_{q \in \{1,\dots,100\}}
C_m(S_m(q))
$$

This initialization is not itself the full cost-plus-performance optimum; it is only the starting point used by the search heuristic.

---

## 28. Algorithmic Update Budget

Although not part of the feasible set, the code uses an iteration-level update budget.

Let $g_m$ be the estimated objective change from increasing $S_m$ by a probe step.

At each iteration, define:

$$
n_-
=
|\{m \in \mathcal{A}: g_m < 0\}|
$$

The update budget in MB is:

$$
B^{\rm iter}
=
\max(n_-,1)
\cdot
10
\cdot
1{,}000{,}000
$$

This budget is distributed proportionally to absolute gradient magnitudes and rounded upward to the nearest TB-sized increment.

This should be interpreted as part of the search procedure, not as a global capacity constraint in the optimization formulation.

---

## 29. Important Modeling Limitations of the Implementation

The formulation above follows the implementation. Several behaviors are worth making explicit:

1. The hit-rate function is nearest-neighbor over a smoothed FD grid, not continuous interpolation.

2. The cost model treats machine counts as fractional:

$$
N_m(S_m)
=
\frac{S_m/1024^2}{35}
$$

rather than applying a ceiling.

3. There is no explicit egress cost.

4. Parent-service cost is based on the same miss traffic used for midgress cost:

$$
(1-h_m(S_m))T_m^{\rm in}
$$

5. Cost does not use the full traffic graph except through aggregate incoming traffic:

$$
T_m^{\rm in}
=
\sum_{u \in \mathcal{U}_m} Q_{u,m}
$$

6. Performance does use per-edge traffic weights $Q_{u,m}$ when combining TTFB PDFs.

7. The TTFB PDF construction is a convolution of zero-inflated components, not a separately enumerated hit/miss mixture.

8. The performance penalty is indexed naturally by client metro $u$, while the cost is indexed by serving metro $m$.

---

## 30. Symbol-to-Code Mapping

| Mathematical symbol   | Meaning                                              | Code variable or function                                                      | Notes                                                       |
| --------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| $\mathcal{M}$         | All metros in selected geo                           | `ALL_METROS`, `metros`, `airport_info.keys()`                                  | Populated by `parse_metro_areas(...)`                       |
| $\mathcal{A}$         | Active metros with FD and performance model          | `active_metros`                                                                | Metros in both `FDS_BY_METRO` and `PERFORMANCE_MODELS`      |
| $u$                   | Client, ASN, or end-user metro                       | `asn_metro`, `from_metro`, `metro` in `compute_performance_for_metro(...)`     | Converted to airport code                                   |
| $m$                   | Serving, bandwidth, or edge metro                    | `bw_metro`, `to_metro`, `candidate_metro`                                      | Converted to airport code                                   |
| $\theta$              | Traffic threshold                                    | `_TRAFFIC_THRESHOLD`                                                           | Command-line argument `--traffic-threshold`                 |
| $\mathcal{B}_u$       | Serving metros used by client metro $u$              | `neighborhood_to[u]`                                                           | Built from thresholded `traffic_lookup`                     |
| $\mathcal{U}_m$       | Client metros served by serving metro $m$            | `neighborhood_from[m]`                                                         | Built from thresholded `traffic_lookup`                     |
| $Q_{u,m}$             | Traffic from client $u$ to serving metro $m$ in Mbps | `traffic_lookup_by_airport[(u,m)]`                                             | Derived from `served_from_<bucket>.csv`                     |
| $T_m^{\rm in}$        | Aggregate incoming traffic at serving metro $m$      | `INCOMING_TRAFFIC[m]`                                                          | Used by cost                                                |
| $T_u^{\rm from}$      | Aggregate traffic originating from client metro $u$  | `TRAFFIC_FROM[u]`                                                              | Used by performance penalty                                 |
| $S_m$                 | Provisioned cache size in MB                         | `DISK_PROVISIONED[m]`                                                          | Optimization state                                          |
| $\mathbf{S}$          | Vector of all provisioned cache sizes                | `DISK_PROVISIONED`                                                             | Dictionary keyed by metro                                   |
| $S_m^{\min}$          | Minimum FD cache size for metro $m$                  | `min(point.cache_space for point in descriptor._points_sorted_by_cache)`       | Enforced during updates                                     |
| $S_m^{\max}$          | Maximum FD cache size for metro $m$                  | `max(point.cache_space for point in descriptor._points_sorted_by_cache)`       | Enforced during updates                                     |
| $\mathcal{F}_m$       | Smoothed FD points                                   | `FDS_BY_METRO[m]`                                                              | `FootprintDescriptor`                                       |
| $s_{m,k}$             | FD cache-size point in MB                            | `point.cache_space`                                                            | Integer MB value                                            |
| $r_{m,k}$             | FD hit-rate point in percent                         | `point.hitrate`                                                                | Percentage                                                  |
| $H_m(S_m)$            | Hit rate as percent                                  | `descriptor.hitrate_for_cache(disk)`                                           | Nearest-neighbor lookup                                     |
| $h_m(S_m)$            | Hit-rate fraction                                    | `TRY_HITRATES[m] / 100.0`                                                      | Used in cost and performance                                |
| $\mu_m(S_m)$          | Miss fraction                                        | `1.0 - hitrate_fraction`                                                       | Used in cost                                                |
| $R_m$                 | Replication factor                                   | `replication_factor_for_metro(...)`                                            | Fixed by metro tier                                         |
| $K$                   | Caribou disk capacity per machine                    | `CARIBOU_DISK_CAPACITY_TB`                                                     | 35 TB                                                       |
| $D_m(S_m)$            | Cache size converted from MB to TB-like units        | `total_disk_required_tb / 1024 / 1024`                                         | Argument name is misleading                                 |
| $N_m(S_m)$            | Machines required                                    | `machines_required`                                                            | Fractional                                                  |
| $c^{\rm dep}$         | Monthly depreciation per machine                     | `_monthly_depreciation_per_machine`                                            | Disk capex divided by depreciation months                   |
| $c^{\rm colo}$        | Monthly colocation per machine                       | `_monthly_kw_infra_cost_per_machine + _monthly_metered_power_cost_per_machine` | Power infrastructure plus metered power                     |
| $\rho_m$              | Midgress cost per Mbps-month                         | `midgress_cost_nonmch` or `MIDGRESS_COST_PER_Mbps_MONTH_MCH`                   | Depends on geo and whether metro has MCH                    |
| $E_{\gamma,b}$        | Effective capacity in Mbps                           | `effcap_mbps`, `get_effcap(geo, traffic_class)`                                | From `COST/effcaps.csv` or fallback                         |
| $c^{\rm par}$         | Monthly parent-service cost per machine              | `_monthly_parent_service_cost_per_machine`                                     | Parent capex divided by depreciation months                 |
| $C_m(S_m)$            | Monthly cost at metro $m$                            | `compute_replicated_total_cost_model_b(...)`                                   | Includes depreciation, colocation, midgress, parent service |
| $R_{u,m}^{\rm edge}$  | Edge RTT PDF                                         | `get_rtt_pdf(...)`, `set_edge_rtt(...)`                                        | From performance DB                                         |
| $A_m^{\rm edge}$      | Edge TAT PDF                                         | `get_edge_tat_pdf(...)`, `set_edge_tat_hit(...)`                               | Cache-hit edge TAT                                          |
| $R_m^{\rm mch}$       | Midgress/MCH RTT PDF                                 | `get_midgress_rtt_pdf(...)`, `set_mch_rtt(...)`                                | Between serving metro and assigned parent                   |
| $A_m^{\rm mch}$       | Parent/MCH TAT PDF                                   | `get_parent_tat_pdf(...)`, `set_mch_tat(...)`                                  | Final definition uses `cache_hit_type != 2`                 |
| $Z(p,X)$              | Zero-inflated PDF                                    | `X.with_fraction_at(0,p)`                                                      | Adds probability mass at zero                               |
| $L_{u,m}(\mathbf{S})$ | Pairwise TTFB PDF                                    | `performance_models[m].get_ttfb_pdf(from_metro=u, ...)`                        | Convolution of modified PDFs                                |
| $L_u(\mathbf{S})$     | Client-level weighted TTFB PDF                       | `weighted_pdf_sum(ttfb_pdfs, weights)`                                         | Weights are $Q_{u,m}$                                       |
| $p50_u(\mathbf{S})$   | 50th percentile TTFB                                 | `combined_pdf.millisecond_at_percentile(50) / 1000.0`                          | Returned in ms                                              |
| $p95_u(\mathbf{S})$   | 95th percentile TTFB                                 | `combined_pdf.millisecond_at_percentile(95) / 1000.0`                          | Returned in ms                                              |
| $\tau_u^{50}$         | p50 threshold                                        | `_DEFAULT_THRESHOLDS`, `_EMEA_REGION_THRESHOLDS`, `_EMEA_COUNTRY_THRESHOLDS`   | Depends on geo and EMEA mappings                            |
| $\tau_u^{95}$         | p95 threshold                                        | `_DEFAULT_THRESHOLDS`, `_EMEA_REGION_THRESHOLDS`, `_EMEA_COUNTRY_THRESHOLDS`   | Depends on geo and EMEA mappings                            |
| $G_u$                 | Client traffic in Gbps                               | `TRAFFIC_FROM[u] / 1000.0`                                                     | Used in penalty                                             |
| $P_u(\mathbf{S})$     | Performance penalty                                  | `penalty_function(...)`                                                        | p50 excess squared, p95 excess linear                       |
| Objective             | Total cost plus total penalty                        | `combined_total = total_cost + total_penalty`                                  | Logged each iteration                                       |
| Global disk budget    | None                                                 | No direct code equivalent                                                      | Only iteration-level update budget exists                   |

---

## 31. Final Correct Objective Statement

The optimization problem implemented by the evaluated state is:

$$
\boxed{
\min_{\{S_m\}_{m \in \mathcal{A}}}
\quad
\sum_{m \in \mathcal{A}}
\left[
R_m N_m(S_m)(c^{\rm dep}+c^{\rm colo})
+
\rho_m(1-h_m(S_m))T_m^{\rm in}
+
c^{\rm par}
\frac{(1-h_m(S_m))T_m^{\rm in}}{E_{\gamma,b}}
\right]
+
\sum_{u \in \mathcal{A}}
2G_u
\left[
\max(p50_u(\mathbf{S})-\tau_u^{50},0)^2
+
\max(p95_u(\mathbf{S})-\tau_u^{95},0)
\right]
}
$$

subject to:

$$
\boxed{
S_m^{\min}
\le
S_m
\le
S_m^{\max}
\qquad
\forall m \in \mathcal{A}
}
$$

with:

$$
\boxed{
h_m(S_m)
=
\frac{1}{100}
r_{m,k^\star(S_m)}
}
$$

where:

$$
\boxed{
k^\star(S_m)
\in
\arg\min_{k \in K_m}
|S_m-s_{m,k}|
}
$$

and with fixed replication factor:

$$
\boxed{
R_m =
\begin{cases}
5, & \text{if tier}(m)=0, \\
3, & \text{if tier}(m)=1, \\
2, & \text{otherwise.}
\end{cases}
}
$$

There is no explicit egress-cost term and no global disk-budget constraint in this formulation.