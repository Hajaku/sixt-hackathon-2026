"""Our re-implementation of the scorer (README Appendix A): plan validity (R5) and profit (R6-R11).

Profit is computed for a plan and one or more demand scenarios (the demand to come D per station,
category and day, e.g. from `fleetopt.forecast.sample_demand`). The code follows the README rules
directly and shares nothing with the MIP in `model_base.py`, so it can check the model's plans.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from fleetkit import Instance
from fleetopt.level0 import active_rentals, categories_in_order, date_to_day, fleet_with_plan, n_days, plan_deltas

PLAN_COLUMNS = ["action", "date", "category", "station_id", "to_station_id", "mode", "cars"]


def read_plan(path: Path) -> pd.DataFrame:
    """Read a plan CSV as written by fleetkit.write_plan (header-only file = do-nothing plan)."""
    plan = pd.read_csv(path, dtype={"to_station_id": "string", "mode": "string", "station_id": "string"})
    missing = set(PLAN_COLUMNS) - set(plan.columns)
    if missing:
        raise ValueError(f"plan {path} misses columns {sorted(missing)}")
    return plan[PLAN_COLUMNS]


def _is_blank(value: object) -> bool:
    """True for an empty CSV cell (NaN, None, pd.NA or whitespace)."""
    return value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def check_plan_format(inst: Instance, plan: pd.DataFrame) -> list[str]:
    """R5, third bullet: ids, categories, dates, modes, car counts, no self-transfer."""
    errors: list[str] = []
    plan = plan.reset_index(drop=True)
    stations = set(inst.stations["station_id"])
    categories = set(inst.categories["category"])
    pairs = set(zip(inst.distances["from_station_id"], inst.distances["to_station_id"]))
    days = date_to_day(inst, pd.to_datetime(plan["date"], errors="coerce"))
    cars = pd.to_numeric(plan["cars"], errors="coerce")

    for i, row in plan.iterrows():
        where = f"row {i + 2}"  # +2: header line and 1-based line numbers, as in the CSV file
        if row["action"] not in ("add", "remove", "transfer"):
            errors.append(f"{where}: unknown action {row['action']!r}")
        if pd.isna(days[i]) or not 1 <= days[i] <= n_days(inst):
            errors.append(f"{where}: date {row['date']!r} is not inside the horizon")
        if row["category"] not in categories:
            errors.append(f"{where}: unknown category {row['category']!r}")
        if row["station_id"] not in stations:
            errors.append(f"{where}: unknown station {row['station_id']!r}")
        if pd.isna(cars[i]) or cars[i] != int(cars[i]) or cars[i] < 1:
            errors.append(f"{where}: cars must be an integer >= 1, got {row['cars']!r}")
        if row["action"] == "transfer":
            if row["mode"] not in ("driver", "truck"):
                errors.append(f"{where}: unknown transfer mode {row['mode']!r}")
            if row["to_station_id"] == row["station_id"]:
                errors.append(f"{where}: transfer to its own station {row['station_id']}")
            elif row["to_station_id"] not in stations:
                errors.append(f"{where}: unknown destination {row['to_station_id']!r}")
            elif (row["station_id"], row["to_station_id"]) not in pairs:
                errors.append(f"{where}: no distance for {row['station_id']} -> {row['to_station_id']}")
        elif row["action"] in ("add", "remove"):
            if not (_is_blank(row["to_station_id"]) and _is_blank(row["mode"])):
                errors.append(f"{where}: to_station_id and mode must be empty for {row['action']}")
    return errors


def check_caps(inst: Instance, plan: pd.DataFrame) -> list[str]:
    """R5, second bullet: additions <= addition_cap and removals <= removal_cap per category."""
    errors: list[str] = []
    for _, cat in inst.categories.iterrows():
        k = cat["category"]
        for action, cap_col in (("add", "addition_cap"), ("remove", "removal_cap")):
            total = int(plan.loc[(plan["action"] == action) & (plan["category"] == k), "cars"].sum())
            if total > cat[cap_col]:
                errors.append(f"{k}: {action} {total} cars > {cap_col} {cat[cap_col]}")
    return errors


def check_fleet(inst: Instance, plan: pd.DataFrame) -> list[str]:
    """R5, first bullet: station fleet >= committed car-days in every cell."""
    t = fleet_with_plan(inst, plan)
    bad = t[t["slack"] < 0]
    return [
        f"{r.station_id} {r.category} {r.date.date()}: fleet {r.station_fleet} < committed {r.committed_car_days}"
        for r in bad.itertuples()
    ]


def check_validity(inst: Instance, plan: pd.DataFrame) -> list[str]:
    """All of R5. Returns the violations as readable lines; an empty list means the plan is valid.

    If the format is broken, the fleet and cap checks are skipped (they would be meaningless).
    """
    errors = check_plan_format(inst, plan)
    if errors:
        return errors
    return check_caps(inst, plan) + check_fleet(inst, plan)


# --------------------------------------------------------------------------------------------
# Profit (R6-R11)
# --------------------------------------------------------------------------------------------
def fare_revenue(served: np.ndarray, demand: np.ndarray, base: np.ndarray | float,
                 shares: np.ndarray, factors: np.ndarray) -> np.ndarray:
    """R8: revenue of serving `served` of the demand `demand` (car-days) at base revenue `base`.

    Total revenue at share q is q * D * base * pf(q) at the listed shares, linear in the served
    car-days in between, and served * base * pf(0.6) below the first share (a line through 0).
    That is base * D * interp(q) over the points (0, 0), (s_i, s_i * pf_i). D = 0 gives 0.
    """
    served, demand = np.asarray(served, float), np.asarray(demand, float)
    xp = np.concatenate([[0.0], shares])
    fp = np.concatenate([[0.0], shares * factors])
    q = np.divide(served, demand, out=np.zeros_like(served), where=demand > 0)
    return np.where(demand > 0, base * demand * np.interp(q, xp, fp), 0.0)


def serve_demand(demand: np.ndarray, free: np.ndarray) -> np.ndarray:
    """R7: served demand per category, last axis = categories from lowest to highest.

    Own category first: own = min(D, a). The free cars of category k that are left serve the
    unserved demand of category k-1 (one step up only): up[k] = min(a[k] - own[k], D[k-1] - own[k-1]).
    served[k] = own[k] + up[k+1], earning the revenue of the requested category k.
    """
    own = np.minimum(demand, free)
    up = np.minimum(free[..., 1:] - own[..., 1:], demand[..., :-1] - own[..., :-1])
    served = own.copy()
    served[..., :-1] += up
    return served


def _to_array(inst: Instance, df: pd.DataFrame, col: str, scenario_col: str | None = None) -> np.ndarray:
    """Long table (station_id, category, day[, scenario]) -> array (scenario, station, day, category)."""
    stations, cats, days = inst.stations["station_id"].tolist(), categories_in_order(inst), range(1, n_days(inst) + 1)
    scen = sorted(df[scenario_col].unique()) if scenario_col else [0]
    keys = ([scenario_col] if scenario_col else []) + ["station_id", "category", "day"]
    idx = pd.MultiIndex.from_product(([scen] if scenario_col else []) + [stations, cats, days], names=keys)
    vals = df.set_index(keys)[col].reindex(idx, fill_value=0).to_numpy(float)
    return vals.reshape(len(scen), len(stations), len(cats), len(days)).transpose(0, 1, 3, 2)


def committed_revenue(inst: Instance) -> float:
    """R9: each open or booked rental earns revenue * (car-days inside the horizon / all its car-days)."""
    r = active_rentals(inst)
    return float((r["revenue"] * r["car_days_in_horizon"] / r["car_days_total"]).sum())


def plan_costs(inst: Instance, plan: pd.DataFrame) -> dict[str, float]:
    """R10: holding, addition and transfer costs of a plan, plus the action counts."""
    t = fleet_with_plan(inst, plan)
    hold = inst.categories.set_index("category")["holding_cost_per_day"]
    car_days = (t["station_fleet"] + t["in_transit"]).groupby(t["category"]).sum()
    out = {"holding_cost": float((car_days * hold.reindex(car_days.index)).sum())}

    p = plan.copy()
    p["cars"] = p["cars"].astype(int)
    add_cost = inst.categories.set_index("category")["addition_cost_per_car"]
    added = p[p["action"] == "add"]
    out["addition_cost"] = float((added["cars"] * added["category"].map(add_cost)).sum())

    tc = inst.transfer_costs.set_index("mode")
    tr = p[p["action"] == "transfer"].merge(
        inst.distances[["from_station_id", "to_station_id", "distance_km"]],
        left_on=["station_id", "to_station_id"], right_on=["from_station_id", "to_station_id"], how="left")
    drv = tr[tr["mode"] == "driver"]
    out["driver_cost"] = float((drv["cars"] * (tc.loc["driver", "fixed_cost"] + tc.loc["driver", "cost_per_km"] * drv["distance_km"])).sum())
    trk = tr[tr["mode"] == "truck"].groupby(["station_id", "to_station_id", "date", "distance_km"])["cars"].sum().reset_index()
    trucks = np.ceil(trk["cars"] / tc.loc["truck", "capacity"])
    out["truck_cost"] = float((trucks * (tc.loc["truck", "fixed_cost"] + tc.loc["truck", "cost_per_km"] * trk["distance_km"])).sum())
    out["transfer_cost"] = out["driver_cost"] + out["truck_cost"]
    out["cars_added"] = int(added["cars"].sum())
    out["cars_removed"] = int(p.loc[p["action"] == "remove", "cars"].sum())
    out["cars_transferred"] = int(tr["cars"].sum())
    out["trucks"] = int(trucks.sum())
    return out


def new_revenue(inst: Instance, plan: pd.DataFrame, demand: pd.DataFrame, base: pd.DataFrame) -> np.ndarray:
    """R6-R8: revenue of the demand to come, one value per scenario.

    demand: station_id, category, day, demand [, scenario]; base: station_id, category, base_revenue.
    """
    t = fleet_with_plan(inst, plan)
    u = t["station_id"].map(inst.stations.set_index("station_id")["max_utilization"])
    t["free"] = np.maximum(0.0, u * t["station_fleet"] - t["committed_car_days"])          # R6
    free = _to_array(inst, t, "free")[0]                                                    # (station, day, cat)
    D = _to_array(inst, demand, "demand", "scenario" if "scenario" in demand.columns else None)
    served = serve_demand(D, free[None])                                                     # R7

    cats = categories_in_order(inst)
    stype = inst.stations["station_type"].to_numpy()
    b = base.set_index(["station_id", "category"])["base_revenue"]
    pf = inst.price_factors.sort_values("served_share")
    rev = np.zeros(D.shape[0])
    for j, k in enumerate(cats):
        for t_ in np.unique(stype):
            g = pf[(pf["station_type"] == t_) & (pf["category"] == k)]
            rows = np.flatnonzero(stype == t_)
            base_s = np.array([b[(s, k)] for s in inst.stations["station_id"].iloc[rows]])[None, :, None]
            # select the category first: D[:, rows, :, j] would move the station axis to the front
            r = fare_revenue(served[..., j][:, rows], D[..., j][:, rows], base_s,
                             g["served_share"].to_numpy(float), g["price_factor"].to_numpy(float))
            rev += r.sum(axis=(1, 2))
    return rev


def score_plan(inst: Instance, plan: pd.DataFrame, demand: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """R11: profit per scenario with the breakdown of the official .result.md.

    Columns: scenario, valid, committed_revenue, new_revenue, holding_cost, addition_cost,
    transfer_cost, profit, plus the action counts. An invalid plan is still scored (valid = False);
    the official scorer ranks it last.
    """
    valid = not check_validity(inst, plan)
    costs = plan_costs(inst, plan)
    rev = new_revenue(inst, plan, demand, base)
    committed = committed_revenue(inst)
    out = pd.DataFrame({"scenario": np.arange(len(rev)), "valid": valid,
                        "committed_revenue": committed, "new_revenue": rev})
    for c in ["holding_cost", "addition_cost", "transfer_cost"]:
        out[c] = costs[c]
    out["profit"] = out["committed_revenue"] + out["new_revenue"] - out["holding_cost"] - out["addition_cost"] - out["transfer_cost"]
    for c in ["cars_added", "cars_removed", "cars_transferred", "trucks"]:
        out[c] = costs[c]
    return out


def summarize(scores: pd.DataFrame) -> pd.Series:
    """Mean over scenarios, with the standard error of the mean profit."""
    s = scores.drop(columns=["scenario", "valid"]).mean().to_dict()
    s["profit_se"] = scores["profit"].std(ddof=1) / np.sqrt(len(scores)) if len(scores) > 1 else np.nan
    s["valid"] = bool(scores["valid"].all())
    s["scenarios"] = len(scores)
    return pd.Series(s, dtype=object)


def compare_plans(inst: Instance, plans: dict[str, pd.DataFrame], scenarios: pd.DataFrame,
                  base: pd.DataFrame, reference: str | None = None) -> pd.DataFrame:
    """Score several plans on the same scenarios (common random numbers), one row per plan.

    Columns: valid, profit (mean), se, the mean breakdown, action counts, and the difference to
    the reference plan (default: the first) with its paired standard error.
    """
    rows, profit = {}, {}
    for name, plan in plans.items():
        per = score_plan(inst, plan, scenarios, base)
        s = summarize(per)
        profit[name] = per["profit"].to_numpy()
        rows[name] = {"valid": bool(s["valid"]), "profit": s["profit"], "se": s["profit_se"],
                      "new_rev": s["new_revenue"], "holding": s["holding_cost"], "addition": s["addition_cost"],
                      "transfer": s["transfer_cost"], "added": s["cars_added"], "removed": s["cars_removed"],
                      "transferred": s["cars_transferred"]}
    out = pd.DataFrame.from_dict(rows, orient="index")
    ref = reference or next(iter(plans))
    diff = {n: p - profit[ref] for n, p in profit.items()}
    out[f"vs_{ref}"] = [diff[n].mean() for n in out.index]
    out["diff_se"] = [diff[n].std(ddof=1) / np.sqrt(len(diff[n])) if len(diff[n]) > 1 else np.nan for n in out.index]
    return out
