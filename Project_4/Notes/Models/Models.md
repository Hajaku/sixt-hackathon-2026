---
tags: [models, index, project-4]
---

# Models

An index of every model version. Each version gets its own note in this folder, named `M<n> <short name>` (e.g. `M1 Fleet size MIP`).
[[Experiments]] link to these notes, so a result always points to the exact model that produced it.
Back to [[Overview]] · Spec: [[Project Description]] · [[Decisions]]

## How to add a version
1. Create a new note in `Models/` from the template (Command palette → *Templates: Insert template* → **Model Template**), or copy [[Model Template]].
2. Name it `M<next number> <short name>` and fill in the frontmatter (`based_on`, `level`, `code`).
3. Add a row to the table below.
4. Never rewrite an old version once it has experiments. Create a new version instead and note what changed.

## Versions
| Model | Level | Based on | Idea in one line | Status | Best official profit |
|---|---|---|---|---|---|
| [[M0 Baseline]] | L1 (rule) | none | fleetkit's baseline rule: add cars on day 1 up to the history-based need | reference | ? |
| [[M1 Full Fleet MIP]] | L1–L3 | [[M0 Baseline]] | one MIP for the whole scorer: add/remove, time-space transfers, trucks, upgrades, fare buckets; levels are restrictions of it | tested; L3 point 3,985,938; **with exact greedy: point 4,108,409 (best), SAA N = 20 4,098,427**; classic SAA on bootstrap scen. 3,999,597 (Gurobi) | — |
| [[M2 Expected-revenue curves]] | L1–L3 | [[M1 Full Fleet MIP]] | M1 with the revenue as expected-revenue curves over demand scenarios (SAA per cell) instead of buckets at E[D]; variants without and with upgrade split | tested; best: curves_up_more L3, 4,011,116 on our scenarios | — |

**Status values:** `idea` → `wip` → `tested` → `submitted` / `dropped`

## Shared building blocks
Notation that every version reuses, so the version notes only state what differs.

- **Sets:** $S$ stations, $K$ categories (ordered economy < compact < midsize < premium), $D=\{1,\dots,14\}$ days, $B_{s,k,d}$ demand buckets from the fare adjustment
- **Data (Level 0):** committed car-days $c_{s,k,d}$ (R1); initial fleet $f^0_{s,k}$ (R3); one-way arrivals and departures (R2)
- **Forecast:** demand to come $\hat D_{s,k,d}$, base revenue per car-day $\hat r_{s,k}$ (`fleetopt.forecast.base_revenue`, see [[Base Revenue]]); demand process in [[Demand]]; both as model input via `fleetopt.forecast.model_inputs(inst)`
- **Parameters:** max utilization $u_s$; holding cost $h_k$; addition cost $a_k$; caps $\bar A_k, \bar R_k$; transfer costs and lead times $\ell_{s,t}$
