"""Our re-implementation of the scorer. For now: plan validity (README Appendix A, R5).

Profit (R6-R11) will be added here later.
"""

from pathlib import Path

import pandas as pd

from fleetkit import Instance
from fleetopt.level0 import date_to_day, fleet_with_plan, n_days

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
