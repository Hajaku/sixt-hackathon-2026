"""Level 0: committed car-days, one-way flows and station fleet per (station, category, day).

Implements README Appendix A, rules R1-R4. Everything here is deterministic: it depends only on
the data, and (for `fleet_with_plan`) on a plan. No forecast.

Conventions used throughout:
- A *cell* is (station_id, category, day). `day` runs 1..14, `date` is the matching calendar date.
- All per-cell tables are long DataFrames on the full grid (stations x categories x days) with
  zeros filled in, sorted by station, category rank, day.
- Plan-independent inputs (committed car-days, one-way flows, initial fleet) are separate from
  the plan effects, so the MIP can use the former as parameters and we can re-check its plan
  with `fleet_with_plan`.
"""

import numpy as np
import pandas as pd

from fleetkit import Instance

KEY = ["station_id", "category", "day"]


# --------------------------------------------------------------------------------------------
# Horizon and grid
# --------------------------------------------------------------------------------------------
def horizon_dates(inst: Instance) -> pd.DatetimeIndex:
    """The dates of day 1 .. day 14."""
    return pd.date_range(inst.horizon["first_date"].iloc[0], inst.horizon["last_date"].iloc[0])


def n_days(inst: Instance) -> int:
    """Number of days in the horizon (14)."""
    return len(horizon_dates(inst))


def date_to_day(inst: Instance, dates: pd.Series) -> pd.Series:
    """Map calendar dates to horizon day numbers (day 1 = first date). Can be < 1 or > 14."""
    first = horizon_dates(inst)[0]
    return (pd.to_datetime(dates) - first).dt.days + 1


def categories_in_order(inst: Instance) -> list[str]:
    """Categories from lowest to highest rank."""
    return inst.categories.sort_values("rank")["category"].tolist()


def cell_grid(inst: Instance) -> pd.DataFrame:
    """All cells: columns station_id, category, day, date."""
    dates = horizon_dates(inst)
    idx = pd.MultiIndex.from_product(
        [inst.stations["station_id"], categories_in_order(inst), range(1, len(dates) + 1)],
        names=KEY,
    )
    grid = idx.to_frame(index=False)
    grid["date"] = dates[grid["day"] - 1]
    return grid


def _count_on_grid(inst: Instance, df: pd.DataFrame, station_col: str, name: str) -> pd.DataFrame:
    """Count rows of `df` per (station_col, category, day) and put the counts on the full grid."""
    counts = (
        df.groupby([station_col, "category", "day"]).size().rename(name).reset_index()
        .rename(columns={station_col: "station_id"})
    )
    out = cell_grid(inst).merge(counts, on=KEY, how="left")
    out[name] = out[name].fillna(0).astype(int)
    return out


# --------------------------------------------------------------------------------------------
# Rentals (R1, R2)
# --------------------------------------------------------------------------------------------
def active_rentals(inst: Instance) -> pd.DataFrame:
    """Open and booked rentals, with horizon day numbers.

    Added columns:
    - pickup_day, return_day: day numbers (pickup_day < 1 for open rentals)
    - first_day, last_day: first and last occupied day inside the horizon (R1)
    - car_days_total, car_days_in_horizon: for the committed revenue share (R9)
    - is_oneway: return station differs from pickup station
    - move_day: day the car changes station for a one-way rental (return_day + 1, R2)
    """
    r = inst.reservations
    r = r[r["status"].isin(["open", "booked"])].copy()
    horizon = n_days(inst)
    r["pickup_day"] = date_to_day(inst, r["pickup_date"])
    r["return_day"] = date_to_day(inst, r["return_date"])
    r["first_day"] = r["pickup_day"].clip(lower=1)
    r["last_day"] = r["return_day"].clip(upper=horizon)
    r["car_days_total"] = r["return_day"] - r["pickup_day"] + 1
    r["car_days_in_horizon"] = (r["last_day"] - r["first_day"] + 1).clip(lower=0)
    r["is_oneway"] = r["pickup_station_id"] != r["return_station_id"]
    r["move_day"] = r["return_day"] + 1
    return r.reset_index(drop=True)


