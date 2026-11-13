"""M1: solve the full fleet MIP and write a plan.

Usage: python Project_4/scripts/run_m1.py [--level 1|2|3] [--solver highs] [--time-limit 120]
       [--gap 0.01] [--max-km 120] [--out plans/m1.csv]

The forecast is the README's simple first one (a placeholder until fleetopt/forecast.py):
mean cars on rent per (station, category, weekday) from the history of completed + open
rentals, minus the committed car-days; base revenue = revenue per car-day of the completed
rentals per (station, category).
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fleetkit import load_instance, write_plan  # noqa: E402
from fleetopt import level0  # noqa: E402
from fleetopt.evaluate import check_validity  # noqa: E402
from fleetopt.model_base import committed_revenue, solve_plan  # noqa: E402

LEFT_CENSOR_DAYS = 9  # the first days of the history miss rentals that started before it


def naive_forecast(inst) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(df_demand, df_base) on the cell grid: README first forecast + base revenue."""
    day1 = level0.horizon_dates(inst)[0]
    r = inst.reservations[inst.reservations["status"].isin(["completed", "open"])].copy()
    r["last"] = r["return_date"].clip(upper=day1 - pd.Timedelta(days=1))
    lengths = (r["last"] - r["pickup_date"]).dt.days + 1
    occ = r.loc[r.index.repeat(lengths)].copy()
    occ["date"] = occ["pickup_date"].to_numpy() + np.concatenate(
        [np.arange(n) for n in lengths]
    ).astype("timedelta64[D]")
    occ = occ[occ["date"] >= occ["date"].min() + np.timedelta64(LEFT_CENSOR_DAYS, "D")]
    per_day = occ.groupby(["pickup_station_id", "category", "date"]).size().rename("on_rent").reset_index()
    per_day["weekday"] = pd.to_datetime(per_day["date"]).dt.day_of_week
    mean_on_rent = (
        per_day.groupby(["pickup_station_id", "category", "weekday"])["on_rent"]
        .mean()
        .rename("mean_on_rent")
        .reset_index()
        .rename(columns={"pickup_station_id": "station_id"})
    )

    t = level0.cell_grid(inst).merge(
        level0.committed_car_days(inst)[level0.KEY + ["committed_car_days"]], on=level0.KEY
    )
    t["weekday"] = t["date"].dt.day_of_week
    t = t.merge(mean_on_rent, on=["station_id", "category", "weekday"], how="left")
    t["mean_on_rent"] = t["mean_on_rent"].fillna(0.0)
    t["demand"] = np.clip(t["mean_on_rent"] - t["committed_car_days"], 0.0, None)
    df_demand = t[level0.KEY + ["demand"]]

    c = inst.reservations[inst.reservations["status"] == "completed"].copy()
    c["car_days"] = (c["return_date"] - c["pickup_date"]).dt.days + 1
    agg = c.groupby(["pickup_station_id", "category"]).agg(rev=("revenue", "sum"), cd=("car_days", "sum"))
    base = (
        (agg["rev"] / agg["cd"])
        .rename("base_revenue")
        .reset_index()
        .rename(columns={"pickup_station_id": "station_id"})
    )
    grid = level0.cell_grid(inst)[["station_id", "category"]].drop_duplicates()
    df_base = grid.merge(base, on=["station_id", "category"], how="left").fillna({"base_revenue": 0.0})
    return df_demand, df_base


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--solver", default="highs", choices=("highs", "cbc", "gurobi"))
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--gap", type=float, default=0.01)
    parser.add_argument("--max-km", type=float, default=None, help="prune transfer arcs longer than this")
    parser.add_argument("--exact-greedy", action="store_true", help="R7 greedy via binaries (slow)")
    parser.add_argument("--out", default="plans/m1.csv")
    args = parser.parse_args()

    inst = load_instance(data_dir=PROJECT / "data")
    df_demand, df_base = naive_forecast(inst)

    modes = {1: (), 2: ("driver",), 3: ("driver", "truck")}[args.level]
    arcs = None
    if args.max_km is not None:
        d = inst.distances
        arcs = [(f, t) for f, t, km in zip(d["from_station_id"], d["to_station_id"], d["distance_km"]) if km <= args.max_km]

    run = solve_plan(
        inst, df_demand, df_base, modes=modes, arcs=arcs,
        solver=args.solver, time_limit=args.time_limit, gap_rel=args.gap,
        exact_greedy=args.exact_greedy,
    )
    out = PROJECT / args.out
    write_plan(df_plan=run.plan, path=out)
    errors = check_validity(inst, run.plan)

    b = run.breakdown
    profit = sum(b.values()) + committed_revenue(inst)
    print(f"{run.extra['model_id']} L{args.level} [{args.solver}]: {run.status}, objective {run.objective:,.0f}")
    print(
        "plan:", ", ".join(
            f"{a} {int(run.plan.loc[run.plan['action'] == a, 'cars'].sum()) if len(run.plan) else 0}"
            for a in ("add", "remove", "transfer")
        )
    )
    print(
        f"revenue {b['new_revenue']:,.0f} | holding {b['holding_fleet'] + b['holding_transit']:,.0f}"
        f" | add {b['addition']:,.0f} | driver {b['driver']:,.0f} | truck {b['truck']:,.0f}"
    )
    print(f"+ committed {committed_revenue(inst):,.0f}  =>  model profit est. {profit:,.0f}")
    print(f"validity: {'VALID' if not errors else 'INVALID'} -> {out}")
    for e in errors[:10]:
        print("  " + e)


if __name__ == "__main__":
    main()
