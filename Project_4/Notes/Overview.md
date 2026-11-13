---
tags: [overview, index]
event: SIXT Hackathon 2026
date: 2026-11-13
status: topic confirmed
---

# Overview

The team vault for **SIXT Hackathon 2026, Project 4: Fleet Allocation Challenge**.
Start here: this note maps out the vault and tracks where we stand.


## Notes in this vault
| Note | What it's for |
|---|---|
| [[Overview]] | This page: vault map, status, team, setup, log |
| [[Project Description]] | The task in brief: rules, scoring, levels, data, feedback loop |
| [[Project Plan]] | The plan for the day: data findings, approach (base revenue, demand, SAA curves, IP), timeline, roles, milestones |
| [[Final Checklist]] | Everything due by 16:45: plan, code, `SUBMISSION.md`, demo, push |
| [[Models]] | Index of model versions; each version (`Models/M<n> …`) has its own note |
| [[Experiments]] | One row per evaluated plan: change, solver, profit, validity |
| [[Decisions]] | Dated decisions with reasoning and the alternatives rejected |
| [[Demand]] | Findings on the demand process: weekday pattern, rental lengths, weekly Gamma shock, demand to come, implications for the forecast |
| [[Base Revenue]] | Findings on base revenue per car-day: estimator, table, multiplicative structure, implications; code in `fleetopt/forecast.py` |

Agent instructions for this repo live in `CLAUDE.md` at the repo root.

## Conventions
- One topic per note. Link with `[[Note Name]]`.
- Put tags in the frontmatter (`tags: [...]`).
- Use checkboxes for to-dos, so the Tasks or Dataview plugins can collect them later.
- This vault lives in the repo (`Project_4/Notes/`). Obsidian's UI state is git-ignored; everything else is shared.


## Setup quick reference
- `Project_4/.venv`: Python 3.14.10 (uv-managed), numpy, pandas, pandera, PuLP with CBC **and HiGHS** (default solver), ipykernel and matplotlib for notebooks, gurobipy 13.0.3 (not in requirements. Would leave it out of there bc we don't whether judges have Gurobi and also only academic license)
- Activate with `source .venv/bin/activate`, or run `.venv/bin/python starter.py`

## Source documents (in the repo)
- `Project_4/README.md`: the full project spec
- `README.md`: general hackathon rules and submission steps
- `SUBMISSION_TEMPLATE.md`: template for `Project_4/SUBMISSION.md`

## Log
- 2026-11-12: environment set up, notes vault created.
- 2026-11-12: topic confirmed as Project 4; removed Project_1/2/3/5/6.
- 2026-11-12: split the project spec out of the Overview into [[Project Description]].
- 2026-11-12: added `CLAUDE.md`, plus the [[Models]], [[Experiments]] and [[Decisions]] notes; HiGHS installed as the default solver.
- 2026-11-12: split models into `Models/` (index + one note per version, [[M0 Baseline]]); added `Templates/Model Template`.
- 2026-11-12: agreed on the plan for the day in [[Project Plan]].
- 2026-11-12: **Level 0 done**: `fleetopt/level0.py` matches all 10 rows of `check_values.csv`; own validity check `fleetopt/evaluate.py` (R5) says do-nothing and baseline are valid. See [[Decisions]].
- 2026-11-13: wrote out the formulation as [[M1 Full Fleet MIP]] (full scorer as one MIP; levels are restrictions). See [[Decisions]].
- 2026-11-13: reviewed M1 against an independent scorer: fixed the greedy big-M sign and the profit print in `run_m1.py`. See [[Decisions]].
- 2026-11-13: exploration notebooks `notebooks/01_base_revenue.ipynb` (base per car-day per station × category) and `notebooks/02_demand_distribution.ipynb` (demand per weekday × station × category, dispersion, pseudo-snapshot demand to come). They use history only, with no future bookings. Takeaways are at the end of each notebook.
- 2026-11-13: **base revenue done**: `fleetopt.forecast.base_revenue` (cell ratio estimator, tested) plus `scripts/estimate_base_revenue.py` → `estimates/base_revenue.csv`. Findings in [[Base Revenue]].
- 2026-11-13: demand notebook: rental lengths checked (pooled truncated geometric, independent). Pickups are **not** Poisson: one Gamma shock per cell and calendar week (±13 %), no carry-over, independent across cells. See [[Decisions]].
- 2026-11-13: demand findings written up in [[Demand]]. Bookings rule clarified in [[Decisions]]: allowed for conditioning, never in history estimates.
- 2026-11-13: **forecast done**: `fleetopt.forecast` gives the model inputs (`model_inputs`), seeded demand scenarios (`sample_demand`) and per-week booking updates (−28 % / −21 % backtest MSE). `scripts/make_estimates.py` writes `estimates/`. Routes A and B agree. See [[Demand]].
- 2026-11-13: **our scorer computes profit** (R6–R11, `fleetopt.evaluate.score_plan`, `scripts/score_plans.py`). Do-nothing 3.03 M, baseline 3.12 M (+97 k ± 0.7 k) on 200 scenarios. See [[Experiments]].
