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
