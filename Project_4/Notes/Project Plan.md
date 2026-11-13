---
tags: [plan, project-4]
date: 2026-11-13
status: agreed
---

# Project Plan

Plan for hackathon day (Fri 13 Nov, deadline **16:45**).
Back to [[Overview]] · [[Project Description]] · [[Models]] · [[Experiments]] · [[Decisions]] · [[Final Checklist]]

## Goal
A **valid** `final.csv` with high **mean profit over 30 hidden demand scenarios** (60 %), plus a model we can explain (40 %). Validity first, then expected profit. Don't fit to the single public scenario.

## Data findings (2026-11-12, quick look)
- **Base revenue per car-day** is flat in rental length (≈ 348 in every length band) and pickup weekday (344–354). It varies strongly by station × category and looks multiplicative (S05 is about 40 % below S03 in every category). Per-rental std is about 20 %. Booked and open rentals match the completed ones.
- **Censored history:**
  - *Right:* "completed" = returned before day 1, so the last week shows 2,235 pickups vs. about 3,350. Add the **open** rentals back.
  - *Left:* history starts 2027-01-04 and rentals last ≤ 10 days, so occupancy in the first ~9 days is too low.
- **Lead times:** median 3 d, 90 % ≤ 11 d, 99 % ≤ 24 d. Rental length: median 2 d, max 10 d.
- **Demand to come is always a round trip.** About 10 % of booked and open rentals are one-way.
- **Non-concave price factors (the Level 4 trap):** downtown midsize 1.056 → **0.99** → 1.016 at 70 / 80 / 90 %. Marginal revenue per bucket ≈ 1.08, 0.91, **0.53, 1.22**, 0.86 × base. An LP that fills buckets in any order overstates revenue there.
- Weekly volume is flat, with no obvious trend. Weekday seasonality is still to check.

## How the price factors work
- We **don't set prices**. The scorer models scarcity pricing: $q$ = served / demand, *not* fleet utilization.
- Few cars relative to demand ⇒ $q<1$ ⇒ only the higher-paying customers are served ⇒ average price factor > 1. That's the same as "booked out ⇒ raise the price".
- Our only lever is the fleet, which sets $q$.
- **Consequence:** the marginal car-day earns *less* than base (e.g. airport economy, last 10 % bucket ≈ 0.89 × base). The last cars must clear holding + addition cost at that marginal rate.

## Decisions

### 1. Base revenue: a point estimate
- **Why it's directly observable:**
  - README l. 36 defines base as the revenue per car-day "if the company serves all demand".
  - Appendix B l. 282: the history shows demand at the base price, with no demand lost.
  - With R8, $q=1 \Rightarrow$ price factor 1, so historical revenue / car-days = base.
- **Estimator:** car-day-weighted Σ revenue / Σ car-days per (s, k). Network-wide: economy 254, compact 315, midsize 404, premium 562. Optionally shrink with a multiplicative station × category fit.
- **Why no stochastic treatment:** revenue is linear in base, so if base ⟂ D the mean is exactly what the expected-profit objective needs. Base is drawn per hidden scenario (l. 233); the history gives its mean.
- [ ] Check corr(base, daily demand) in the notebook.

### 2. Demand to come $E[N^d]$: two routes, cross-checked
$N^d$ = car-days on day d from rentals booked on or after day 1. $B^d$ = committed.

**Why not "mean − committed":** $E[T]-B^d$ is only right if B and N are uncorrelated. Rough check: residual corr(B, N) ≈ **+0.24** (stations, 7-day cutoff, n = 450). So the naive estimate moves the wrong way: high B ⇒ it predicts less to come, while the data suggest more.

**A. Model-based**
- **Assumptions:** pickups arrive at rate λ(s, k, weekday). Rental length L (car-days, both ends counted) and lead ℓ = pickup − booking have a **joint** distribution per station type × category. We don't assume L ⟂ ℓ.
- A pickup on horizon day p counts for $N^d$ if $L \ge d-p+1$ and $\ell \le p-1$. Pickups before day 1 are all committed.
$$E[N^d]=\sum_{p=1}^{d}\lambda(s,k,\mathrm{wd}(p))\;P\big(L\ge d-p+1,\ \ell\le p-1 \,\big|\, \text{type}(s),k\big)$$
- **λ:** mean daily pickups per (s, k, weekday) from completed **plus open** rentals. Together they hold every pickup in the window.
- **Joint P(L ≥ a, ℓ ≤ b):** the empirical fraction of historical rentals with L ≥ a and ℓ ≤ b, per station type × category (n ≈ 1,100–7,300 per group). There's no truncation bias: the sample is every pickup in the 8-week window, whatever its L or ℓ, since open rentals are added back. For scenarios, sample (L, ℓ) **pairs** from the same group.
- **Check (2026-11-13, see [[Decisions]]):** in this data, L and ℓ are practically independent (Spearman −0.002 overall; the joint/product ratio of the probabilities above is within 1 %). What does matter is the **station type**: mean lead is 3.9–4.2 d at airports vs. 4.6–4.9 d downtown. So the grouping matters more than the joint estimate. We keep the joint one anyway, because it costs nothing and needs no assumption. Recheck per station if the counts allow.
- **Scenarios:** Poisson or NegBin pickups, then sample one (L, ℓ) pair for each from the joint empirical distribution of its group. This is the generator for the expected-revenue curves and for our own scorer.