def committed_car_days(inst: Instance) -> pd.DataFrame:
    """R1: cars occupied by open and booked rentals, per pickup station, category and day."""
    r = active_rentals(inst)
    r = r[r["car_days_in_horizon"] > 0]
    # one row per (rental, occupied day)
    lengths = (r["last_day"] - r["first_day"] + 1).to_numpy()
    occupied = r.loc[r.index.repeat(lengths), ["pickup_station_id", "category", "first_day"]]
    occupied["day"] = occupied["first_day"].to_numpy() + np.concatenate([np.arange(n) for n in lengths])
    return _count_on_grid(inst, occupied, "pickup_station_id", "committed_car_days")


def oneway_flows(inst: Instance) -> pd.DataFrame:
    """R2: one-way cars leaving the pickup station and joining the return station on move_day."""
    r = active_rentals(inst)
    moves = r[r["is_oneway"] & (r["move_day"] <= n_days(inst))].rename(columns={"move_day": "day"})
    arrivals = _count_on_grid(inst, moves, "return_station_id", "oneway_arrivals")
    departures = _count_on_grid(inst, moves, "pickup_station_id", "oneway_departures")
    return arrivals.merge(departures[KEY + ["oneway_departures"]], on=KEY)


# --------------------------------------------------------------------------------------------
# Fleet (R3)
# --------------------------------------------------------------------------------------------
def initial_fleet(inst: Instance) -> pd.DataFrame:
    """R3: f0 per (station, category) = idle cars there + on-rent cars picked up there."""
    snap = inst.fleet_snapshot
    idle = snap[snap["status"] == "idle"][["station_id", "category"]]
    on_rent = snap[snap["status"] == "on_rent"].drop(columns="station_id").merge(
        inst.reservations[["reservation_id", "pickup_station_id"]], on="reservation_id", how="left"
    )
    if on_rent["pickup_station_id"].isna().any():
        raise ValueError("on-rent snapshot car without a matching reservation")
    on_rent = on_rent.rename(columns={"pickup_station_id": "station_id"})[["station_id", "category"]]
    cars = pd.concat([idle, on_rent]).groupby(["station_id", "category"]).size().rename("initial_fleet")
    grid = cell_grid(inst)[["station_id", "category"]].drop_duplicates()
    out = grid.merge(cars.reset_index(), on=["station_id", "category"], how="left")
    out["initial_fleet"] = out["initial_fleet"].fillna(0).astype(int)
    return out.reset_index(drop=True)


def level0_table(inst: Instance) -> pd.DataFrame:
    """The Level 0 table under the do-nothing plan, one row per cell.

    Columns: station_id, category, day, date, committed_car_days, oneway_arrivals,
    oneway_departures, initial_fleet, station_fleet, slack (= station_fleet - committed_car_days).
    """
    t = committed_car_days(inst).merge(oneway_flows(inst).drop(columns="date"), on=KEY)
    t = t.merge(initial_fleet(inst), on=["station_id", "category"])
    net = (t["oneway_arrivals"] - t["oneway_departures"]).groupby([t["station_id"], t["category"]]).cumsum()
    t["station_fleet"] = t["initial_fleet"] + net
    t["slack"] = t["station_fleet"] - t["committed_car_days"]
    return t


def max_removable(table: pd.DataFrame) -> pd.Series:
    """Cars that can be removed on each cell's day without violating f >= c later: min slack over days >= d."""
    rev = table.sort_values(KEY, ascending=[True, True, False])
    m = rev.groupby(["station_id", "category"])["slack"].cummin()
    return m.reindex(table.index).rename("max_removable")


def check_against_reference(inst: Instance) -> pd.DataFrame:
    """Compare level0_table with check_values.csv. Returns the mismatching rows (empty = all OK)."""
    cols = ["committed_car_days", "oneway_arrivals", "oneway_departures", "station_fleet"]
    ref = inst.check_values.copy()
    ref["date"] = pd.to_datetime(ref["date"])
    ours = level0_table(inst)[["station_id", "category", "date"] + cols]
    cmp = ref.merge(ours, on=["station_id", "category", "date"], how="left", suffixes=("_ref", ""))
    bad = cmp[cols].isna().any(axis=1)
    for c in cols:
        bad |= cmp[c] != cmp[f"{c}_ref"]
    return cmp[bad]


