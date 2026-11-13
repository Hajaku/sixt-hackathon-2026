"""Plan effects (R4) and the validity check (R5)."""

import pandas as pd

from fleetopt.evaluate import check_validity, read_plan
from fleetopt.level0 import fleet_with_plan, horizon_dates, level0_table, max_removable, plan_deltas


def make_plan(*rows: dict) -> pd.DataFrame:
    cols = ["action", "date", "category", "station_id", "to_station_id", "mode", "cars"]
    return pd.DataFrame([{c: r.get(c) for c in cols} for r in rows], columns=cols)


def date(inst, day: int) -> str:
    return str(horizon_dates(inst)[day - 1].date())


def pair_with_lead(inst, lead: int) -> tuple[str, str]:
    row = inst.distances[inst.distances["lead_time_days"] == lead].iloc[0]
    return row["from_station_id"], row["to_station_id"]


def test_reference_plans_are_valid(inst, project):
    for name in ("do_nothing.csv", "baseline.csv"):
        assert check_validity(inst, read_plan(project / "plans" / name)) == [], name


def test_empty_plan_equals_do_nothing(inst):
    t = fleet_with_plan(inst, make_plan())
    assert (t["station_fleet"] == level0_table(inst)["station_fleet"]).all()


def test_removal_from_zero_slack_cell_is_invalid(inst):
    t = level0_table(inst)
    t["max_removable"] = max_removable(t)
    cell = t[(t["day"] == 1) & (t["max_removable"] == 0)].iloc[0]
    plan = make_plan(dict(action="remove", date=date(inst, 1), category=cell.category,
                          station_id=cell.station_id, cars=1))
    errors = check_validity(inst, plan)
    assert errors and all("fleet" in e for e in errors)


def test_removal_within_slack_is_valid(inst):
    t = level0_table(inst)
    t["max_removable"] = max_removable(t)
    cell = t[(t["day"] == 3) & (t["max_removable"] >= 2)].iloc[0]
    plan = make_plan(dict(action="remove", date=date(inst, 3), category=cell.category,
                          station_id=cell.station_id, cars=2))
    assert check_validity(inst, plan) == []


def test_cap_exceeded(inst):
    cap = int(inst.categories.set_index("category").loc["economy", "addition_cap"])
    plan = make_plan(dict(action="add", date=date(inst, 1), category="economy", station_id="S01", cars=cap),
                     dict(action="add", date=date(inst, 5), category="economy", station_id="S02", cars=1))
    errors = check_validity(inst, plan)
    assert errors == [f"economy: add {cap + 1} cars > addition_cap {cap}"]


def test_format_errors(inst):
    plan = make_plan(
        dict(action="transfer", date=date(inst, 1), category="economy", station_id="S01",
             to_station_id="S01", mode="driver", cars=1),
        dict(action="add", date="2027-02-28", category="economy", station_id="S01", cars=1),
        dict(action="add", date=date(inst, 1), category="luxury", station_id="S99", cars=0),
        dict(action="transfer", date=date(inst, 1), category="economy", station_id="S01",
             to_station_id="S02", mode="boat", cars=1),
    )
    text = "\n".join(check_validity(inst, plan))
    for needle in ("own station", "not inside the horizon", "unknown category", "unknown station",
                   "integer >= 1", "unknown transfer mode"):
        assert needle in text, needle


def test_transfer_timing(inst):
    """Leaves on d, in transit d..d+lead-1, arrives on d+lead; an arrival after day 14 never lands."""
    a, b = pair_with_lead(inst, 1)
    c, e = pair_with_lead(inst, 2)
    plan = make_plan(
        dict(action="transfer", date=date(inst, 3), category="premium", station_id=a,
             to_station_id=b, mode="driver", cars=2),
        dict(action="transfer", date=date(inst, 3), category="premium", station_id=a,
             to_station_id=b, mode="driver", cars=1),  # identical rows add up
        dict(action="transfer", date=date(inst, 13), category="premium", station_id=c,
             to_station_id=e, mode="truck", cars=4),
    )
    d = plan_deltas(inst, plan).set_index(["station_id", "category", "day"])
    assert d.loc[(a, "premium", 3), "transfer_out"] == 3
    assert d.loc[(b, "premium", 4), "transfer_in"] == 3
    assert d.loc[(a, "premium", 3), "in_transit"] == 3
    assert d.loc[(a, "premium", 4), "in_transit"] == 0
    assert d.loc[(c, "premium", 13), "transfer_out"] == 4
    assert d.loc[(c, "premium", 13), "in_transit"] == 4
    assert d.loc[(c, "premium", 14), "in_transit"] == 4
    assert d["transfer_in"].sum() == 3  # the day-13 truck (lead 2) arrives on day 15
    assert d["in_transit"].sum() == 3 * 1 + 4 * 2

    t = fleet_with_plan(inst, plan).set_index(["station_id", "category", "day"])
    base = level0_table(inst).set_index(["station_id", "category", "day"])["station_fleet"]
    diff = t["station_fleet"] - base
    assert diff.loc[(a, "premium", 2)] == 0 and diff.loc[(a, "premium", 3)] == -3
    assert diff.loc[(b, "premium", 3)] == 0 and diff.loc[(b, "premium", 4)] == 3
    assert diff.loc[(e, "premium", 14)] == 0
