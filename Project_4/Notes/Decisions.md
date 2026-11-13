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

## 2026-11-13: M1 review: greedy big-M sign fixed; LP second stage stays the default for now
- **Bug:** the R7 greedy constraint read $p \ge a^{fr} - M(1-\theta)$. Then $\theta=1$ forces $p \ge \max(\hat D, a^{fr})$ and $\theta=0$ forces nothing, so the solver set $\theta=0$ everywhere and `exact_greedy` did nothing. **Fixed** to $p \ge a^{fr} - M\theta$ ($\theta=1 \Rightarrow p=\hat D$, $\theta=0 \Rightarrow p=a^{fr}$), in code and in [[M1 Full Fleet MIP]] (no experiments ran against the wrong version).
- **Also fixed:** `run_m1.py` printed revenue **+** costs as the profit estimate.
- **Checked** against an independent R6–R11 scorer on the forecast as the scenario: costs match to the euro. With the fix and `--exact-greedy`, the L1 model profit equals the scorer's (3,503,800). Without θ (the default LP second stage), the model overstates new revenue by 0.8 % (L1) to 2.7 % (L2): it diverts category-$k$ capacity from its own demand to $k{-}1$ upgrades when $k{-}1$'s bucket marginal is higher. The scorer also rates the exact-greedy plans higher (L1 +11k, L2 +37k at a 120 s limit).
- **Open:** exact greedy is slower (L1 ≥ 120 s instead of 17 s). Next: keep θ only on cells where diverting can pay ($\max_b \mu_{k-1,b} > \min_b \mu_{k,b}$) and tighten $M^a$ per cell, then make it the default.

## 2026-11-13: Forecast implementation: route A, each week conditioned on its bookings
- **Decision:** `fleetopt.forecast` is the forecast for the model and our scorer.
  - **Point forecast** (`model_inputs`): $E[D_{s,k,d}]=\sum_{p\le d}E[G_{w(p)}]\,\lambda_{s,k,\mathrm{wd}(p)}\,P(L\ge d-p+1,\ \ell\le p-1)$. It uses plain 8-week weekday means for $\lambda$ and the joint empirical (L, ℓ) kernel per station type × category.
  - **Scenarios** (`sample_demand`, seeded): weekly Gamma factors, Poisson to-come pickups, lengths from the kernel.
  - **Booking update:** each horizon week's factor is conditioned on the bookings already made for that week, with Gamma posterior $(1/v+n_B,\ 1/v+\mu_B)$.
- **Why:**
  - Route A and route B (pseudo-snapshots) agree: totals within 0.3 %, per cell-day correlation 0.998.
  - The booking update lowers the backtest MSE of to-come pickups by 28 % (week 1) and 21 % (week 2), using rates estimated without the predicted weeks.
  - The bookings match the model's prediction on average, so $\lambda$ and the lead distribution are consistent.
- **Rejected:**
  - The README's "mean − committed" placeholder in `scripts/run_m1.py`: it ignores the B–D correlation and has no scenarios.
  - Route B as the forecast: noisy, 7–8 snapshots per cell-day.
  - Updating only week 1: week-2 bookings carry information on the week-2 factor too.
- **Not modelled:** variation of base between hidden scenarios. Revenue is linear in base, so it only affects the score spread (see [[Base Revenue]]).

## 2026-11-13: Revenue term: expected-revenue curves with upgrade split (M2 curves_up)
- **Decision:** the candidate for the final plan is [[M2 Expected-revenue curves]] in the `curves_up` variant. It is M1 with buckets built from $\bar R_{s,k,d}(a)$ over 300 demand scenarios, and with M1's upgrade variables kept.
- **Why:** on 500 independent evaluation scenarios at L3 it beats M1's point-forecast buckets by +28 k (paired SE 0.6 k) and the baseline by +884 k. At L1 the ranking is the same (+7.8 k, SE 0.2 k).
  - Its own profit estimate is much closer to the evaluation: +85 k at L3, vs. +244 k for the buckets.
  - The averaging removes the non-concave cells, so no prefix binaries are needed.
