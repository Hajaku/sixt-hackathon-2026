---
tags: [model, project-4]
model: M1
level: L1–L3 (restrictions give each level)
based_on: "[M0 Baseline](M0%20Baseline.md)"
status: implemented
code: fleetopt/model_base.py, scripts/run_m1.py
created: 2026-11-13
---

# M1 Full Fleet MIP

One MIP for the whole scorer (R1–R11): additions, removals, driver and truck transfers in a time-space network, one-step upgrades, and concave-or-not fare buckets. Given the forecast $(\hat D, \hat r)$ it reproduces the scorer's revenue **exactly**, so the plan it produces is scored as the model prices it. Levels are restrictions of it: **L1** = set $y = 0$; **L2** = drivers only; **L3** = full.
Back to [Models](../Models.md) · [Experiments](../Experiments.md) · Spec: [Project Description](../../README.md)

## Idea and changes vs. based_on
- [M0 Baseline](M0%20Baseline.md) is a per-cell rule (add to a static "need"). M1 optimizes the full profit over the 14 days in one model: day-by-day fleet, transfers with lead times, removal caps, upgrades, and the marginal-revenue buckets of the fare adjustment.
- Not a derivation from M0 — M0 stays the reference to beat.

## Shared data (from [Models](../Models.md#Shared building blocks), all Level 0 or forecast)
- $c_{skd}$ committed car-days, $f^0_{sk}$ initial fleet, one-way flows $o^{+}_{skd}, o^{-}_{skd}$ (`fleetopt/level0.py`).
- Forecast: demand to come $\hat D_{skd}$, base revenue $\hat r_{sk}$.
- Stations $S$ with max utilization $u_s$; categories $K$ ordered $1\dots4$; days $D=\{1..14\}$; transfer arcs $(s,t)$ with distance $\delta_{st}$, lead $\ell_{st}\in\{1,2\}$.
- Costs: holding $h_k$, addition $a_k$; driver $(g^{d} + p^{d}\,\delta_{st})$ per car; truck $(g^{t} + p^{t}\,\delta_{st})$ per truck, 8 places; caps $\bar A_k, \bar R_k$.
- **Buckets** (Appendix C, fare adjustment at $\hat D_{skd}$): $b \in \{1..5\}$ with size $\beta_{skdb}$ and marginal revenue $\mu_{skdb} = \hat r_{sk} \times$ (bucket slope). First bucket uses pf(60 %) below 60 %; $\hat D_{skd}=0 \Rightarrow$ no buckets.

## Simplifications / assumptions
1. **Deterministic forecast**: one point estimate $(\hat D, \hat r)$; scenarios enter only at M3 (SAA curves on top of this model).
2. **No post-horizon transfers** ($d + \ell_{st} > 14$ dropped): the car pays transfer cost and holding, its destination gain is outside the horizon ⇒ never profitable (a transfer is not a removal dodge: in-transit cars still pay holding).
3. **Exact scorer behavior** given the forecast: greedy "own category first" via binaries, trucks with the `ceil` (no fractional trucks), bucket revenue incl. the non-concave downtown-midsize set via prefix binaries. The model is never smarter than the scorer (the pitfall in [Project Plan](../Project%20Plan.md) §4).

