---
tags: [model, project-4]
model: M2
level: L1–L3 (same restrictions as M1)
based_on: "[[M1 Full Fleet MIP]]"
status: tested (best so far: curves_up_more L3, 4,011,116)
code: fleetopt/fares.py, fleetopt/model_base.py (buckets=, upgrades=), scripts/compare_objectives.py
created: 2026-11-13
---

# M2 Expected-revenue curves

[[M1 Full Fleet MIP]] with a different revenue term. M1 prices the fare buckets at the *point* forecast $E[D]$. M2 uses the **expected revenue over demand scenarios** as a function of the free capacity.
Back to [[Models]] · [[Experiments]] · [[Project Plan]] §3 · [[Demand]]

## Idea and changes vs. based_on
- **Revenue term.** M1 uses $\mathrm{rev}(\text{served};\,E[D])$ with served $\le E[D]$. M2 uses, per cell,
  $$\bar R_{s,k,d}(a)=\frac1N\sum_{\omega}\mathrm{rev}\big(\min(D_{s,k,d}^{\omega},a),\,D^{\omega}_{s,k,d}\big),$$
  where $\mathrm{rev}$ is R8 exactly (the scorer's `fare_revenue`) and the $D^\omega$ come from `forecast.sample_demand` (weekly Gamma shock, booking update).
  - **Why:** the plan is fixed before the horizon (no recourse) and the objective is separable over cell-days, so $E[\text{profit}]$ needs only the marginal distribution of each $D_{s,k,d}$. $\bar R$ is the exact SAA of the revenue term when there are no upgrades.
- **As buckets.** $\bar R$ is evaluated on an integer capacity grid with ≤ 20 segments per cell, step $\lceil \max_\omega D^\omega / 20\rceil$. It becomes buckets of size step and marginal $\Delta\bar R/\text{step}$, in the same format as `demand_buckets`, so the MIP is unchanged.
  - The most the buckets can absorb ($\max_\omega D^\omega$) replaces $E[D]$ as the bound on served demand.
- **Concavity for free.** Averaging over scenarios smooths the non-concave price factors (downtown midsize). Only 7 of 560 cells keep a rise in the marginal, of at most €0.31 per car-day, so we treat them as concave (tolerance €1).
  - M1 needs prefix binaries in 112 non-concave cells; M2 needs none.
- **Two variants:**
  - **`curves`:** `upgrades=False`, no upgrade variables. The scorer still upgrades when it evaluates the plan.
  - **`curves_up`:** M1's upgrade variables $q$ stay. Capacity of category $k+1$ can be assigned to category $k$'s curve. This is a *deterministic* split decided ex ante; the scorer serves own demand first in each scenario. So it approximates upgrades under uncertainty, without being exact.

## Simplifications / assumptions
- Curves come from $N=300$ scenarios (seed 11). Plans are evaluated on different scenarios (500, seed 2026).
- Piecewise-linear interpolation of $\bar R$ between grid points. $\bar R$ is concave, so this slightly *under*states revenue.
- Base revenue fixed at the cell estimate ([[Base Revenue]]).
- Upgrades: none (`curves`) or a deterministic split (`curves_up`). An exact treatment would need SAA with per-scenario serving variables.

## Variables / constraints
As [[M1 Full Fleet MIP]]; only the bucket table (sizes, marginals, concave flags) and the bound on served demand change. `curves` drops $q$.

## Objective
$$\max\ \sum_{s,k,d}\bar R_{s,k,d}\big(\text{served}_{s,k,d}\big)\;-\;\text{holding}\;-\;\text{addition}\;-\;\text{transfer cost},\qquad \text{served}_{s,k,d}=p_{s,k,d}+q_{s,k,d}$$

## Size and solve
- **L1** (HiGHS, gap 1 %): `buckets` 19 s, `curves` 2 s, `curves_up` 26 s, all optimal.
- **L3** (time limit 300 s): `buckets` hit the time limit, `curves` optimal in 223 s, `curves_up` hit the time limit. The final MIP gaps were not recorded; rerun with a log before trusting differences below ~1 %.

## Results (500 evaluation scenarios, paired SE; see [[Experiments]])
**L1:**

| Variant | Profit | vs. M1 buckets | Model's own estimate |
|---|---:|---:|---:|
| M1 buckets | 3,415,712 | — | 3,483,715 (+68 k optimistic) |
| M2 curves | 3,411,701 | −4,011 (SE 286) | 3,330,235 |
| M2 curves_up | **3,423,479** | **+7,767 (SE 172)** | 3,409,298 (−14 k) |

- At L1 both caps bind in all variants (115 added, 233 removed). The variants differ only in where and when.
- **M1's estimate is too optimistic.** Its point forecast ignores the variance, so it overstates profit by 68 k. The curves are honest: they estimate within 14 k, slightly pessimistic, because the scorer upgrades more flexibly than the split.
- **Upgrades matter in the objective.** Curves without upgrades lose to point-forecast buckets *with* upgrades, while curves with upgrades win.

**L3** (drivers + trucks + upgrades):

| Variant | Profit | vs. M1 buckets | Model's own estimate | Solve |
|---|---:|---:|---:|---|
| baseline | 3,118,529 | −855,293 | — | — |
| M1 buckets | 3,973,822 | — | 4,218,319 (**+244 k optimistic**) | time limit |
| M2 curves | 3,929,427 | −44,395 (SE 887) | 3,801,574 | optimal, 223 s |
| M2 curves_up | **4,002,078** | **+28,256 (SE 604)** | 4,087,390 (+85 k) | time limit |

- **Same ranking as L1:** curves_up > buckets > curves. All plans are valid by our check.
- **Transfers amplify the bias of the point forecast.** M1 overstates its profit by 244 k, because it moves cars to chase revenue that $E[D]$ promises but the spread of $D$ doesn't deliver. The curves are much closer.
- curves_up uses fewer transfers (656 vs. 745 cars), with transfer cost 88.6 k vs. 97.1 k, and earns more.
- Both caps still bind in buckets and curves_up (233 removed); the L3 plans add no cars.

## Round 2 (2026-11-13, 14:00–14:45): the four objectives at L3 with Gurobi
**The objectives being compared** ([[Project Plan]] §3). All use the same M1 model, forecast and costs:

| Name in code | Revenue term | Upgrades in the model | Exact? |
|---|---|---|---|
| `point` | M1: price-factor buckets at the point forecast $E[D]$ | yes | no (ignores the spread of $D$) |
| `saa_up` | classic SAA: per-scenario $p^\omega, q^\omega$ and buckets at each $D^\omega$ (`build_model(scenarios=…)`) | yes | yes, for the sample (the model may split upgrades better than the scorer's greedy rule) |
| `saa` | classic SAA | no | yes |
| `curves_same` | curves $\bar R$ from the **same** scenarios as the SAA, at every kink ($D^\omega\cdot s_i$) | no | **equals `saa`**: without upgrades the second stage separates per cell and serves $\min(D^\omega,a)$ |
| `curves_more` | curves from **500** scenarios, 20-segment grid | no | yes, up to the grid |
| `curves_up_same` / `curves_up_more` | the curves above, plus M1's upgrade variables (deterministic split of the higher category's capacity) | yes | no |

**Setup:**
- Level 3, Gurobi 13 (used for experiments with your OK; the final model must still solve with HiGHS), MIP gap 0.5 %, time limit 900 s.
- **Scenario seeds:** SAA $N=20$ (seed 11); the "more" curves use 500 scenarios (seed 12). All plans are scored on 500 *other* scenarios (seed 2026), with paired SEs.
- Code: `scripts/compare_objectives.py solve|score`, plans `plans/cmp_L3_<variant>.csv` (+ `.json` with status, gap and bound).

**Results (L3):**

| Variant | Profit | vs. `point` (paired SE) | Model's own estimate | MIP gap | Wall time |
|---|---:|---:|---:|---:|---:|
| baseline | 3,118,529 | −867,410 | — | — | — |
| `point` | 3,985,938 | — | 4,230,800 (+245 k) | 0.48 % | 159 s |
| `curves_same` (N = 20, exact) | 3,932,348 | −53,591 (910) | 3,799,817 (−133 k) | 0.50 % | 1,358 s |
| `curves_more` (N = 500) | 3,932,586 | −53,352 (895) | 3,809,821 (−123 k) | 0.35 % | 154 s |
| **`curves_up_more`** (N = 500) | **4,011,116** | **+25,177 (463)** | 4,110,898 (+100 k) | 0.43 % | 437 s |
| `curves_up_same` (N = 20, exact) | 4,009,002 | +23,064 (−2,114 vs. `curves_up_more`, SE 272) | 4,102,120 (+93 k) | 0.50 % (time limit) | 2,072 s |
| *bootstrap SAA with upgrades* (N = 10, other session, `run_saa_bootstrap.py`) | 3,999,597 | +13,659 (−11,519 vs. `curves_up_more`, SE 370) | 4,157,279 (+158 k) | 0.67 % (stopped at 520 s) | 520 s |
| `saa`, `saa_up` on our 20 scenarios | not run to the end (see finding 5) | | | | |

**Findings:**
1. **`curves_up_more` is the best plan so far:** 4,011,116, i.e. +25 k over the point-forecast model and +893 k over the baseline. With a closed gap it is 9 k above the earlier HiGHS run (time limit). The plan is committed as `plans/cmp_L3_curves_up_more.csv` (commit `7cbe44f`).
2. **With upgrades, more scenarios help a little and cost less:** `curves_up_more` (N = 500) beats `curves_up_same` (N = 20) by +2.1 k (SE 0.3 k). It also finishes in 437 s instead of 2,072 s.
   - **First SAA with upgrades at L3** (bootstrap scenarios, N = 10, gap 0.67 %): 3,999,597, between the point model and the curves. It is not a clean SAA comparison: the scenarios are replayed history weeks without the booking update, and N is small.
3. **More scenarios don't change the curves without upgrades:** N = 20 exact and N = 500 on a grid give the same profit (3,932,348 vs. 3,932,586). The expectation of a separable concave term is well estimated by few scenarios.
   - The grid is **9× faster to build**: ~100 kink segments per cell make the exact curves slow in PuLP.
   - So with more scenarios the cost does *not* go up: the grid version is both cheaper and as good.
4. **Without upgrades in the model, the curves lose 53 k** against the point model *with* upgrades. The upgrades are worth more than accounting for the spread of $D$, and both together are best.
5. **The models' own estimates:**
   - The point model overstates by 245 k.
   - The curves without upgrades understate by 123–133 k, because the scorer still upgrades.
   - The curves with the upgrade split overstate by 100 k: the ex-ante split assumes the higher category's spare cars are always free.
6. **SAA on our scenarios (`saa`, `saa_up`) didn't finish in this round.** PuLP's standard Gurobi interface builds the model one variable at a time, so with 20 scenario blocks the handover to Gurobi alone took over 40 minutes. The runs were stopped at 14:44.
   - A parallel session has since added a batched builder (`solvers._FastGUROBI`; L1 SAA solves in 46 s) and is running `saa_up` (N = 10) and a bootstrap SAA at L3.
   - The `saa` = `curves_same` check on our scenarios is still open. The bootstrap SAA result is in the table above.

## All plans on one scale (2026-11-13, 14:58)
Every plan in `plans/` scored on the same 500 evaluation scenarios (seed 2026), with paired SE against the best plan. All are valid by our check.

| Plan | Model / objective | Solver, gap | Profit | vs. best (paired SE) | added / removed / transferred |
|---|---|---|---:|---:|---|
| **`cmp_L3_curves_up_more`** | M2 curves (500 scen.) + upgrade split | Gurobi 0.43 % | **4,011,116** | — | 0 / 233 / 711 |
| `cmp_L3_curves_up_same` | M2 curves (20 SAA scen., exact) + upgrade split | Gurobi 0.50 % | 4,009,002 | −2,114 (272) | 3 / 233 / 719 |
| `cmp_L3_curves_up` | M2 curves (300 scen.) + upgrade split, round 1 | HiGHS, time limit | 4,002,078 | −9,038 (615) | 0 / 233 / 656 |
| `cmp_L3_saa_boot_gurobi` | M1 classic SAA + upgrades, bootstrap N = 10 | Gurobi 0.67 % | 3,999,597 | −11,519 (370) | 0 / 233 / 730 |
| `cmp_L3_point` | M1 buckets at E[D] | Gurobi 0.48 % | 3,985,938 | −25,177 (463) | 0 / 232 / 781 |
| `cmp_L3_buckets` | M1 buckets at E[D], round 1 | HiGHS, time limit | 3,973,822 | −37,294 (470) | 0 / 233 / 745 |
| `cmp_L3_curves_more` | M2 curves (500 scen.), no upgrades | Gurobi 0.35 % | 3,932,586 | −78,530 (689) | 49 / 120 / 570 |
| `cmp_L3_curves_same` | M2 curves (20 SAA scen., exact), no upgrades | Gurobi 0.50 % | 3,932,348 | −78,768 (708) | 49 / 123 / 563 |
| `cmp_L3_curves` | M2 curves (300 scen.), no upgrades, round 1 | HiGHS, optimal | 3,929,427 | −81,689 (702) | 49 / 124 / 578 |
| `cmp_L1_saa_boot_gurobi` | M1 classic SAA + upgrades, bootstrap N = 10, **L1** | Gurobi 0.43 % | 3,420,297 | −590,819 | 115 / 233 / — |
| `cmp_L1_saa_boot` | same, HiGHS, **L1** | HiGHS 22 % | 3,411,869 | −599,247 | 115 / 233 / — |
| `cmp_L1_saa_boot_noup` | M1 classic SAA, no upgrades, bootstrap, **L1** | HiGHS 7.4 % | 3,411,796 | −599,320 | 106 / 233 / — |
| baseline | fleetkit rule ([[M0 Baseline]]) | — | 3,118,529 | −892,587 | 96 / 0 / — |
| do-nothing | — | — | 3,021,476 | −989,639 | 0 / 0 / — |

**Reading it:**
- **Transfers dominate:** L3 is worth about 590 k more than L1.
- **Upgrades in the objective come next:** about +78 k.
- **The objective form adds tens of thousands on top:** curves > SAA-bootstrap (N = 10) > point forecast.
- **L1 cross-check:** the best L1 plans are SAA-bootstrap with Gurobi (3,420,297) and M2 curves_up from round 1 (3,423,479, scored on the same seed; the plan file was later removed). That's the same ranking as at L3.
- **Both caps bind** in every good L3 plan: all 233 removals are used and almost no additions.

## Known issues / next ideas
- **Exact upgrades under uncertainty:** SAA with per-scenario serving variables $p^\omega, q^\omega$ and fills, over 20–30 scenarios. That's large; worth it only if `curves_up` leaves a gap. Implemented as `build_model(scenarios=…)`; on our scenarios not run to the end (round 2, finding 6).
- Re-check the result with other curve seeds and $N$.
