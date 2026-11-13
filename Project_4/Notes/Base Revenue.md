---
tags: [forecast, base-revenue, findings, project-4]
date: 2026-11-13
status: done
code: fleetopt/forecast.py
notebook: notebooks/01_base_revenue.ipynb
---

# Base Revenue

Findings on the base revenue per car-day $\hat r_{s,k}$ (notation of [[Models]]; called $\hat b$ in the notebook).
Back to [[Overview]] · [[Project Plan]] (§1) · [[Decisions]]

**In one line:** base depends only on station × category, is multiplicative, is estimated to within 2 %, and is independent of demand. So the model uses $\hat r_{s,k}$ as a fixed parameter.

## How to use it in code
```python
from fleetopt.forecast import base_revenue
b = base_revenue(inst)                      # one row per (station_id, category)
r_hat = b.set_index(["station_id", "category"])["base"]
```
- Columns: `base` (the chosen method), `base_cell`, `base_multiplicative`, `se`, `n_rentals`, `car_days`.
- `method="cell"` (default) or `method="multiplicative"`.
- `scripts/estimate_base_revenue.py` writes the same table to `estimates/base_revenue.csv` for reading. The function is the source of truth.
- `tests/test_forecast.py` checks it, and the notebook asserts that it gives the same numbers.

## Estimator
- **Data:** the history is at the base price with no lost demand (Appendix B), and R8 gives price factor 1 at $q=1$. So each rental's revenue per car-day $R_i/L_i$ is a draw of base.
- **Ratio estimator, car-day weighted:**
  $$\hat r_{s,k}=\frac{\sum_{i\in(s,k)}R_i}{\sum_{i\in(s,k)}L_i},\qquad \mathrm{SE}\approx\frac{\sqrt{\sum_i L_i^2\,(R_i/L_i-\hat r_{s,k})^2}}{\sum_i L_i}$$
- **Rentals used:** only the 25,674 `completed` rentals. `open` rentals serve only as a check (same prices). Future bookings are not used (see [[Decisions]], 2026-11-13).

## Results
$\hat r_{s,k}$ per car-day:

| Station | Type | economy | compact | midsize | premium |
|---|---|---:|---:|---:|---:|
| S01 Marlow Airport | airport | 244.2 | 299.0 | 385.6 | 545.0 |
| S02 Marlow Central | downtown | 268.1 | 325.2 | 415.5 | 598.8 |
| S03 Old Quarter | downtown | 281.6 | 340.1 | 438.0 | 628.3 |
| S04 Quayside | downtown | 255.3 | 307.7 | 391.5 | 570.4 |
| S05 Fairgrounds | downtown | 160.0 | 192.6 | 245.8 | 350.3 |
| S06 Dunmere Airport | airport | 233.8 | 286.4 | 372.5 | 522.4 |
| S07 Dunmere Central | downtown | 204.4 | 251.5 | 314.2 | 447.9 |
| S08 University Quarter | downtown | 188.4 | 223.8 | 291.1 | 415.7 |
| S09 Highvale Spa | downtown | 294.9 | 359.7 | 459.5 | 646.9 |
| S10 Lakeside | downtown | 287.6 | 349.8 | 449.2 | 642.8 |
| **network (car-day weighted)** | | **254.0** | **314.6** | **403.8** | **561.5** |

![[base_revenue_histograms.png]]

## Findings
1. **Precise.** The relative SE is 0.5–1.8 % per cell (the largest for premium at S05, S07 and S08). Estimation error is negligible next to the demand uncertainty.
2. **Multiplicative, $r_{s,k}=\alpha_s\beta_k$.** The two-way fit of $\log\hat r$ matches every cell to within 1.6 %, and all residuals are within 1.6 SE. So there is no station × category interaction.
   - **Station factor $\alpha_s$ (geo-mean 1):**

     | S01 | S02 | S03 | S04 | S05 | S06 | S07 | S08 | S09 | S10 |
     |---|---|---|---|---|---|---|---|---|---|
     | 1.04 | 1.13 | 1.19 | 1.07 | 0.67 | 0.99 | 0.86 | 0.79 | 1.24 | 1.21 |

     The airports are average; S05 Fairgrounds is the cheapest station, S09/S10 the most expensive.
   - **Category ratios (relative to economy):** compact 1.21, midsize 1.55, premium 2.22. They are the same at every station.

   ![[base_revenue_multiplicative.png]]
3. **Per-rental noise.** The CV is about 0.15 in every station, category and station type. The noise is right-skewed: log-normal fits better than normal. This only matters if we simulate revenue per rental.
4. **No other effects.** $R_i/L_i$ is flat in rental length, pickup weekday, lead time and history week, and open rentals are priced like completed ones. The only borderline point is history week 8, at −0.9 % (≈ 2.5 SE).

   ![[base_revenue_no_other_effects.png]]
5. **No time shocks, and no link to demand.** The price level per (s, k, week) and per (s, k, day) varies only as much as per-rental noise predicts (Var(z) = 0.85 weekly, 0.97 daily). Its correlation with pickups is +0.04 weekly and +0.01 daily.

   ![[base_revenue_time_and_demand.png]]

## Implications for the model
- **Point estimate is enough.** R8 revenue is linear in base, and base is independent of demand (finding 5). So $E[\text{revenue}]$ needs only $E[r_{s,k}]$, and $\hat r_{s,k}$ goes into the model as a parameter. No scenarios over base are needed.
- **Cell vs. multiplicative.** The two estimates differ by at most 1.6 %, which is within noise. We use the cell estimate (default) because it needs no model assumption. The multiplicative fit is the fallback if a cell ever has few rentals.
- **Upgrades:** an upgraded rental earns the base of the *requested* category (R7). So a midsize car serving compact demand earns $1.21/1.55 \approx 78\,\%$ of what it would earn on midsize demand, while paying midsize holding cost.
- **Holding cost as a share of base** (per car-day), $h_k/\hat r_{s,k}$:
  - S09/S10: 0.17–0.20; S01–S04, S06: 0.18–0.24; S07/S08: 0.24–0.31; S05: 0.31–0.37.
  - A car must be on rent a good share of its days to pay for itself. At S05 that takes over a third of its days even at the full base price, and more after the fare adjustment. Weak stations are the natural source for removals and transfers.
- **What the history can't tell us:** how much the hidden scenarios vary base *between* scenarios (R8: "base … of that scenario"). That doesn't change the expected profit, which is linear in base. It only widens the spread of the 30-scenario score.
