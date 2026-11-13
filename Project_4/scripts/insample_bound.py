"""Upper bound from hindsight on a scenario sample: how far are our plans from the best
single plan for exactly these scenarios?

1. Draw N evaluation scenarios (fixed seed, not used to build any plan) and score the given plans.
2. Solve the classic SAA (L3, exact greedy) on exactly these scenarios. Its optimum is the best
   any one plan can do on this sample, and Gurobi's best bound caps that optimum.
The SAA objective is the scorer's profit on these scenarios, so incumbent and bound are in the
same units as the plan scores (committed revenue added).

Usage: Project_4/.venv/bin/python Project_4/scripts/insample_bound.py [--seed 777] [--n 10]
       [--time-limit 600] [--solver gurobi] final_point final_saa_20 ...
"""

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fleetkit import load_instance, write_plan  # noqa: E402
from fleetopt import forecast  # noqa: E402
from fleetopt.evaluate import check_validity, committed_revenue, compare_plans, read_plan  # noqa: E402
from fleetopt.model_base import solve_plan  # noqa: E402
from fleetopt.solvers import pick_solver  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plans", nargs="+", help="plan stems in plans/")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--time-limit", type=float, default=600)
    ap.add_argument("--gap", type=float, default=0.005)
    ap.add_argument("--solver", default="gurobi")
    args = ap.parse_args()

    inst = load_instance(data_dir=PROJECT / "data")
    df_mean, df_base = forecast.model_inputs(inst)
    scen = forecast.sample_demand(inst, args.n, seed=args.seed)
    tables = [g[["station_id", "category", "day", "demand"]] for _, g in scen.groupby("scenario")]
    committed = committed_revenue(inst)

    t0 = time.time()
    run = solve_plan(inst, df_mean, df_base, modes=("driver", "truck"), solver=pick_solver(args.solver),
                     time_limit=args.time_limit, gap_rel=args.gap, exact_greedy=True,
                     upgrades=True, scenarios=tables)
    stem = PROJECT / "plans" / f"insample_saa_seed{args.seed}_n{args.n}"
    write_plan(df_plan=run.plan, path=stem.with_suffix(".csv"))
    info = {"seed": args.seed, "n": args.n, "status": run.status, "secs": round(time.time() - t0),
            "gap": run.extra["gap_rel"], "incumbent_profit": run.objective + committed,
            "bound_profit": (run.extra["best_bound"] or float("nan")) + committed}
    stem.with_suffix(".json").write_text(json.dumps(info, indent=1))

    plans = {n: read_plan(PROJECT / "plans" / f"{n}.csv") for n in args.plans}
    plans["insample_saa"] = run.plan
    table = compare_plans(inst, plans, scen, df_base, reference="insample_saa")
    table["valid_ours"] = [not check_validity(inst, p) for p in plans.values()]
    print(json.dumps(info))
    cols = ["profit", "se", "vs_insample_saa", "diff_se", "added", "removed", "transferred", "valid_ours"]
    print(table[cols].round(0).to_string())


if __name__ == "__main__":
    main()
