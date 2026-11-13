"""Classic SAA of the fleet MIP on bootstrap scenarios (history weeks replayed) instead of
the parametric demand model of `fleetopt.forecast.sample_demand`.

Solve (one process per variant, can run in parallel):
    Project_4/.venv/bin/python Project_4/scripts/run_saa_bootstrap.py solve [--level 1]
        [--scenarios 10] [--seed 21] [--block network|cell] [--no-upgrades]
        [--time-limit 600] [--gap 0.005] [--solver highs]
    -> plans/cmp_L<level>_saa_boot[_cell][_noup].csv + .json
Score every plans/cmp_L<level>_*.csv plan, plus do-nothing and baseline, on two test sets:
    Project_4/.venv/bin/python Project_4/scripts/run_saa_bootstrap.py score [--level 1] [--eval-scenarios 500]
  param  forecast.sample_demand, seed 2026 (same set as compare_objectives.py score)
  boot   all 64 network week pairs: the exact bootstrap distribution. In-sample for the bootstrap
         plans (their SAA scenarios are some of these 64), so read it as a check, not a contest.

Model: M1 with `scenarios=` (classic SAA, as variant saa_up / saa of compare_objectives.py);
only the scenario generator differs (fleetopt/bootstrap.py). Base revenue and the point forecast
handed to the model (used for reporting only under SAA) are unchanged.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fleetkit import load_instance, write_plan  # noqa: E402
from fleetopt import bootstrap, forecast  # noqa: E402
from fleetopt.evaluate import check_validity, committed_revenue, compare_plans, read_plan  # noqa: E402
from fleetopt.model_base import MODEL_ID, solve_plan  # noqa: E402

EVAL_SEED = 2026          # parametric test set, shared with compare_objectives.py
MODES = {1: (), 2: ("driver",), 3: ("driver", "truck")}


def variant_name(block: str, upgrades: bool) -> str:
    return "saa_boot" + ("_cell" if block == "cell" else "") + ("" if upgrades else "_noup")


def solve(args) -> None:
    inst = load_instance(data_dir=PROJECT / "data")
    df_mean, df_base = forecast.model_inputs(inst)
    sc = bootstrap.bootstrap_demand(inst, args.scenarios, seed=args.seed, block=args.block)
    tables = [g[["station_id", "category", "day", "demand"]] for _, g in sc.groupby("scenario")]
    t0 = time.time()
    run = solve_plan(inst, df_mean, df_base, modes=MODES[args.level], solver=args.solver,
                     time_limit=args.time_limit, gap_rel=args.gap, msg=args.msg,
                     scenarios=tables, upgrades=not args.no_upgrades)
    variant = variant_name(args.block, not args.no_upgrades) + ("" if args.solver == "highs" else f"_{args.solver}")
    stem = PROJECT / "plans" / f"cmp_L{args.level}_{variant}"
    write_plan(df_plan=run.plan, path=stem.with_suffix(".csv"))
    errors = check_validity(inst, read_plan(stem.with_suffix(".csv")))   # check what was written
    info = {"variant": variant, "model_id": MODEL_ID, "level": args.level, "status": run.status,
            "secs": round(time.time() - t0), "objective": run.objective,
            "best_bound": run.extra.get("best_bound"), "gap": run.extra.get("gap_rel"),
            "scenarios": "bootstrap", "block": args.block, "n_saa": args.scenarios, "seed": args.seed,
            "upgrades": not args.no_upgrades, "solver": args.solver, "time_limit": args.time_limit,
            "valid": not errors}
    stem.with_suffix(".json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info))
    if errors:
        print("INVALID PLAN:\n  " + "\n  ".join(errors[:20]), file=sys.stderr)
        sys.exit(1)


def score(args) -> None:
    inst = load_instance(data_dir=PROJECT / "data")
    _, df_base = forecast.model_inputs(inst)
    plans = {"do_nothing": read_plan(PROJECT / "plans" / "do_nothing.csv"),
             "baseline": read_plan(PROJECT / "plans" / "baseline.csv")}
    infos = {}
    for csv in sorted((PROJECT / "plans").glob(f"cmp_L{args.level}_*.csv")):   # solve info only if a .json exists
        v = csv.stem.removeprefix(f"cmp_L{args.level}_")
        plans[v] = read_plan(csv)
        if csv.with_suffix(".json").exists():
            infos[v] = json.loads(csv.with_suffix(".json").read_text())
    ref = "point" if "point" in plans else None
    info = pd.DataFrame.from_dict(infos, orient="index")
    if len(info):
        info["model_profit"] = info["objective"] + committed_revenue(inst)
    test_sets = {
        f"param ({args.eval_scenarios} scen., seed {EVAL_SEED})":
            forecast.sample_demand(inst, args.eval_scenarios, seed=EVAL_SEED),
        "boot (all 64 week pairs)": bootstrap.all_week_pairs(inst),
    }
    pd.set_option("display.width", 250, "display.max_columns", 30)
    for name, scen in test_sets.items():
        table = compare_plans(inst, plans, scen, df_base, reference=ref)
        if len(info):
            table = table.join(info[[c for c in ("status", "secs", "gap", "model_profit") if c in info]])
        num = [c for c in table.columns if c not in ("valid", "status")]
        print(f"\nL{args.level} on {name}")
        print(table.astype({c: float for c in num}).round({c: 0 for c in num if c != "gap"} | {"gap": 4}).to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("solve")
    s.add_argument("--level", type=int, default=1, choices=(1, 2, 3))
    s.add_argument("--scenarios", type=int, default=10, help="number of bootstrap SAA scenarios")
    s.add_argument("--seed", type=int, default=21, help="bootstrap seed (parametric seeds are 11, 12, 2026)")
    s.add_argument("--block", choices=("network", "cell"), default="network")
    s.add_argument("--no-upgrades", action="store_true")
    s.add_argument("--solver", default="highs")
    s.add_argument("--time-limit", type=float, default=600.0)
    s.add_argument("--gap", type=float, default=0.005)
    s.add_argument("--msg", action="store_true", help="show the solver log")
    c = sub.add_parser("score")
    c.add_argument("--level", type=int, default=1, choices=(1, 2, 3))
    c.add_argument("--eval-scenarios", type=int, default=500)
    args = ap.parse_args()
    solve(args) if args.cmd == "solve" else score(args)


if __name__ == "__main__":
    main()
