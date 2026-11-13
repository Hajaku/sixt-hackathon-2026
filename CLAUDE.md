# CLAUDE.md

Guidance for Claude Code (and any other coding agent) in this repo.

## Context
- **Event:** SIXT Hackathon 2026, Fri 13 Nov 2026. **Hard deadline 16:45.** Submission = this public repo.
- **Project:** Project 4, Fleet Allocation Challenge. All our work goes in `Project_4/`; the other project folders are already removed.
- **Spec:** `Project_4/README.md` (exact scoring rules in Appendix A). General rules: `README.md`. Template: `SUBMISSION_TEMPLATE.md`.
- **Team:** two people (the repo owner and Leander), both with PhDs from TUM in discrete optimization (IP, combinatorial optimization).
  - Talk to us at expert level about modeling: LP/MIP, network flows, time-space networks, duality, relaxations, decomposition. Don't explain OR basics.
  - We are **not** software developers. You own the engineering side: code structure, Python idioms, tooling, testing, git hygiene. Explain those choices in a sentence when it matters.

## What is graded
- **60 %**: mean profit of `final.csv` over 30 hidden demand scenarios. Scores within 2 standard errors tie. **An invalid plan ranks last.**
- **40 %**: jury assessment of the model and the presentation.
- So: **validity first**, then expected profit across scenarios. Don't overfit to the single public feedback scenario. A clear, explainable model matters as much as the last euro.

## Environment
- Python **3.14** venv at `Project_4/.venv` (uv-managed CPython 3.14.10). Run code with `Project_4/.venv/bin/python …` or after `source Project_4/.venv/bin/activate`.
- Install packages with `uv pip install --python Project_4/.venv <pkg>`, and add every runtime dependency to `Project_4/requirements.txt`.
- **PuLP 4 API** (not the old one): `model.add_variable(...)` / `model.add_variable_dict(...)`, and `stats = model.solve(solver)` returns an object with `.status`, `.has_solution` and `.objective`. See `Project_4/starter.py`. Old-style `pulp.LpVariable(..., cat=...)` fails.

## Solvers: open source by default
- **Default: PuLP + HiGHS** (`pulp.HiGHS(msg=False, timeLimit=..., gapRel=...)`). CBC (`pulp.COIN_CMD`) is the fallback.
- Keep the solver a **single parameter** (e.g. a `--solver highs|cbc|gurobi` flag or a `get_solver(name)` helper), never hard-coded in the model.
- **Gurobi:** gurobipy 13 plus an academic license (expires 2026-12-16) are installed locally, but the submission must run open source.
  - **Never** add gurobipy to `requirements.txt`.
  - Only switch to Gurobi after **asking** us, and only for a real performance bottleneck. The submitted model must still be solvable with HiGHS.
  - What counts in the end is the plan CSV and the model.

## Code layout (target)
```
Project_4/
  fleetkit/          provided helper code: load_instance, write_plan, baseline_plan, split_total_plan. Don't edit.
  fleetopt/          our package (create as needed)
    level0.py        committed car-days, one-way flows, fleet per (station, category, day); checked against check_values.csv
    forecast.py      demand to come + base revenue per (station, category, weekday/day)
    fares.py         price factors -> demand buckets (Appendix C); concavity check
    model.py         the MIP (time-space network, buckets, upgrades, trucks), built level by level
    evaluate.py      our own re-implementation of the scorer: validity + profit for a plan and a demand scenario
    solvers.py       get_solver(name)
  scripts/           thin entry points, e.g. run_level1.py -> writes plans/<name>.csv
  notebooks/         data exploration only (forecast checks, plots); no logic the pipeline depends on
  plans/             plan CSVs (plans/final.csv = the submitted one)
  tests/             pytest: Level 0 vs check_values.csv, plan validity, small model sanity checks
  Notes/             Obsidian vault (see below)
```
- Logic lives in `fleetopt/`. Scripts and notebooks only call it.
- Every plan goes through `fleetkit.write_plan` **and** our own validity check before anyone uploads it.
- The final plan must be reproducible with one command from a fresh clone. Seed anything random.
- Keep it simple: plain functions, pandas DataFrames, type hints on public functions, short docstrings. No frameworks or over-abstraction; it's a one-day hack.

## Git
- Work on `main` of our fork. Never push to the upstream `sixt-hackathon-2026/sixt-hackathon-2026` repo, and don't push branches there.
- **Ask before every commit.** Small, focused commits with clear messages.
- **Pushing** is done by us (it needs an SSH passphrase). Tell us when there's something to push.
- Never commit secrets (`.env`, keys, `gurobi.lic`) or real data. Only the provided mock data.

## Obsidian vault (`Project_4/Notes/`)
Keep it up to date as we work, without being asked:
- **`Overview.md`**: the vault index. Add every new note to its table, and add a dated line to its Log for milestones.
- **`Models/`**: one note per model version, plus the index `Models/Models.md`.
  - Name each version `M<n> <short name>`, created from `Templates/Model Template.md`. Fill in the frontmatter (`model`, `level`, `based_on`, `status`, `code`) and state what changed vs. `based_on`. Use LaTeX (`$…$`, `$$…$$`).
  - Add every version as a row in the index table. Shared notation lives in the index under "Shared building blocks".
  - Once a version has experiments, **don't rewrite it**. Make a new version instead. Only fix typos or add results.
  - The `M<n>` id should also appear in the code (e.g. a `MODEL_ID` constant or the plan file name) so plans trace back to a note.
- **`Experiments.md`**: append one row per plan we evaluate (date and time, plan file, **git commit short hash** (`<hash>-dirty` if uncommitted changes; commit first for anything that might be submitted), **model as a `[[M<n> …]]` link**, forecast/params, solver/time/gap, our profit estimate, official profit from `.result.md`, valid?, notes). Never rewrite past rows.
- **`Decisions.md`**: a short dated entry per decision (forecast method, simplifications, solver choice…) with the reasoning and the alternatives rejected.
- **`Final Checklist.md`**: tick items as they get done.
- **`Project Description.md`**: the condensed spec. Only change it if we misread the spec.
- Obsidian style: `[[wikilinks]]` between notes, frontmatter `tags`, `- [ ]` checkboxes.
