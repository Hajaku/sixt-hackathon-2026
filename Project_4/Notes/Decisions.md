---
tags: [decisions, project-4]
---

# Decisions

Short dated entries: what we decided, why, and what we rejected. Newest at the bottom.
Back to [[Overview]] · [[Models]] · [[Experiments]]

## 2026-11-12: Open-source solver stack (PuLP + HiGHS)
- **Decision:** model in PuLP 4 and solve with HiGHS by default, with CBC as the fallback. The solver is a single switch.
- **Why:** the submission must run without a commercial license, since the judges may not have Gurobi and ours is an expiring academic one. HiGHS is typically much faster than CBC.
- **Rejected:** Gurobi as the default (license); Pyomo (heavier, and the starter is already in PuLP).
- **Escape hatch:** Gurobi only for a real performance bottleneck, and only after we agree. The model stays HiGHS-solvable.

## 2026-11-12: Code layout
- **Decision:** our own package `fleetopt/` plus thin `scripts/`; notebooks only for data exploration. `fleetkit/` stays untouched.
- **Why:** reproducible from one command, testable, easy to show in the submission.

## 2026-11-12: Level 0 rules as implemented
- **Decision:** we read R1–R4 as follows. All 10 rows of `check_values.csv` match, which confirms the reading.
  - Committed car-days count only `open` and `booked` rentals. Each one occupies its pickup station on the days $[\max(\text{pickup}, 1), \min(\text{return}, 14)]$.
  - A one-way car leaves the pickup station and joins the return station on **return + 1**. After day 14 nothing happens.
  - $f^0$ = idle cars + on-rent cars counted at the **pickup** station of their open rental (joined on `reservation_id`).
  - Plan effects: add/remove/transfer-out count from their date on. A transfer arrives on date + lead, or never if that is after day 14. It is in transit on days $d \dots d+\text{lead}-1$ (for holding cost).
- **Why:** this is the spec read literally, and it matches the check values.
- **Structure:** the plan-independent parts ($c$, $f^0$, one-way flows) are kept apart from the plan effects $\Delta$, with $f^{\text{plan}} = f^{\text{nothing}} + \Delta$. The MIP uses the first as parameters. `check_validity` re-checks any plan, the MIP's included, with code that is independent of the model's constraints.
- **Finding:** do-nothing is valid, with min slack 0 in every category, but only 18 of 560 cells have zero slack. Removable cars on day 1, i.e. the min of the slack over the remaining days, summed over stations: economy 270, compact 194, midsize 86, premium 484. The removal caps are 67 / 63 / 37 / 66, so the caps bind long before slack does.

