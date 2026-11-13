---
tags: [experiments, results, project-4]
---

# Experiments

One row per evaluated plan. Append only, never rewrite past rows. This feeds the Results section of `SUBMISSION.md`.
The **Model** column links the exact model version from [[Models]]. If the model changed, create a new version note first.
The **Commit** column holds the short git hash of the code that produced the plan (`git rev-parse --short HEAD`), so any row can be reproduced with `git checkout <hash>`. Commit before you log a run. If the code had uncommitted changes, write `<hash>-dirty`. Such a row can't be reproduced exactly, so avoid it for anything we might submit.
Back to [[Overview]] · [[Models]] · [[Decisions]]

**Reference points** (from `leaderboard.md`): do-nothing = ? · baseline ([[M0 Baseline]]) = ?

| When | Plan file | Commit | Model | Forecast / params | Solver / time / gap | Our profit est. | Official profit | Valid? | Notes |
|---|---|---|---|---|---|---|---|---|---|
| | `plans/baseline.csv` | `0121d61` (fleetkit, unchanged) | [[M0 Baseline]] | none | none | | | | reference |
| 2026-11-13 12:38 | `plans/do_nothing.csv` | `9ff803c-dirty` (scorer not yet committed) | none (do-nothing) | `forecast.sample_demand`, 200 scenarios, seed 2026, booking update on; base = cell estimate | none | **3,027,360** (SE 4,048); 3,053,943 at E[D] | | valid (ours) | committed 2,851,080 · new 2,885,854 · holding 2,709,574 |
| 2026-11-13 12:38 | `plans/baseline.csv` | `9ff803c-dirty` (scorer not yet committed) | [[M0 Baseline]] | same scenarios as the row above | none | **3,124,078** (SE 4,108); 3,154,649 at E[D] | | valid (ours) | +96,719 vs. do-nothing (paired SE 723) · 96 cars added · addition 43,680 · holding 2,809,226 |
