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