## Variables
| Var | Domain | Meaning |
|---|---|---|
| $x^{+}_{skd},\; x^{-}_{skd}$ | $\mathbb{Z}_{\ge0}$ | cars added / removed at $s$, cat $k$, effective from day $d$ |
| $y^{m}_{stk d}$ | $\mathbb{Z}_{\ge0}$, $m\in\{d,t\}$ | cars of cat $k$ departing $s\to t$ on day $d$ by driver / truck ($d+\ell_{st}\le14$) |
| $z_{std}$ | $\mathbb{Z}_{\ge0}$ | trucks on $(s,t)$ departing day $d$ (shared across categories) |
| $f_{skd}$ | $\mathbb{R}_{\ge0}$ | station fleet on day $d$ (integer automatically, by the flow equalities) |
| $a^{fr}_{skd}$ | $\mathbb{R}_{\ge0}$ | free capacity for demand to come (R6) |
| $p_{skd}$ | $\mathbb{R}_{\ge0}$ | car-days of cat-$k$ demand served by cat-$k$ cars ("own") |
| $q_{skd}$ | $\mathbb{R}_{\ge0}$, $q_{s4d}=0$ | cat-$k$ demand served by cat-$(k{+}1)$ cars (one-step upgrade, earns cat-$k$ revenue) |
| $s_{skdb}$ | $\mathbb{R}_{\ge0}$ | bucket fill, and $\delta_{skdb}\in\{0,1\}$ where non-concave |
| $\theta_{skd}$ | $\{0,1\}$ | greedy switch: 1 = own demand fully served |
| $w_{skd}$ | $\{0,1\}$ | starved switch: 1 = $u_s f_{skd} \ge c_{skd}$ (free capacity positive) |

## Constraints
**(1) Fleet flow (R3/R4)**, with $f_{sk,0} := f^0_{sk}$ and $y := 0$ for day indices $\le 0$:
$$f_{skd} = f_{sk,d-1} + o^{+}_{skd} - o^{-}_{skd} + x^{+}_{skd} - x^{-}_{skd} - \sum_{t}\sum_{m} y^{m}_{stk d} + \sum_{t}\sum_{m} y^{m}_{tsk,\,d-\ell_{ts}} \qquad \forall s,k,d$$

**(2) Validity (R5):** $\;f_{skd} \ge c_{skd} \quad \forall s,k,d.$
(Removals $\le$ fleet is implied by (1)+(2). Export only rows with $cars \ge 1$ for the plan format.)

**(3) Caps (R5):** $\;\sum_{s,d} x^{+}_{skd} \le \bar A_k,\quad \sum_{s,d} x^{-}_{skd} \le \bar R_k \quad \forall k.$

**(4) Free capacity (R6):** $\;a^{fr}_{skd} = \max(0,\ u_s f_{skd} - c_{skd})$ exactly, via a "not starved" binary $w_{skd}$ and the bound $M^a_{skd} = \max(0,\ u_s (f^{0,\text{net}}_k + \bar A_k) - c_{skd})$:
$$a^{fr}_{skd} \ge u_s f_{skd} - c_{skd},\qquad a^{fr}_{skd} \ge 0,\qquad a^{fr}_{skd} \le u_s f_{skd} - c_{skd} + M^a_{skd}(1 - w_{skd}),\qquad a^{fr}_{skd} \le M^a_{skd}\, w_{skd}$$
$w=1$ is feasible only when $u_s f \ge c$ (then $a^{fr} = u_s f - c$); $w=0$ forces $a^{fr} = 0$. Both branches upper-bound the true $\max(0,\cdot)$, so the model can never serve more than the scorer would. (Naively keeping only the two lower bounds is wrong: an $a^{fr}$ bounded from below only lets the solver serve out of thin air.)

**(5) Serving (R7):** per $(s,k,d)$:
- capacity: $p_{skd} + q_{s,k-1,d} \le a^{fr}_{skd}$ (own use + cars stepping down to $k-1$; $q_{s,0d}:=0$)
- unserved: $q_{skd} \le \hat D_{skd} - p_{skd}$
- greedy "own first", $p_{skd} = \min(\hat D_{skd}, a^{fr}_{skd})$, with big-M $M^a_{skd} \ge \overline{a^{fr}_{skd}}$:
$$p_{skd} \ge \hat D_{skd}\,\theta_{skd}, \qquad p_{skd} \ge a^{fr}_{skd} - M^a_{skd}\,\theta_{skd}$$
  $\theta=1 \Rightarrow p=\hat D$ (own fully served, leftover capacity may upgrade); $\theta=0 \Rightarrow p=a^{fr}$ (capacity binding, no upgrade out). At the optimum $q_{skd} = \min(\hat D_{skd}-p_{skd},\; a^{fr}_{s,k+1,d}-p_{s,k+1,d})$ — exactly the scorer's $\text{up}[k]$.