- **Rejected:**
  - Curves without upgrades in the model (−44 k at L3): the model can't see that the higher category's spare cars help.
  - Point-forecast buckets: they ignore the spread of $D$ and chase revenue that doesn't come.
- **Open:**
  - L3 hit the 300 s time limit for buckets and curves_up, so check the MIP gap.
  - Exact upgrades via SAA.
  - Robustness to the curve seed.


## 2026-11-13: Bootstrap scenarios as a second scenario source (check, not yet a choice)
- **What:** `fleetopt/bootstrap.py` replays the history weeks. Each horizon week $j$ gets one of the 8 history weeks, drawn with replacement and independently for the two weeks. Every rental in that week keeps its weekday, length and lead, and counts as demand to come iff $\text{lead} \le p-1$. `block="network"` uses the same week for every cell, so it keeps the cross-cell correlation of the history; `block="cell"` draws per cell. Script: `scripts/run_saa_bootstrap.py` (SAA solve + scoring on the parametric and the bootstrap test sets).
- **Why:** it tests whether the plan depends on our parametric demand model (Gamma week factor, iid cells, joint length–lead kernel per station type).
- **Findings:**
  - The bootstrap mean matches `expected_demand(booking_update=False)` to within 1 % per day.
  - The SD of total demand is 206 (network blocks) vs. 244 (cell blocks) vs. 268 (parametric). The history shows no positive cross-cell correlation, so the parametric iid assumption is, if anything, conservative.
- **Limits:**
  - No booking update.
  - Only 64 distinct network scenarios, so scoring the bootstrap plans on them is in-sample.
- **Open:** the L1 SAA hits the 300 s limit (gap 22 % with upgrades, 7 % without), so compare against the parametric SAA (`compare_objectives.py saa_up`) at equal solve time.

## 2026-11-13: Gurobi as a measuring tool, with a batched model build
- **Context:** the L1 classic SAA (10 bootstrap scenarios, with upgrades) stops at the HiGHS 300 s limit with a 22 % gap.
- **Test (asked for by us):** Gurobi 13 on the same model.
  - It reaches a 0.43 % gap in 46 s.
  - Its plan scores **+8.4 k** over the HiGHS plan on the 500 parametric evaluation scenarios.
  - So HiGHS's gap is mostly a weak bound: its incumbent is only about 2 % worse in model objective.
- **Engineering:** PuLP's `GUROBI` builds the model one variable at a time and looks up each objective coefficient separately: about 540 s of a 586 s run. `fleetopt/solvers.py` now has `_FastGUROBI`, which builds in batches (`addVars` + `addLConstr`). Same objective, 53 s wall. `get_solver("gurobi")` uses it.
- **Rule unchanged:** the submitted model must solve with HiGHS, and gurobipy stays out of `requirements.txt`. Gurobi plans are reference points that show how much HiGHS leaves on the table at a given time limit.
- **Rejected:** `pulp.GUROBI_CMD`, because there is no `gurobi_cl` binary in our setup.

## 2026-11-13: Gurobi for the objective experiments; curves from many scenarios on a grid
- **Gurobi:** allowed by the team for the experiments, because HiGHS couldn't close the L3 gaps in useful time and SAA needs it even more.
  - The submitted model must still solve with HiGHS. The HiGHS run of the same curves model at L3 (time limit) was within 9 k of the Gurobi plan.
  - gurobipy stays out of `requirements.txt`.
- **Curves on a grid:** build the expected-revenue curves from many scenarios (500) on a 20-segment grid, not from the exact kinks of a few scenarios. At L3, N = 20 exact and N = 500 on a grid give the same profit, and the grid builds 9× faster: model size doesn't grow with N.
- **Candidate for `final.csv`:** `plans/cmp_L3_curves_up_more.csv` (4,011,116 on our 500 scenarios). It is replaced only if SAA with upgrades (still running) is clearly better.
- **Rejected:** exact-kink curves for production (slow to build, no gain).


