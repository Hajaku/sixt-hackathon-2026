---
tags: [checklist, submission, project-4]
deadline: 2026-11-13 16:45
---

# Final Checklist: Project 4 submission

> [!danger] Hard deadline: **Fri 13 Nov, 16:45**
> The repo link from the registration form **is** the submission. Whatever is pushed by then counts.
> An **invalid `final.csv` ranks last**, so validity beats squeezing out the last euro.

Back to [[Overview]]

---

## T−∞: once the topic is confirmed
- [x] Topic match confirmed as **Project 4**
- [x] Delete the other project folders, keeping LICENSE, README, runbook, handout and assets
- [x] Commit and push the removal: `git commit -m "Keep only my project folder" && git push`
- [x] Repo is **public**, `git remote -v` shows our fork as `origin`, teammates added as collaborators
- [ ] Every teammate can run `.venv/bin/python starter.py`
- [ ] Found our **team folder in the shared folder** and the `leaderboard.md`

## T−60 min: the plan (60 % of the grade)
- [ ] Final plan written with `fleetkit.write_plan(...)` (checks the format only, **not** validity)
- [ ] Uploaded to the shared team folder under a **new** name (e.g. `final_candidate_v3.csv`) and read its `.result.md`:
  - [ ] **Valid**: zero violations
  - [ ] Profit is above the **baseline** and the **do-nothing** plan on `leaderboard.md`
- [ ] Our own check of the validity rules:
  - [ ] fleet ≥ committed car-days for **every** station × category × day
  - [ ] Σ additions per category ≤ `addition_cap`; Σ removals ≤ `removal_cap`
  - [ ] all ids, categories, modes and dates are valid; dates are inside 2027-03-01 … 2027-03-14
  - [ ] `cars` are integers ≥ 1; no transfer to its own station; `to_station_id` and `mode` empty for add/remove
- [ ] Robustness check: the plan isn't overfitted to the single public scenario (the final score is the mean of **30 hidden** scenarios)
- [ ] Copy the chosen plan to the shared team folder as **`final.csv`** before the deadline
- [ ] Also commit the same plan in the repo, e.g. `Project_4/plans/final.csv`

## T−45 min: code and reproducibility
- [ ] All code committed in `Project_4/`
- [ ] `requirements.txt` up to date (highspy, ipykernel, matplotlib + anything new; **no gurobipy**)
- [ ] One command regenerates `final.csv` from a fresh clone (test it in a clean checkout if there's time)
- [ ] Final model and plan reproducible with **HiGHS** (open source); if Gurobi was used anywhere, say so in `SUBMISSION.md`
- [ ] **No secrets in git**: no `.env`, keys or license files (`git status`, check `git log -p` for key-like strings)
- [ ] No real SIXT, customer or personal data (only the provided mock data)

## T−30 min: `Project_4/SUBMISSION.md`
Copy `SUBMISSION_TEMPLATE.md` to `Project_4/SUBMISSION.md` and fill in:
- [ ] **Authors**: team name, members
- [ ] **Project**: "Project 4: Fleet Allocation Challenge" (required: it must say which project)
- [ ] **Problem and approach**: main idea, assumptions (demand forecast, base revenue, simplifications)
- [ ] **Models and why**: the optimization model(s) (LP/MIP, time-space network…), solver, runtime; what we compared
- [ ] **Results**: the evaluation results the Project 4 README asks for
  - [ ] Profit vs. **do-nothing** and **baseline** (from `.result.md` / `leaderboard.md`)
  - [ ] Profit breakdown: committed revenue, new revenue, holding, addition, transfer cost
  - [ ] Cars added / removed / transferred
  - [ ] Level 0 check against `check_values.csv`
  - [ ] Highest level reached (L0–L4)
  - [ ] Honest limits and what didn't work
- [ ] **How to run**: Python 3.14+, `uv venv` / `pip install -r requirements.txt`, data in `Project_4/data/`, exact commands, environment variable **names** only
- [ ] **Demo**: path to the video or slides
- [ ] **Next steps**: more time, how SIXT could use it

## T−20 min: demo (pick ONE)
- [ ] **Either** `Project_4/submission/demo.mp4`: about 1 min, **under 50 MB**
- [ ] **Or** `Project_4/submission/slides.pdf`: **max 5 slides**
  - Suggested 5: problem → data and forecast → model → results vs. baseline → limits and next steps
- [ ] File is inside the **project folder** and committed

## T−10 min: final push
- [ ] `git status` is clean, `git push` done
- [ ] Open the **public** repo URL in a private browser window: `SUBMISSION.md`, code and `submission/` are visible
- [ ] `final.csv` is in the shared team folder **and** its `.result.md` says valid
- [ ] Repo link matches the one in the registration form

## After 16:45
- [ ] If we're a finalist: **present to the jury** (40 % of the grade: model and presentation)
- [ ] Optional: arXiv-style write-up with TUM (`arxiv_templates/`)
- [ ] Optional: tell the owners if we'd like to collaborate after the hackathon
