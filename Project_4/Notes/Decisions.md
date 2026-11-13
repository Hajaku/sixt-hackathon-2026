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
