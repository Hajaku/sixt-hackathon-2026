"""Compare revenue objectives of the fleet MIP: classic SAA vs. expected-revenue curves.

Solve one variant (can run in parallel, one process per variant):
    Project_4/.venv/bin/python Project_4/scripts/compare_objectives.py solve VARIANT [--level 1]
        [--saa-scenarios 10] [--more-scenarios 500] [--time-limit 600] [--gap 0.005]
Score every solved variant of a level, plus do-nothing and baseline, on common scenarios:
    Project_4/.venv/bin/python Project_4/scripts/compare_objectives.py score [--level 1] [--eval-scenarios 500]

Variants (Project Plan section 3; Notes/Models/M2 Expected-revenue curves.md):
  point            M1: price-factor buckets at the point forecast E[D], with upgrades
  saa_up           classic SAA over the SAA scenarios: per-scenario serving + buckets, with upgrades
  saa              classic SAA, no upgrades
  curves_same      expected-revenue curves from the SAA scenarios, exact kinks, no upgrades (= saa)
  curves_more      curves from many more scenarios (20-segment grid), no upgrades
  curves_up_same   curves from the SAA scenarios (exact kinks), with M1's upgrade split (approximate)
  curves_up_more   curves from many more scenarios (20-segment grid), with the upgrade split
Scenario seeds: SAA 11, more 12, evaluation 2026, so no plan is scored on its own scenarios.
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
from fleetopt import fares, forecast  # noqa: E402
from fleetopt.evaluate import compare_plans, read_plan  # noqa: E402
from fleetopt.model_base import solve_plan  # noqa: E402

SAA_SEED, MORE_SEED, EVAL_SEED = 11, 12, 2026
VARIANTS = ["point", "saa_up", "saa", "curves_same", "curves_more", "curves_up_same", "curves_up_more"]
MODES = {1: (), 2: ("driver",), 3: ("driver", "truck")}


def setup(inst, variant: str, df_base: pd.DataFrame, n_saa: int, n_more: int) -> dict:
    """solve_plan keyword arguments for a variant."""
    if variant == "point":
        return {"upgrades": True}
    if variant.startswith("saa"):
        sc = forecast.sample_demand(inst, n_saa, seed=SAA_SEED)
        tables = [g[["station_id", "category", "day", "demand"]] for _, g in sc.groupby("scenario")]
        return {"scenarios": tables, "upgrades": variant == "saa_up"}
    same = variant.endswith("_same")
    sc = forecast.sample_demand(inst, n_saa if same else n_more, seed=SAA_SEED if same else MORE_SEED)
    curves = (fares.expected_revenue_curves(inst, sc, df_base, max_segments=None, concave_tol=1e-6) if same
              else fares.expected_revenue_curves(inst, sc, df_base))
    return {"buckets": curves, "upgrades": variant.startswith("curves_up")}


def solve(args) -> None:
    inst = load_instance(data_dir=PROJECT / "data")
    df_mean, df_base = forecast.model_inputs(inst)
    kw = setup(inst, args.variant, df_base, args.saa_scenarios, args.more_scenarios)
    t0 = time.time()
    run = solve_plan(inst, df_mean, df_base, modes=MODES[args.level], solver=args.solver,
                     time_limit=args.time_limit, gap_rel=args.gap, exact_greedy=args.exact_greedy, **kw)
    suffix = "_greedy" if args.exact_greedy else ""
    stem = PROJECT / "plans" / f"cmp_L{args.level}_{args.variant}{suffix}"
    write_plan(df_plan=run.plan, path=stem.with_suffix(".csv"))
    info = {"variant": args.variant, "level": args.level, "status": run.status, "secs": round(time.time() - t0),
            "objective": run.objective, "best_bound": run.extra["best_bound"], "gap": run.extra["gap_rel"],
            "exact_greedy": args.exact_greedy, "solver": args.solver, "n_saa": args.saa_scenarios, "n_more": args.more_scenarios, "time_limit": args.time_limit}
    stem.with_suffix(".json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info))


def score(args) -> None:
    inst = load_instance(data_dir=PROJECT / "data")
    _, df_base = forecast.model_inputs(inst)
    plans = {"do_nothing": read_plan(PROJECT / "plans" / "do_nothing.csv"),
             "baseline": read_plan(PROJECT / "plans" / "baseline.csv")}
    infos = {}
    for v in VARIANTS:
        stem = PROJECT / "plans" / f"cmp_L{args.level}_{v}"
        if stem.with_suffix(".json").exists():
            plans[v] = read_plan(stem.with_suffix(".csv"))
            infos[v] = json.loads(stem.with_suffix(".json").read_text())
    scen = forecast.sample_demand(inst, args.eval_scenarios, seed=EVAL_SEED)
    table = compare_plans(inst, plans, scen, df_base, reference="point" if "point" in plans else None)
    committed = __import__("fleetopt.evaluate", fromlist=["committed_revenue"]).committed_revenue(inst)
    info = pd.DataFrame.from_dict(infos, orient="index")
    if len(info):
        info["model_profit"] = info["objective"] + committed
        table = table.join(info[["status", "secs", "gap", "model_profit"]])
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(f"L{args.level}: {args.eval_scenarios} evaluation scenarios (seed {EVAL_SEED})")
    num = [c for c in table.columns if c not in ("valid", "status")]
    print(table.astype({c: float for c in num}).round({c: 0 for c in num if c != "gap"} | {"gap": 4}).to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("solve")
    s.add_argument("variant", choices=VARIANTS)
    s.add_argument("--level", type=int, default=1, choices=(1, 2, 3))
    s.add_argument("--solver", default="highs")
    s.add_argument("--time-limit", type=float, default=600.0)
    s.add_argument("--gap", type=float, default=0.005)
    s.add_argument("--saa-scenarios", type=int, default=10)
    s.add_argument("--more-scenarios", type=int, default=500)
    s.add_argument("--exact-greedy", action="store_true",
                   help="R7 greedy own-first via binaries theta (exact, slower); plan file gets suffix _greedy")
    c = sub.add_parser("score")
    c.add_argument("--level", type=int, default=1, choices=(1, 2, 3))
    c.add_argument("--eval-scenarios", type=int, default=500)
    args = ap.parse_args()
    solve(args) if args.cmd == "solve" else score(args)


if __name__ == "__main__":
    main()
