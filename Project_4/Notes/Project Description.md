---
tags: [spec, project-4]
source: Project_4/README.md
---

# Project Spec: Fleet Allocation Challenge

A condensed version of `Project_4/README.md`. Read that file for the exact rules (Appendix A) and data columns (Appendix B).
Back to [[Overview]] · See also [[Final Checklist]]

**Owners:** Sara Michetti, Julian Mehne (on-site tech support, domain experts remote)

## The problem in one paragraph
A rental company has **10 stations** (2 airport, 8 downtown) in 3 towns: Marlow, Dunmere and Highvale. It has **4 categories**: economy < compact < midsize < premium. Plan the next **14 days** (day 1 = Mon 2027-03-01) with three kinds of action:
- **add**: an early fleet addition. Costs 455 per car, with a cap per category.
- **remove**: send an idle car back early. Saves holding cost, with a cap per category.
- **transfer**: by `driver` (cost per car) or `truck` (up to 8 cars of any category). Lead time is 1–2 days, and a car in transit earns nothing.

The goal is **maximum profit**: revenue − holding − additions − transfers. Demand to come is unknown and has to be estimated from 8 weeks of history.

## Plan format
CSV columns: `action, date, category, station_id, to_station_id, mode, cars`

```
action,date,category,station_id,to_station_id,mode,cars
add,2027-03-01,economy,S03,,,2
remove,2027-03-04,premium,S07,,,1
transfer,2027-03-02,compact,S01,S05,driver,1
```

- Rows with the same values add up. A header-only file is the do-nothing plan.
- Always per category. `fleetkit.split_total_plan` converts a total-fleet plan into one per category.
- Write it with `fleetkit.write_plan` (checks the format, **not** validity).

## Hard constraints (an invalid final plan ranks last)
1. Station fleet ≥ committed car-days for every station, category and day.
2. Additions ≤ `addition_cap`, removals ≤ `removal_cap`. Each cap is per category, summed over all stations and days.
3. Valid ids, categories, dates and modes, and no transfer to its own origin.

## Scoring mechanics (key points)
- New demand ≤ `max_util[s] × fleet − committed`.
- Upgrades only go **one category up**, at the revenue of the category that was requested.
- The price factors make revenue **concave** in the share served, so serving less can pay more per car. Watch for sets that are *not* concave (Level 4).
- A one-way rental moves its car to the return station on the **day after** the return.
- Holding cost counts **every** car-day: idle, on rent and in transit.
- The fleet position after day 14 has no value.
- **Final rank = mean profit over 30 hidden demand scenarios.** Scores within 2 standard errors count as a tie. Don't overfit to the public feedback scenario.

## Judging
- **60 %**: rank of `final.csv` on the hidden scenarios
- **40 %**: jury assessment of the model and the presentation

## Levels (one model can grow through them)
- [ ] **L0 Data**: committed car-days, one-way flows, fleet per (s, k, d); a demand forecast and base revenue. Must match `data/check_values.csv`.
- [ ] **L1 Fleet size**: add and remove only. Beat the baseline (96 cars added on day 1).
- [ ] **L2 Driver transfers**: a time-space network.
- [ ] **L3 Categories and trucks**: upgrades, trucks with 8 places.
- [ ] **L4 Bonus**: robustness to forecast error; check the price-factor sets for concavity.

## Data at a glance
| File | What |
|---|---|
| `horizon.csv` | first and last date |
| `stations.csv` | type, position, max utilization |
| `distances.csv` | km plus lead time |
| `fleet_snapshot.csv` | 2,357 cars at the start of day 1 |
| `reservations.csv` | 25,674 completed / 1,041 open / 1,865 booked |
| `categories.csv` | holding cost, addition cost, caps |
| `transfer_costs.csv` | driver 91 + 18.2/km; truck 682 + 4.5/km |
| `price_factors.csv` | factors at 60–100 % served, by station type and category |
| `check_values.csv` | 10 L0 check cells |

## Feedback loop (on the day)
1. `fleetkit.write_plan(...)` checks the **format only**.
2. Copy the plan to the team folder in the **shared folder** with a fresh name, e.g. `level1_v2.csv`.
3. About 1 min later, `level1_v2.result.md` appears with validity, violations and the profit breakdown.
4. `leaderboard.md` shows the best profit of each team, plus the do-nothing and baseline profits.
5. Before the deadline, put the final plan in the team folder as `final.csv`.