## 2026-11-13: Demand to come: joint (L, ℓ), grouped by station type × category
- **Decision:** in route A of [[Project Plan]], estimate rental length L and lead time ℓ **jointly** (empirical $P(L\ge a, \ell\le b)$ per station type × category), not as a product of marginals. Scenarios sample (L, ℓ) pairs.
- **Why:** intuitively short rentals are booked more spontaneously, so independence is a real assumption. The joint estimate drops it at no cost: the sample is every pickup in the window, so there's no truncation bias.
- **What the data say:** practically independent. Spearman(L, ℓ) = −0.002 (n = 26,715), and the mean lead is ≈ 4.6 d for every L from 1 to 10. Per station type × category |ρ| ≤ 0.07; the largest is airport economy at −0.07, about 2.6 SE. **The station type does matter:** airport leads are ~0.7 d shorter. Weekday has almost no effect on lead or L.
- **Rejected:** a product of marginals (an assumption we don't need); a joint per station (fewer counts; maybe later as a check).

## 2026-11-13: One full MIP (M1), levels are its restrictions
- **Decision:** write the model once, fully, as [[M1 Full Fleet MIP]] — add/remove + driver/truck transfers on a time-space network + one-step upgrades + fare buckets — and obtain L1/L2 by fixing variables to zero. Three modeling choices to stay faithful to the scorer:
  - the greedy "own category first" of R7 is enforced exactly with one binary $\theta_{s,k,d}$ (560 total) instead of letting an LP second stage optimize the allocation;
  - non-concave bucket sets (downtown midsize) get prefix binaries so buckets fill in order;
  - transfers with $d+\ell>14$ are dropped (they only cost; and a transfer is no removal dodge, since in-transit cars keep paying holding).
- **Why:** the README says one model covers all levels; an exact match to the scorer means our objective equals the official profit given the forecast, so "beats on our scenarios" is meaningful. A smarter-than-scorer LP would silently overstate revenue.
- **Rejected:** separate small models per level (duplicated flow/validity code, version drift); SOS2 instead of prefix binaries (finer discretization needed to reproduce R8 exactly).

## 2026-11-13: R6 fix during implementation — starved binary, not an epigraph
- **Decision:** in `fleetopt/model_base.py` (M1), $a^{fr}_{s,k,d} = \max(0, u_s f - c)$ is enforced exactly with one binary $w_{s,k,d}$ per capacity cell; the M1 note is updated in place (no experiments ran against the wrong version).
- **Why:** the first draft had only the lower bounds $a^{fr} \ge u_s f - c,\ a^{fr} \ge 0$ and claimed maximality would tighten them — wrong: $a^{fr}$ then has no upper bound and the solver serves demand "out of thin air" (a mechanics test with 200 car-days/day at S05 served fully with zero fleet changes). The two-branch binary is honest in both directions: $w=0$ forces $a^{fr}=0$, $w=1$ forces $a^{fr}=u_s f - c \ge 0$.
- **Verified after the fix:** the same mechanics test now draws 3 truck transfers (one loaded with midsize cars serving compact demand — the scorer's upgrade rule working through our model) and a served ramp 52 → 200 over the lead times; plan VALID.

## 2026-11-13: Estimation uses the history only, with no future bookings
- **Decision:** the estimation and exploration of base revenue and demand (`notebooks/01_base_revenue`, `02_demand_distribution`, and later `fleetopt/forecast.py`) use only `completed` and `open` rentals. `booked` rentals (picked up on or after day 1) enter only as the committed car-days $c$ in the model (R1), never in an estimator.
- **Why:** they are future information about the horizon itself. Using them in an estimate mixes the forecast with the committed part we already condition on, and would skew things like the B–D relation.
- **Kept:** `open` rentals. They were picked up before day 1 and are part of the observed past demand; without them, cars on rent in the last ~10 days of the window would be truncated.
- **Removed from the demand notebook:** the outlook of demand to come vs. free capacity $u f - c$, and the comparison of today's book with the pseudo-snapshots (both used $c$, which includes the bookings). That comparison belongs to the model step.

## 2026-11-13: Base revenue is a fixed cell estimate
- **Decision:** the model uses $\hat r_{s,k}$ = Σ revenue / Σ car-days of the completed rentals per station × category as a fixed parameter (`fleetopt.forecast.base_revenue`, `method="cell"`). Details in [[Base Revenue]].
- **Why:** the relative SE is ≤ 1.8 %. Base shows no time shocks and no correlation with demand. R8 is linear in base, so the mean is all the expected-profit objective needs.
- **Rejected:**
  - The multiplicative fit $\alpha_s\beta_k$ as the default. It is within 1.6 % of every cell, so it gains nothing here; it stays available as `method="multiplicative"`.
  - Scenarios over base. With no dependence on demand there is no expected-value effect.
  - Adding `open` rentals to the estimate. They would add only 4 % more rentals, and they are more useful as an independent check (they price the same).

## 2026-11-13: Demand process: weekly Gamma shock per cell, pooled geometric lengths
- **Finding** (`notebooks/02_demand_distribution.ipynb` §3–4):
  - **Lengths:** one truncated geometric fits all groups ($q\approx0.70$, mean ≈ 3). χ² finds no difference across station type × category (p = 0.54).
  - **Independence:** length is independent of weekday, week, day volume, lead and the other rentals of the same day.
  - **Mean check:** given that, $M_t/G/\infty$ reproduces mean cars on rent within 0.5 %.
- **The earlier "close to Poisson" was wrong.** Against a simulated Poisson null, pickups and cars on rent are clearly overdispersed (p < 1/200).
  - **Source:** one multiplicative shock per (station, category, calendar week). Evidence: $\phi_{\text{week}}/\phi_{\text{day}}\approx5.8$; daily residuals correlate within a week but not Sun → Mon.
  - **No carry-over:** the level of one week does not predict the next.
  - **Not shared:** no correlation across stations or categories.
  - **Size:** $\mathrm{Var}[G]\approx0.017$.
- **Decision:**
  - **Generator:** $P_{s,k,d}\sim\mathrm{Poisson}(G_{s,k,w(d)}\,\lambda_{s,k,\mathrm{wd}(d)})$ with $G\sim\Gamma$(mean 1, var 0.017), i.i.d. per cell and calendar week, plus pooled geometric lengths.
  - **Expected demand:** plain 8-week weekday means, not recent weeks.
  - **The downtown-economy "trend"** is these shocks, not a trend.
- **Rejected:**
  - Pure Poisson: it understates a cell's variance by $1+v\mu$ (×1.9 at μ = 50), and with it the concavity of the revenue curves.
  - i.i.d. daily NegBin: wrong persistence; T is more overdispersed than P.
  - Weighting recent weeks: worse out of sample.
- **Open:** the committed book correlates with demand to come (+0.17). That fits the week-1 shock, so updating $G_{s,k,1}$ from $c$ could sharpen the week-1 forecast. Worth checking in `forecast.py`.

## 2026-11-13: Bookings: allowed for conditioning, not in history estimates (clarifies the entry above)
- **Rule:**
  - **Excluded:** future bookings (`booked`) never enter the history-based estimates: base revenue, pickup rates $\lambda$, the length and lead distributions, and the shock variance $v$.
  - **Allowed:** they may be used to condition the forecast on what is known at day 1. That means the committed car-days $c$ (R1), and the week-1 update $E[G_{s,k,1}\mid n_B]$ in [[Demand]].
- **Why:** the estimates should describe the demand process from the history alone. Conditioning on information we hold at decision time is legitimate forecasting, not leakage.
- **Supersedes** the wording "never in an estimator" in the entry "Estimation uses the history only" above. The notebooks are unchanged: they only estimate.
