# Submission: Project 4, Fleet Allocation Challenge

## Authors
**Team:** Dr. Lukas Brandl, Dr. Leander Schnaars

**Project:** Project 4: Fleet Allocation Challenge

**Final plan:** `plans/final.csv` (copy of `plans/final_point.csv`). It is a Level 3 plan with car removals, driver and truck transfers, and upgrades.

## Problem and approach
For each station, category and day of the 14-day horizon, we plan additions, removals and transfers (by driver or by truck) so that the plan is valid and maximizes expected profit over the hidden demand scenarios.

In short:
1. Estimate the base revenue and the demand distribution from the 8 weeks of history. Use the bookings that already exist only to condition the forecast (see [Forecast](#forecast-base-revenue-and-demand)).
2. Solve one MIP that reproduces the scorer's rules R1–R11 exactly, for a given set of demand scenarios. This is a sample-average approximation (SAA).
3. Score every plan with our own copy of the scorer on 500 fresh scenarios, and pick the plan with the best mean.

## The model: SAA over demand scenarios
**Notation.** $s$ is a station, $k \in \{1,\dots,4\}$ a category (economy < compact < midsize < premium), $d \in \{1,\dots,14\}$ a day, and $\omega \in \Omega$ a demand scenario with weight $1/|\Omega|$.
- Level 0 data: committed car-days $c_{skd}$, initial fleet $f^0_{sk}$, one-way arrivals and departures $o^\pm_{skd}$.
- Forecast: demand to come $D^\omega_{skd}$ and base revenue $\hat r_{sk}$.
- Parameters: maximum utilization $u_s$, holding cost $h_k$, addition cost $a_k$, caps $\bar A_k, \bar R_k$, lead times $\ell_{st}$, and transfer costs for drivers (per car) and trucks (per truck, 8 places).

**First stage (the plan, one for all scenarios).**
- $x^\pm_{skd} \in \mathbb{Z}_{\ge 0}$: cars added or removed.
- $y^{m}_{stkd} \in \mathbb{Z}_{\ge 0}$: cars transferred from $s$ to $t$ by mode $m \in \{\text{drv},\text{trk}\}$.
- $z_{std} \in \mathbb{Z}_{\ge 0}$: trucks used.
- Fleet $f_{skd}$ and free capacity $a_{skd}$.

$$
\begin{aligned}
f_{skd} &= f_{sk,d-1} + o^+_{skd} - o^-_{skd} + x^+_{skd} - x^-_{skd} - \textstyle\sum_{t,m} y^m_{stkd} + \sum_{t,m} y^m_{tsk,\,d-\ell_{ts}} && \text{(R3, R4: time-space flow)}\\
f_{skd} &\ge c_{skd}, \qquad \textstyle\sum_{s,d} x^+_{skd} \le \bar A_k, \qquad \sum_{s,d} x^-_{skd} \le \bar R_k && \text{(R5: validity)}\\
a_{skd} &= \max(0,\; u_s f_{skd} - c_{skd}) && \text{(R6, exact via one binary } w_{skd})\\
8\, z_{std} &\ge \textstyle\sum_k y^{\text{trk}}_{stkd} && \text{(R10: trucks)}
\end{aligned}
$$

**Second stage (serving, one block per scenario $\omega$).**
- $p^\omega_{skd}$: demand of category $k$ served by category-$k$ cars.
- $q^\omega_{skd}$: demand of category $k$ served by category-$(k{+}1)$ cars (a one-step upgrade).

$$
\begin{aligned}
p^\omega_{skd} + q^\omega_{s,k-1,d} &\le a_{skd}, \qquad q^\omega_{skd} \le D^\omega_{skd} - p^\omega_{skd} && \text{(R7: capacity, upgrades)}\\
p^\omega_{skd} &\ge D^\omega_{skd}\,\theta^\omega_{skd}, \qquad p^\omega_{skd} \ge a_{skd} - M_{skd}\,\theta^\omega_{skd}, \quad \theta^\omega_{skd}\in\{0,1\} && \text{(R7: own category first, exact)}\\
\textstyle\sum_b \sigma^\omega_{skdb} &= p^\omega_{skd} + q^\omega_{skd}, \qquad 0 \le \sigma^\omega_{skdb} \le \beta^\omega_{skdb} && \text{(R8: fare buckets)}
\end{aligned}
$$

**Objective (R11).** The committed revenue (R9) is a constant.

$$
\max\; \frac{1}{|\Omega|}\sum_{\omega}\sum_{s,k,d,b} \mu^\omega_{skdb}\,\sigma^\omega_{skdb}
\;-\; \sum_k h_k\Big(\sum_{s,d} f_{skd} + \text{cars in transit}\Big)
\;-\; \sum a_k x^+
\;-\; \text{driver cost} \;-\; \text{truck cost}
$$

**The point forecast is the special case $|\Omega| = 1$** with $D^1 = E[D]$. Our final plan uses exactly this case (see [Results](#results)).

**Levels are restrictions of the same model.** Level 1 sets $y = 0$, Level 2 allows drivers only, and Level 3 is the full model.

**Fare buckets via marginals (R8, Appendix C).** For each cell and scenario, the price factors give 5 buckets: size $\beta_b$ and marginal revenue $\mu_b = \hat r_{sk}\cdot\Delta(\text{revenue})/\Delta(\text{car-days})$. Where the marginals fall, the LP fills the buckets in the right order. In the few cells where they rise (downtown midsize), prefix binaries force the buckets to fill in order. With this, the bucket revenue equals R8 exactly.

**R7 made a big difference.** The scorer serves a category's own demand first and upgrades only from what is left over. Without $\theta$, the LP splits upgrades more cleverly than the scorer would, so it plans for revenue the scorer never pays out. Modelling the greedy rule exactly with $\theta$ was worth about **+100 k** (point: 3,985,938 → 4,108,409). That is more than every change to the revenue model put together.

Code: `fleetopt/model_base.py` (`build_model`, `solve_plan`). Full write-up: `Notes/Models/M1 Full Fleet MIP.md`.

## Forecast: base revenue and demand
All estimates come from the 8 history weeks (Mon 2027-01-04 to Sun 2027-02-28). Future bookings never enter these estimates; they only condition the forecast. Code: `fleetopt/forecast.py`; exploration: `notebooks/`; findings: `Notes/Base Revenue.md`, `Notes/Demand.md`.

### Base revenue
- History rentals are priced at the base price (price factor 1 at $q = 1$). So revenue per car-day is a direct draw of base revenue.
- We use the car-day-weighted ratio estimator $\hat r_{sk} = \sum R_i / \sum L_i$ per station × category, from 25,674 completed rentals.
- What we checked:
  - Relative SE is 0.5–1.8 % per cell.
  - The base is multiplicative, $r_{sk} = \alpha_s \beta_k$, to within 1.6 % in every cell, so there is no interaction.
  - It doesn't depend on rental length, weekday, lead time or week.
  - There is no time shock, and no correlation with demand (+0.04 weekly).
- R8 is linear in base and base is independent of demand, so a point estimate is enough.

### Demand
- **Weekday pattern** by station type: downtown peaks Fri–Sun; airports peak Mon and Thu.
- **Rental length:** one geometric distribution truncated at 10 days ($q \approx 0.70$, mean ≈ 3 car-days), the same for all categories and station types (χ² p = 0.54 across the 8 type × category groups).
- **Lead time:** about 80 % of rentals are booked at most 7 days ahead (airports later than downtown).
- Length is independent of lead time, weekday and how busy the day is. So by Poisson thinning, cars on rent are Poisson *if* pickups are.
- **Pickups are not Poisson.** Var/mean is far outside a Poisson null from 200 simulated histories (pooled excess 0.34, null 95 % ≤ 0.08). The excess persists within a calendar week (Mon–Sun) and disappears from Sunday to Monday. It doesn't carry over to the next week and isn't shared across cells.
- **Model: Gamma–Poisson.** Pickups are $\text{Poisson}(G_{skw}\,\lambda_{sk,\text{weekday}})$, with one shock per cell and week, $G \sim \Gamma(1/v, 1/v)$. The method of moments on weekly totals gives $\hat v = 0.017$ (SE 0.003), about ±13 % per week. Marginally, a week's pickups are negative binomial.
- **Booking update:** by Gamma–Poisson conjugacy, each horizon week's $G$ is updated with that week's existing bookings. In a backtest on pseudo-snapshots (every history Monday as day 1), this lowers the MSE of demand to come by 28 % (week 1) and 21 % (week 2).
- **Output:** $E[D_{skd}]$ for the point model, and seeded scenarios (`forecast.sample_demand`) for SAA and scoring. Two independent routes agree: the convolution and the pseudo-snapshots match to within 0.3 %, with correlation 0.998 per cell-day.

## Our own scorer
`fleetopt/evaluate.py` re-implements Appendix A:
- the validity check (R5), independent of the model;
- the profit rules R6–R11, for a plan and a demand scenario.

Plans are scored on the same 500 scenarios (seed 2026) and are never evaluated on their own SAA scenarios, so differences between plans come with a paired SE. On the public feedback scenario in the shared folder, our scorer matches the official `.result.md` well: **TODO: our vs. official profit for one plan**. Level 0 (`fleetopt/level0.py`) matches all 10 rows of `check_values.csv`.

## Results
All plans are Level 3 and valid by our check. Profit is the mean over 500 evaluation scenarios (SE ≈ 3.1 k per plan; paired SEs between plans are 0.3–0.8 k).

| Plan | Objective | Solver, time, gap | Profit | vs. final (paired SE) |
|---|---|---|---:|---:|
| Upper bound (hindsight, other sample) | SAA solved on exactly 10 test scenarios (seed 777), exact R7 | Gurobi, 480 s, 1.46 % | on those 10: incumbent 4,147,543, bound ≤ 4,166,474; `final_point` 4,130,592 | `final_point` −16,951 (SE 3,410) to the incumbent, ≤ −35,882 to the bound |
| **`final_point` (submitted)** | SAA with $\lvert\Omega\rvert = 1$, $D = E[D]$, exact R7 | Gurobi, 300 s, 0.60 % | **4,108,409** | — |
| `final_saa_20` | SAA, 20 scenarios, exact R7 | Gurobi, 900 s, 3.73 % | 4,098,427 | −9,982 |
| `final_saa` | SAA, 10 scenarios, exact R7 | Gurobi, 300 s, 3.42 % | 4,095,776 | −12,633 |
| `final_curves` | revenue curves (500 scenarios), exact R7 | Gurobi, 900 s, 0.51 % | 4,060,965 | −47,444 |
| `cmp_L3_curves_up_more` | revenue curves, no exact R7 | Gurobi, 437 s, 0.43 % | 4,011,116 | −97,293 |
| `cmp_L3_point` | point, no exact R7 | Gurobi, 159 s, 0.48 % | 3,985,938 | −122,471 |
| `cmp_L1_saa_boot_gurobi` | SAA at **Level 1** (no transfers) | Gurobi, 0.43 % | 3,420,297 | −688,112 |
| baseline | fleetkit rule | — | 3,118,529 | −989,880 |
| do-nothing | — | — | 3,021,476 | −1,086,933 |

**Official result for `final.csv`:** TODO (profit, breakdown, valid?) from `.result.md`.

The final plan adds no cars, removes 233 (the removal caps bind), and transfers 898: 13 by driver and 885 by truck.

**What we learned:**
- **Transfers matter most:** Level 3 is worth about +590 k over Level 1.
- **The exact R7 greedy comes next,** at about +100 k.
- **The point estimate beat SAA**, to our surprise, by 10 k (paired SE ≈ 0.7 k). The SAA runs didn't converge (3.4–3.7 % gap at the time limit), and 10–20 scenarios are a noisy sample of the weekly shocks. Our guess is that both matter.
- **Revenue curves did worse.** These replace the buckets with the expected revenue $\bar R_{skd}(a) = \frac1N\sum_\omega \mathrm{rev}(\min(D^\omega, a), D^\omega)$ as a concave piecewise-linear function of capacity, from 500 scenarios. Without upgrades this is the exact SAA, and it adds no binaries. With upgrades, though, the split has to be fixed ex ante. Together with the exact greedy, the threshold is too pessimistic, and the model keeps extra cars instead of upgrading.

## Limits
- **One history, no test set.** We have 8 weeks of history and one public scenario. A proper train/validation split, e.g. estimating on 6 weeks and testing on 2, would have shown how far our scorer's scenarios are from the hidden ones. Our evaluation uses our own demand model, so any error in that model also biases the comparison of plans.
- **SAA doesn't converge** in the available time, so we can't separate "SAA is worse" from "the solver didn't finish".
- **Static plan:** the whole 14 days are fixed at day 1, with no recourse.
- Transfers that end after day 14 are ignored (they never pay off), and upgrades are one step only, as in the rules.

## How to run
Python 3.14+, from a fresh clone:

```bash
cd Project_4
python3 -m venv .venv            # or: uv venv --python 3.14 .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/                        # Level 0 vs. check_values.csv, validity, model checks
.venv/bin/python scripts/run_level0.py plans/final.csv   # Level 0 check + validity of the final plan
.venv/bin/python scripts/make_final.py --objective point # regenerates plans/final.csv, checks and scores it
.venv/bin/python scripts/score_plans.py plans/do_nothing.csv plans/final.csv --scenarios 500
```

- Data is read from `Project_4/data/`. No environment variables or secrets are needed.
- `make_final.py --objective saa --saa-scenarios 20` gives the SAA plan.
- `scripts/compare_objectives.py` reruns the whole comparison.

**Gurobi caveat.** Our plans were solved with Gurobi 13 (academic license), because it closes the Level 3 gaps much faster. `make_final.py` asks for Gurobi first and **falls back to HiGHS** (open source, the default in `requirements.txt`) when gurobipy or a license is missing; `--solver highs` forces HiGHS. The model is plain PuLP and solver-independent. With HiGHS, the same time limit gives a larger gap, so the regenerated plan can differ slightly from `final.csv`. **TODO: HiGHS result for the point model.** gurobipy is deliberately not in `requirements.txt`.

## Demo
`submission/slides.pdf`: 5 slides (approach, forecast, model, results, limits and next steps). Source: `submission/slides.tex`, built with `latexmk -pdf slides.tex`.

## Next steps
- **Dynamic plans:** re-solve daily as bookings arrive (rolling horizon), using the booking update we already have.
- **Larger models:** more SAA scenarios with a decomposition (Benders or progressive hedging over scenarios), so SAA converges and the point-vs-SAA question gets a clean answer.
- **Train/test discipline:** hold out history weeks, and calibrate the scenario generator on held-out weeks.
- **Exact upgrades under uncertainty:** combine the exact R7 greedy with revenue curves.
- **For SIXT:** the model is a weekly fleet-balancing tool. It says where to move cars by truck and which cars to defleet, with an explainable profit breakdown per station.