**(6) Fare buckets (R8):** $\;\sum_b s_{skdb} = p_{skd} + q_{skd}$ (served, R7 step 3), $\;0 \le s_{skdb} \le \beta_{skdb}$.
- Concave $\mu$ (marginals decreasing): LP fills best-first = correct revenue, no binaries.
- Non-concave cells (downtown midsize, see [Project Plan](../Project%20Plan.md) findings): prefix binaries $\delta_{skdb} = 1 \Leftrightarrow$ "bucket $b$ may be used": $\;s_{skdb} \le \beta_{skdb}\,\delta_{skdb}$ and $\;s_{skdb-1} \ge \beta_{skdb-1}\,\delta_{skdb}$ force in-order fill = exact R8 incl. linear interpolation.

**(7) Trucks (R10):** $\;8\,z_{std} \ge \sum_k y^{\text{truck}}_{stk d}$ (ceil is exact because cost is increasing in $z$).

## Objective (R11; committed revenue R9 is a constant, added in reporting)
$$\max \left( \sum_{s,k,d,b} \mu_{skdb} s_{skdb} \right)$$
$$- \sum_{k} h_k \left( \sum_{s,d} f_{skd} + \sum_{s,t,k} \ell_{st} (y^{\text{drv}}_{stk\cdot} + y^{\text{truck}}_{stk\cdot}) \right)$$
$$- \sum_{s,k,d} a_k x^{+}_{skd}$$
$$- \sum_{s,t,d} \left[ (g^d + p^d \delta_{st}) \sum_k y^{\text{drv}}_{stk d} + (g^t + p^t \delta_{st}) z_{std} \right]$$
A transferred car is in transit on days $d \dots d+\ell_{st}-1$ $\implies$ exactly $\ell_{st} h_k$ of holding per car (assumption 2 keeps all of it inside the horizon).

## Size and solve
- Integers: $x$ 1 120, $y$ up to $\approx 2\cdot|A|\cdot 4 \cdot 12.5 \approx 9$k on the full digraph ($|A|=90$), $z \le 1\,260$, $\theta$ and $w$ 560 each, prefix $\delta$ only on non-concave cells ($\approx 8\cdot14\cdot4$). Constraints of the same order. Prune arcs first (drivers within town, trucks between towns, or only pairs where expected marginal revenue gain exceeds the cost) — expected to fall to 1–2k transfer integers.
- HiGHS (default), MIP gap 1–2 %, time limit per level; CBC fallback ([Decisions](../Decisions.md)).

## Known issues / next ideas
- **Big-M tightness**: use per-cell $M^a_{skd} = u_s \bar f_{skd} - c_{skd}$ with $\bar f_{skd}$ the fleet bound ($f^0$ + $\bar A_k$ + in-transit bound). If the greedy binary weakens the LP too much, a variant drops $\theta$ and accepts an LP second stage that can be *smarter* than the scorer (revenue slightly overstated, plan still valid) — settle against `fleetopt/evaluate.py`.
- **Terminal wave**: no value of fleet after day 14 ⇒ expect removals at the caps near the end; check the caps don't bind validity $f\ge c$ on the last days.
- **Upgrades couple cells**, so the per-cell SAA curves of M3 are only approximate with upgrades (as noted in [Project Plan](../Project%20Plan.md) §3).
- L1 experiments solve the same model with $y \equiv 0$: no separate model needed.

## Experiments
See [Experiments](../Experiments.md) rows that link this note.
- 2026-11-13: classic SAA mode (`scenarios=`) run on bootstrap scenarios at L1 (`scripts/run_saa_bootstrap.py`): HiGHS 22 % gap in 300 s, Gurobi 0.43 % in 46 s (+8.4 k in our scorer). L3: see the next line.
- 2026-11-13: L3 classic SAA on 10 bootstrap scenarios, Gurobi 0.67 % gap at 520 s: 3,999,597 on the parametric test set. That is −11.5 k (SE 0.4 k) vs. [[M2 Expected-revenue curves]] curves_up_more, and −10.1 k (SE 1.5 k) on the bootstrap's own 64 week pairs.
