"""Wait-and-see bound: one plan optimized per scenario, as if its demand were known in advance.

For each of the N scenarios (same seed as insample_bound.py) solve the L3 model with exact greedy
on that single scenario. The mean of these optima is the wait-and-see value WS; any plan's mean
profit on the sample is below it, so EVPI on the sample = WS - (best here-and-now profit).
Gurobi's best bounds give an upper bound on WS when a solve stops at its time limit.

Usage: Project_4/.venv/bin/python Project_4/scripts/wait_and_see.py [--seed 777] [--n 10]
       [--time-limit 45] [--gap 0.005] [--solver gurobi]
"""

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fleetkit import load_instance  # noqa: E402
from fleetopt import forecast  # noqa: E402
from fleetopt.evaluate import committed_revenue, score_plan  # noqa: E402
from fleetopt.model_base import solve_plan  # noqa: E402
from fleetopt.solvers import pick_solver  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--time-limit", type=float, default=45)
    ap.add_argument("--gap", type=float, default=0.005)
    ap.add_argument("--solver", default="gurobi")
    args = ap.parse_args()

    inst = load_instance(data_dir=PROJECT / "data")
    df_mean, df_base = forecast.model_inputs(inst)
    scen = forecast.sample_demand(inst, args.n, seed=args.seed)
    committed = committed_revenue(inst)
    solver = pick_solver(args.solver)

    rows = []
    for sid, g in scen.groupby("scenario"):
        t0 = time.time()
        table = g[["station_id", "category", "day", "demand"]]
        run = solve_plan(inst, df_mean, df_base, modes=("driver", "truck"), solver=solver,
                         time_limit=args.time_limit, gap_rel=args.gap, exact_greedy=True,
                         upgrades=True, scenarios=[table])
        scored = score_plan(inst, run.plan, g, df_base)["profit"].iloc[0]   # the scorer on this scenario
        row = {"scenario": int(sid), "status": run.status, "secs": round(time.time() - t0),
               "gap": run.extra["gap_rel"], "model_profit": run.objective + committed,
               "bound_profit": (run.extra["best_bound"] or float("nan")) + committed, "scored_profit": scored}
        rows.append(row)
        print(json.dumps(row), flush=True)

    ws = sum(r["scored_profit"] for r in rows) / len(rows)
    ws_ub = sum(r["bound_profit"] for r in rows) / len(rows)
    out = {"seed": args.seed, "n": args.n, "ws_scored": ws, "ws_bound": ws_ub, "rows": rows}
    (PROJECT / "plans" / f"wait_and_see_seed{args.seed}_n{args.n}.json").write_text(json.dumps(out, indent=1))
    print(f"WS (scored) {ws:,.0f}   WS upper bound {ws_ub:,.0f}")


if __name__ == "__main__":
    main()