## 2026-11-13: Bootstrap scenarios: not the scenario source for the final plan
- **Result (L3, with upgrades):**
  - The classic SAA on 10 bootstrap scenarios, solved by Gurobi to a 0.67 % gap, scores 3,999,597 on the 500 parametric evaluation scenarios.
  - That is **−11.5 k (paired SE 0.4 k)** vs. [[M2 Expected-revenue curves]] `curves_up_more`, which is the best plan so far at 4,011,116.
  - It also loses on the bootstrap's own 64 week pairs: −10.1 k, SE 1.5 k, and in-sample for the bootstrap plan. So the parametric curves plan is better on both scenario laws, not just on its own.
  - The SAA's own estimate is 158 k optimistic (10 in-sample scenarios), vs. 100 k for curves_up_more.
- **Reading:**
  - The gap comes from the number of scenarios (10, vs. 500 behind the curves) and from the missing booking update, not from the scenario law.
  - The bootstrap's cross-cell correlation hardly matters, since only the marginals enter the expected profit (see [[Demand]] §6).
- **Decision:** keep the parametric generator (booking update, smooth, as many scenarios as we want). Use the bootstrap only as a robustness check of the final plan: score it on `bootstrap.all_week_pairs`.
- **Rejected:** a bootstrap SAA with more scenarios. Only 64 distinct network scenarios exist, and the classic SAA grows by one serving block per scenario.

## 2026-11-13: Exact R7 greedy in the final model; final between point and SAA
- **Finding:**
  - The exact greedy binaries θ are worth about +100 k at L3: `point_greedy` scores 4,108,409, against 4,011,116 for the best plan without them.
  - Without θ the model splits capacity between own demand and upgrades in a way the scorer never does, so the plan is built for a split that does not happen.
  - This gain is far larger than curves vs. point (+25 k).
- **Spec audit (subagent):** the model matches R1–R11. Drivers are allowed at L2/L3 but cost more than trucks from 5 cars up. Trucks use the ceil rule ($\sum_k y \le 8z$, $z$ integer). Only a loose upper bound on $z$ was fixed.
- **Candidates:**
  - `point` + greedy: 4,108,409, gap 0.6 %.
  - SAA (N = 20) + greedy: 4,098,427, gap 3.7 % after 900 s.
  - SAA (N = 10) + greedy: 4,095,776.
  - Curves + greedy: 4,060,965. The greedy threshold $\max_\omega D^\omega$ is too pessimistic about upgrades.
  - The final choice between point and SAA is still open; both lie within the ~25 k tie band of 30 hidden scenarios.
- **Reproduction:** `scripts/make_final.py --objective point|saa`. It uses Gurobi by default, because Gurobi closes the L3 gaps. Without gurobipy or a license it falls back to HiGHS with a message (`solvers.pick_solver`). gurobipy stays out of `requirements.txt`.
- **Removed:** `scripts/run_m1.py`. It used the README's placeholder forecast and was superseded by `compare_objectives.py` and `make_final.py`; it is still in git history.

## 2026-11-13: Final plan = `final_point`
- **Decision:** submit `plans/final_point.csv` (point forecast + exact R7 greedy, L3) as `plans/final.csv`.
- **Why:** it has the best mean on our 500 evaluation scenarios: 4,108,409, which is +9,982 over SAA N = 20 (paired SE ≈ 0.7 k). It is also the only candidate whose MIP converged (0.6 % gap vs. 3.4–3.7 % for SAA). In `SUBMISSION.md` it is presented as the special case $|\Omega| = 1$, $D = E[D]$ of the SAA model.
- **Rejected:**
  - SAA N = 20: within the 30-scenario tie band, but lower on our scenarios and not converged.
  - Curves + greedy: −47 k.
