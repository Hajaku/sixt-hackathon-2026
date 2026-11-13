---
tags: [results, bounds, project-4]
---

# Value of Perfect Info

How much do our plans lose because the demand is unknown when the plan is fixed? Back to [[Overview]] · [[Experiments]] · [[M1 Full Fleet MIP]]

## Setup (2026-11-13, 16:26–16:35)
- **Sample:** 10 scenarios from `forecast.sample_demand`, seed 777. No plan was built on them: the SAA plans used seed 11, and the evaluation set is seed 2026.
- **Plans scored on it:** `final_point`, `final_saa_20` and `final_saa`, all L3 with the exact R7 greedy.
- **Hindsight solve:** the classic SAA (L3, upgrades, exact greedy) on exactly these 10 scenarios, with Gurobi, a 480 s limit, stopped at a 1.46 % gap.
  - That model is exact for the scorer on its scenarios: our scorer gives its plan 4,147,543, the same as the model's own value.
  - So the solve gives the best single plan for this sample (the incumbent) and a cap on it (the bound).
- **Code:** `scripts/insample_bound.py --seed 777 --n 10 --time-limit 480 final_point final_saa_20 final_saa`. Plan: `plans/insample_saa_seed777_n10.csv`.

## Results (mean profit over the 10 scenarios, paired SE)
| Plan | Profit | vs. hindsight SAA |
|---|---:|---:|
| Hindsight SAA, bound | ≤ 4,166,474 | |
| Hindsight SAA, incumbent | 4,147,543 | — |
| `final_point` | 4,130,592 | −16,951 (3,410) |
| `final_saa_20` | 4,123,846 | −23,697 (2,758) |
| `final_saa` | 4,120,303 | −27,239 (2,176) |

## Reading
- **This is not the textbook EVPI.** The hindsight SAA is one plan for all 10 scenarios. It measures the value of knowing the *sample*: an upper bound for any non-anticipative plan on it. The textbook EVPI uses wait-and-see, one plan per scenario, which gives an even higher bound. See below.
- **`final_point` is at most 36 k (0.9 %) from the best single plan with hindsight on this sample, and 17 k from the incumbent.** That is about the tie band of the final ranking (≈ 25 k). Little is left for any better here-and-now model to gain.
- **The ranking point > SAA-20 > SAA-10 holds on this independent sample too,** matching the 500-scenario evaluation.

## Wait-and-see (EVPI proper)
- **What it does:** `scripts/wait_and_see.py --seed 777 --n 10 --time-limit 45` solves L3 with the exact greedy once per scenario, scores each plan on its own scenario, and saves `plans/wait_and_see_seed777_n10.json`.
- **EVPI on the sample** = WS − 4,130,592 (`final_point`), or − 4,147,543 against the best single plan.
- **Run:** 16:35–16:43, 10 solves of 46 s each, gaps 1.6–3.3 % at the limit. Each plan's score on its own scenario equals its model value, so the model is exact.
- **Wait-and-see value:** WS ∈ [4,190,995, 4,221,009]. The lower end is the mean of the incumbents, the upper end the mean of Gurobi's bounds.
- **EVPI on the sample** (WS minus the best single plan, which lies in [4,147,543, 4,166,474]): **between 25 k and 73 k**, i.e. 0.6–1.8 %.
- **`final_point` vs. perfect information:** 60–90 k below WS, of which only 17–36 k is due to the plan itself; the rest is the price of not knowing the demand.
