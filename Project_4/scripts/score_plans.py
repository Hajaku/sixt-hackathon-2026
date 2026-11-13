"""Score plans with our scorer: validity plus profit on seeded demand scenarios.

Usage: Project_4/.venv/bin/python Project_4/scripts/score_plans.py plans/do_nothing.csv plans/baseline.csv
       [--scenarios 200] [--seed 2026] [--no-booking-update]

All plans are scored on the same scenarios (common random numbers), so differences between plans
come with a paired standard error. The first plan is the reference for the differences.
Also prints the profit on the expected demand (one deterministic scenario) for comparison.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fleetkit import load_instance  # noqa: E402
from fleetopt import forecast  # noqa: E402
from fleetopt.evaluate import check_validity, read_plan, score_plan, summarize  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plans", nargs="+", type=Path)
    ap.add_argument("--scenarios", type=int, default=200)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-booking-update", action="store_true")
    args = ap.parse_args()
    update = not args.no_booking_update

    inst = load_instance(data_dir=PROJECT / "data")
    df_mean, df_base = forecast.model_inputs(inst, booking_update=update)
    scen = forecast.sample_demand(inst, args.scenarios, seed=args.seed, booking_update=update)

    rows, profits = [], {}
    for path in args.plans:
        plan = read_plan(path if path.is_absolute() else Path.cwd() / path)
        errors = check_validity(inst, plan)
        per_scenario = score_plan(inst, plan, scen, df_base)
        s = summarize(per_scenario)
        det = score_plan(inst, plan, df_mean, df_base).iloc[0]
        profits[path.name] = per_scenario["profit"].to_numpy()
        rows.append({"plan": path.name, "valid": not errors, "profit": s["profit"], "se": s["profit_se"],
                     "profit_at_E[D]": det["profit"], "committed_rev": s["committed_revenue"],
                     "new_rev": s["new_revenue"], "holding": s["holding_cost"], "addition": s["addition_cost"],
                     "transfer": s["transfer_cost"], "added": int(s["cars_added"]), "removed": int(s["cars_removed"]),
                     "transferred": int(s["cars_transferred"])})
        if errors:
            print(f"{path.name}: INVALID, {len(errors)} violations, e.g. {errors[0]}")

    table = pd.DataFrame(rows).set_index("plan")
    ref = args.plans[0].name
    diff = {k: v - profits[ref] for k, v in profits.items()}
    table[f"vs {ref}"] = [diff[k].mean() for k in table.index]
    table["diff_se"] = [diff[k].std(ddof=1) / np.sqrt(len(diff[k])) for k in table.index]
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(f"{args.scenarios} scenarios, seed {args.seed}, booking update {'on' if update else 'off'}; "
          f"money in EUR, profit = mean over scenarios, se = its standard error")
    print(table.astype({c: float for c in table.columns if c != "valid"}).round(0).to_string())


if __name__ == "__main__":
    main()
