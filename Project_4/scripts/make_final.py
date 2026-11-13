"""Reproduce our final plan with one command: Level 3 fleet MIP with the exact R7 greedy.

Usage (from the repo root or Project_4/):
    Project_4/.venv/bin/python Project_4/scripts/make_final.py [--objective point|saa]
        [--solver gurobi|highs|cbc] [--time-limit S] [--gap 0.005] [--saa-scenarios 20]
        [--out plans/final.csv] [--eval-scenarios 500]

Model: M1 (Notes/Models/M1 Full Fleet MIP.md) at Level 3: additions/removals, driver and
truck transfers on the time-space network, one-step upgrades, fare buckets, and the binaries
theta that make serving follow the scorer's own-category-first rule (R7) exactly.
Two revenue objectives, toggled with --objective:
  point  buckets at the point forecast E[D] (forecast.model_inputs, booking update on)
  saa    classic SAA: one serving block (p, q, theta, buckets) per demand scenario,
         scenarios from forecast.sample_demand (seed 11)
Defaults reproduce the logged runs: point = cmp_L3_point_greedy (300 s), saa =
cmp_L3_saa_up_greedy_20 (N = 20, 900 s), both at gap 0.5 %.

Solver: Gurobi by default because it closes the L3 gaps much faster. If gurobipy or a
license is missing, it falls back to HiGHS (open source) and says so. Gurobi is not in
requirements.txt. Seeds are fixed; with Gurobi the run is deterministic for a fixed machine
and thread count, and a time limit that binds can still give a slightly different plan.

Afterwards the plan is checked for validity (R5, our own check, independent of the model)
and scored with our scorer on the evaluation scenarios (seed 2026) against do-nothing and
the baseline. The script exits with code 1 if the plan is invalid.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fleetkit import baseline_plan, load_instance, write_plan  # noqa: E402
from fleetopt import forecast  # noqa: E402
from fleetopt.evaluate import check_validity, committed_revenue, compare_plans  # noqa: E402
from fleetopt.model_base import solve_plan  # noqa: E402
from fleetopt.solvers import pick_solver  # noqa: E402

MODEL_ID = "M1"
SAA_SEED, EVAL_SEED = 11, 2026
DEFAULT_TIME = {"point": 300.0, "saa": 900.0}
PLAN_COLUMNS = ["action", "date", "category", "station_id", "to_station_id", "mode", "cars"]


def build_kwargs(inst, objective: str, n_saa: int) -> dict:
    """solve_plan keyword arguments for the chosen revenue objective (both with upgrades)."""
    if objective == "point":
        return {"upgrades": True}
    sc = forecast.sample_demand(inst, n_saa, seed=SAA_SEED)
    tables = [g[["station_id", "category", "day", "demand"]] for _, g in sc.groupby("scenario")]
    return {"upgrades": True, "scenarios": tables}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--objective", choices=("point", "saa"), default="point")
    ap.add_argument("--solver", default="gurobi", help="gurobi (default, falls back to highs), highs or cbc")
    ap.add_argument("--time-limit", type=float, default=None, help="seconds; default 300 (point) or 900 (saa)")
    ap.add_argument("--gap", type=float, default=0.005, help="relative MIP gap")
    ap.add_argument("--saa-scenarios", type=int, default=20, help="number of SAA scenarios (saa only)")
    ap.add_argument("--out", type=Path, default=Path("plans/final.csv"), help="relative to Project_4/")
    ap.add_argument("--eval-scenarios", type=int, default=500, help="0 skips the scoring")
    ap.add_argument("--msg", action="store_true", help="show the solver log")
    args = ap.parse_args()

    solver = pick_solver(args.solver)
    time_limit = args.time_limit or DEFAULT_TIME[args.objective]
    out = args.out if args.out.is_absolute() else PROJECT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    inst = load_instance(data_dir=PROJECT / "data")
    df_mean, df_base = forecast.model_inputs(inst)
    kw = build_kwargs(inst, args.objective, args.saa_scenarios)
    print(f"{MODEL_ID} L3, objective={args.objective}, exact greedy, solver={solver}, "
          f"time limit {time_limit:.0f} s, gap {args.gap}"
          + (f", {args.saa_scenarios} SAA scenarios (seed {SAA_SEED})" if args.objective == "saa" else ""))

    t0 = time.time()
    run = solve_plan(inst, df_mean, df_base, modes=("driver", "truck"), solver=solver,
                     time_limit=time_limit, gap_rel=args.gap, exact_greedy=True, msg=args.msg, **kw)
    secs = time.time() - t0
    write_plan(df_plan=run.plan, path=out)
    info = {"model": MODEL_ID, "level": 3, "objective": args.objective, "exact_greedy": True,
            "solver": solver, "status": run.status, "secs": round(secs), "time_limit": time_limit,
            "gap_target": args.gap, "gap": run.extra["gap_rel"], "best_bound": run.extra["best_bound"],
            "objective_value": run.objective, "model_profit": run.objective + committed_revenue(inst),
            "n_saa": args.saa_scenarios if args.objective == "saa" else None, "saa_seed": SAA_SEED}
    out.with_suffix(".json").write_text(json.dumps(info, indent=1))
    print(f"wrote {out}: status {run.status}, {secs:.0f} s, gap {run.extra['gap_rel']}, "
          f"model profit {info['model_profit']:,.0f}")

    errors = check_validity(inst, run.plan)
    if errors:
        print(f"INVALID: {len(errors)} violations, e.g. {errors[:3]}")
        sys.exit(1)
    print("valid (our R5 check): fleet >= committed in every cell, caps and format OK")

    if args.eval_scenarios > 0:
        plans = {"plan": run.plan, "baseline": baseline_plan(instance=inst),
                 "do_nothing": pd.DataFrame(columns=PLAN_COLUMNS)}
        scen = forecast.sample_demand(inst, args.eval_scenarios, seed=EVAL_SEED)
        table = compare_plans(inst, plans, scen, df_base, reference="plan")
        pd.set_option("display.width", 200, "display.max_columns", 20)
        print(f"\nour scorer, {args.eval_scenarios} evaluation scenarios (seed {EVAL_SEED}), EUR:")
        cols = ["profit", "se", "vs_plan", "diff_se", "new_rev", "holding", "addition", "transfer",
                "added", "removed", "transferred"]
        print(table[cols].astype(float).round(0).to_string())


if __name__ == "__main__":
    main()