**B. Empirical pseudo-snapshots**
- Choose dates $t_0'$ in the history with ≥ 10 days of buffer before and 14 after.
- For each $t_0'$ and d = 1…14: $N^d$ = cars on rent on $t_0'+d-1$ from rentals booked on or after $t_0'$. Average per (s, k, target weekday, d).
- No independence assumptions, but noisy: about 4–5 snapshots per weekday alignment.
- The same data give β per lead band in $E[N\mid B]=E[N]+\beta\,(B-E[B])$, which shows whether a conditional adjustment is needed.

**Combine**
- If A ≈ B, use A: it's smooth, generalizes and gives scenarios.
- If they diverge systematically, A's independence assumptions are wrong, and B shows where (e.g. lead depends on length).
- After the first upload: check the public `.result.md` new revenue (one draw) against A's predictive distribution. Far outside it is a red flag.
- If even A isn't parametric enough (overdispersion, station effects), fall back to bootstrapping historical weeks.

### 3. Stochastic programming via expected-revenue curves
- **Per-cell revenue:** ignoring upgrades, it's $R(\min(D,a))$ with $a=uf-c$. For concave $R$ this is concave in $a$, and so is its expectation.
- **Precompute** $\bar R_{s,k,d}(f)$ on the integer fleet grid by averaging over N = 200+ scenarios, and use it as a concave piecewise-linear objective. That's **exact SAA at deterministic model size**, and the $\max(0,\cdot)$ is built in.
- **Non-concave cells** (downtown midsize, about 8 stations × 14 days): an incremental / binary formulation on the integer grid.
- **Upgrades** couple categories, so the curves are only approximate there. Refinement: a full SAA with explicit upgrade flows over about 20–30 scenarios, *or* an upgrade-aware LP on expected demand. Our scorer decides.

### 4. The IP (first stage, integer)
- **Variables:**
  - fleet $f_{s,k,d}$
  - add / remove $x^{\pm}_{s,k,d}$
  - transfers $y^{\text{drv}}_{s,t,k,d}$, $y^{\text{trk}}_{s,t,k,d}$
  - trucks $z_{s,t,d} \ge \tfrac18\sum_k y^{\text{trk}}_{s,t,k,d}$
- **Constraints:** flow conservation with lead times and one-way flows (R3/R4); $f\ge c$; caps.
- **Objective:** $\sum \bar R(f)$ − holding (including in transit) − addition − transfer cost.
- **Pitfalls:**
  - There's no terminal value, so expect late removals.
  - The scorer serves greedily (own category first, then one step up), so our upgrade model must not be smarter than the scorer.
- **Prune transfer arcs:** the towns are about 80–250 km apart. Maybe drivers within a town and trucks between towns.

### 5. Easy to forget
- [x] **Level 0** matches `check_values.csv`. Validity depends on it. (`fleetopt/level0.py`, 10/10 rows)
- [ ] **Our own scorer** `fleetopt/evaluate.py`: R1–R11 exactly (greedy upgrades, truck `ceil`), run on 100+ sampled scenarios. That's how we compare models, since the leaderboard has one scenario.
- [ ] **Upload do-nothing + baseline early.** Their `.result.md` sanity-checks the forecast and our scorer.

## Timeline and roles
| Time (relative) | Person A: data & forecast | Person B: model | Claude: engineering |
|---|---|---|---|
| 0:00–1:00 | Level 0 → match check_values; base-revenue table | Write out the formulation (Models note M1) | `fleetopt/` skeleton, solver switch; upload do-nothing + baseline |
| 1:00–2:00 | Demand notebook: weekday/station patterns, overdispersion, L and ℓ distributions | **M1**: L1 add/remove with curves on a naive forecast → submit v1 | `evaluate.py` + validity check; test vs. public result |
| 2:00–3:00 | Route A (formula + generator) and route B (snapshots, β); compare | **M2**: L2/L3 transfers, trucks, upgrades | Evaluate on our scenarios; log [[Experiments]] |
| 3:00–4:00 | Forecast vs. public result | **M3**: SAA curves + non-concave cells; maybe explicit-upgrade SAA | Out-of-sample comparison; robustness |
| 4:00–4:15 | **Freeze `final.csv`** (best mean on our scenarios, valid in feedback) | | Validity double-check, `plans/final.csv` |
| 4:15–end | `SUBMISSION.md`, slides / demo | | Reproducible run command, push reminder |

**Rule:** a valid plan stays uploaded at all times. A new version is only promoted if it beats the previous one on our scenario set.

## Milestones
- [x] Level 0 matches check_values
- [ ] do-nothing + baseline uploaded, reference profits noted in [[Experiments]]
- [ ] base-revenue table
- [ ] own scorer agrees with the public `.result.md`
- [ ] M1 valid and above baseline
- [ ] demand routes A and B compared
- [ ] M2 (transfers, trucks, upgrades)
- [ ] M3 (SAA curves, non-concave cells)
- [ ] `final.csv` frozen and uploaded