# --------------------------------------------------------------------------------------------
# Plan effects (R4)
# --------------------------------------------------------------------------------------------
def plan_deltas(inst: Instance, plan: pd.DataFrame) -> pd.DataFrame:
    """R4: per-cell effect of a plan. The plan must already be well formed (see evaluate.check_plan_format).

    Columns (counts on that cell's day, not cumulative): added, removed, transfer_out, transfer_in,
    plus in_transit = cars that left this station (as origin) and are on the road on that day.
    A transfer leaving on day d is in transit on days d .. d+lead-1 and joins the destination on
    d+lead; if d+lead > 14 it never arrives inside the horizon (but is still in transit, so it
    still costs holding cost).
    """
    cols = ["added", "removed", "transfer_out", "transfer_in", "in_transit"]
    out = cell_grid(inst)
    for c in cols:
        out[c] = 0
    if len(plan) == 0:
        return out

    p = plan.copy()
    p["day"] = date_to_day(inst, p["date"])
    p["cars"] = p["cars"].astype(int)
    horizon = n_days(inst)
    pieces: list[pd.DataFrame] = []

    def add_piece(df: pd.DataFrame, station_col: str, name: str) -> None:
        piece = df[[station_col, "category", "day", "cars"]].rename(columns={station_col: "station_id"})
        pieces.append(piece.assign(col=name))

    add_piece(p[p["action"] == "add"], "station_id", "added")
    add_piece(p[p["action"] == "remove"], "station_id", "removed")

    tr = p[p["action"] == "transfer"].merge(
        inst.distances[["from_station_id", "to_station_id", "lead_time_days"]],
        left_on=["station_id", "to_station_id"],
        right_on=["from_station_id", "to_station_id"],
        how="left",
    )
    if tr["lead_time_days"].isna().any():
        raise ValueError("transfer between stations without a distances.csv row")
    add_piece(tr, "station_id", "transfer_out")
    arriving = tr.assign(day=tr["day"] + tr["lead_time_days"].astype(int))
    add_piece(arriving[arriving["day"] <= horizon], "to_station_id", "transfer_in")
    # one row per (transfer, day on the road) inside the horizon
    on_road_days = (tr["lead_time_days"].astype(int)).clip(upper=horizon - tr["day"] + 1).to_numpy()
    road = tr.loc[tr.index.repeat(on_road_days)].copy()
    road["day"] = road["day"].to_numpy() + np.concatenate([np.arange(n) for n in on_road_days] or [[]]).astype(int)
    add_piece(road, "station_id", "in_transit")

    long = pd.concat(pieces)
    wide = long.pivot_table(index=KEY, columns="col", values="cars", aggfunc="sum", fill_value=0)
    out = out.drop(columns=cols).merge(wide.reset_index(), on=KEY, how="left")
    for c in cols:
        out[c] = out[c].fillna(0).astype(int) if c in out else 0
    return out


def fleet_with_plan(inst: Instance, plan: pd.DataFrame) -> pd.DataFrame:
    """level0_table with the plan applied: station_fleet and slack under the plan (R3 + R4).

    Keeps the do-nothing fleet as `station_fleet_do_nothing`. An empty plan gives the do-nothing table.
    """
    t = level0_table(inst).rename(columns={"station_fleet": "station_fleet_do_nothing"})
    d = plan_deltas(inst, plan)
    t = t.merge(d.drop(columns="date"), on=KEY)
    step = t["added"] - t["removed"] - t["transfer_out"] + t["transfer_in"]
    t["station_fleet"] = t["station_fleet_do_nothing"] + step.groupby([t["station_id"], t["category"]]).cumsum()
    t["slack"] = t["station_fleet"] - t["committed_car_days"]
    return t
