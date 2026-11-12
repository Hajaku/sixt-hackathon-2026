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
