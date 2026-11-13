"""M1: the full fleet MIP (Notes/Models/M1 Full Fleet MIP.md).

One model for the whole scorer (README Appendix A, R1-R11): additions, removals,
driver and truck transfers on a time-space network, one-step upgrades and the
fare-adjustment buckets. Levels are restrictions of it:

- `modes=()`                 -> Level 1 (add / remove only)
- `modes=("driver",)`        -> Level 2 (plus driver transfers)
- `modes=("driver","truck")` -> Level 3 (plus trucks, upgrades via the buckets)

The model is faithful to the scorer given the forecast: the greedy "own category
first" of R7 is enforced with one binary per cell (never smarter than the scorer),
non-concave bucket sets fill in order via prefix binaries, and trucks count whole
`ceil` loads. Committed revenue (R9) is a constant: report it with
`committed_revenue`, it is not part of the objective.

Beyond the instance the model needs the forecast as two long tables:
- `df_demand`: station_id, category, day, demand       (R7's D, car-days to come)
- `df_base`:   station_id, category, base_revenue      (R8's base, per car-day)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd
import pulp

from fleetkit import Instance
from fleetopt import level0
from fleetopt.solvers import get_solver

MODEL_ID = "M1"
KEY = ["station_id", "category", "day"]
EPS = 1e-9


@dataclass
class ModelRun:
    """The outcome of one solve: a plan plus what the model thinks it earns."""

    plan: pd.DataFrame
    status: str
    objective: float
    breakdown: dict[str, float]
    fleet: pd.DataFrame  # solved f per cell, with committed and slack
    served: pd.DataFrame  # forecast demand vs. served car-days per cell
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------------------------
# Fare adjustment (Appendix C): buckets per cell
# --------------------------------------------------------------------------------------------
def demand_buckets(
    inst: Instance, df_demand: pd.DataFrame, df_base: pd.DataFrame
) -> pd.DataFrame:
    """Turn the price factors into demand buckets, one row per (cell, bucket).

    Columns: station_id, category, day, bucket (1 = first), size (car-days),
    marginal (revenue per car-day in that bucket), concave (per-cell flag: the
    marginals do not rise, so an LP fills the buckets in order by itself).
    A cell with zero demand has no buckets; a non-positive marginal or a missing
    base revenue raises (Level 4 territory, see the Project Plan findings).
    """
    t = _on_grid(inst, df_demand.rename(columns={"demand": "demand_filled"}), ["demand_filled"])
    base = df_base.set_index(["station_id", "category"])["base_revenue"].to_dict()
    stype = inst.stations.set_index("station_id")["station_type"].to_dict()
    pf = inst.price_factors.set_index(["station_type", "category", "served_share"])["price_factor"]
    shares = sorted(inst.price_factors["served_share"].unique())

    rows = []
    for row in t.itertuples():
        if row.demand_filled <= 0:
            continue
        r = base.get((row.station_id, row.category), 0.0)
        if r <= 0:
            raise ValueError(f"no base_revenue for {row.station_id}/{row.category} with demand > 0")
        pfs = [pf[(stype[row.station_id], row.category, q)] for q in shares]
        totals = [q * row.demand_filled * r * p for q, p in zip(shares, pfs)]
        size = [shares[0] * row.demand_filled]
        marg = [r * pfs[0]]  # below 60 % the price factor of 60 % applies
        for i in range(1, len(shares)):
            dq = shares[i] - shares[i - 1]
            size.append(dq * row.demand_filled)
            marg.append((totals[i] - totals[i - 1]) / (dq * row.demand_filled))
        if min(marg) <= 0:
            raise ValueError(
                f"non-positive bucket marginal at {row.station_id}/{row.category}/day {row.day} "
                f"(marginals {np.round(marg, 3)}); check the price factors (Level 4)"
            )
        concave = bool(np.all(np.diff(marg) <= EPS))
        for b, (sz, mg) in enumerate(zip(size, marg), start=1):
            rows.append(
                {
                    "station_id": row.station_id,
                    "category": row.category,
                    "day": row.day,
                    "bucket": b,
                    "size": sz,
                    "marginal": mg,
                    "concave": concave,
                }
            )
    return pd.DataFrame(rows, columns=[*KEY, "bucket", "size", "marginal", "concave"])


# --------------------------------------------------------------------------------------------
# Forecast input helper
# --------------------------------------------------------------------------------------------
def _on_grid(inst: Instance, df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Left-merge a (possibly partial) table onto the full cell grid, filling zeros."""
    t = level0.cell_grid(inst).merge(df, on=KEY, how="left")
    for c in cols:
        if c not in t:
            raise ValueError(f"forecast table is missing column {c!r}")
        t[c] = t[c].fillna(0.0)
    return t


# --------------------------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------------------------
def build_model(
    inst: Instance,
    df_demand: pd.DataFrame,
    df_base: pd.DataFrame,
    *,
    modes: tuple[str, ...] = ("driver", "truck"),
    arcs: Iterable[tuple[str, str]] | None = None,
    prefix_all: bool = False,
    exact_greedy: bool = False,
) -> tuple[pulp.LpProblem, dict]:
    """Build the M1 MIP. Levels are restrictions: `modes=()` is L1, drivers only is L2.

    `arcs` optionally restricts transfers to the given (from, to) station pairs.
    `prefix_all` uses the prefix binaries on every cell, concave or not (for testing).
    `exact_greedy` adds the R7 greedy binaries theta. They reproduce the scorer's
    "own category first" exactly but kill the primal heuristics (no incumbent for
    minutes); the default LP second stage can only deviate by moving a higher
    category's free capacity from its own unserved demand to the category below,
    and every plan it yields is valid - settle the difference with fleetopt/evaluate.py
    (see Decisions 2026-11-13).
    Returns the problem and a context dict with the parameters and variables.
    """
    dates = level0.horizon_dates(inst)
    nd = len(dates)
    stations = inst.stations["station_id"].tolist()
    cats = level0.categories_in_order(inst)  # lowest rank first
    days = list(range(1, nd + 1))

    l0 = level0.level0_table(inst)
    committed = l0.set_index(KEY)["committed_car_days"].to_dict()
    ow_arr = l0.set_index(KEY)["oneway_arrivals"].to_dict()
    ow_dep = l0.set_index(KEY)["oneway_departures"].to_dict()
    f0 = level0.initial_fleet(inst).set_index(["station_id", "category"])["initial_fleet"].to_dict()
    util = inst.stations.set_index("station_id")["max_utilization"].to_dict()
    par = inst.categories.set_index("category")
    holding = par["holding_cost_per_day"].to_dict()
    add_cost = par["addition_cost_per_car"].to_dict()
    add_cap = par["addition_cap"].to_dict()
    rem_cap = par["removal_cap"].to_dict()
    # cars of category k on the whole network (one-ways move, only additions create)
    cars_k = {k: int((inst.fleet_snapshot["category"] == k).sum()) for k in cats}

    demand_t = _on_grid(inst, df_demand.rename(columns={"demand": "demand_filled"}), ["demand_filled"])
    demand = demand_t.set_index(KEY)["demand_filled"].to_dict()
    buckets = demand_buckets(inst, df_demand, df_base)

    # transfer arcs with feasible departure days (a transfer must arrive inside the horizon)
    dist = inst.distances
    if arcs is not None:
        keep = {(s, t) for s, t in arcs}
        mask = [
            (a, b) in keep for a, b in zip(dist["from_station_id"], dist["to_station_id"])
        ]
        dist = dist[mask]
    tc = inst.transfer_costs.set_index("mode")
    arc_lead = {
        (r.from_station_id, r.to_station_id): r.lead_time_days for r in dist.itertuples()
    }
    arc_days = {a: range(1, nd - lead + 1) for a, lead in arc_lead.items()}

    model = pulp.LpProblem("M1_fleet", pulp.LpMaximize)

    # --- first-stage plan variables
    xadd = model.add_variable_dict("xadd", (stations, cats, days), lowBound=0, cat="Integer")
    xrem = model.add_variable_dict("xrem", (stations, cats, days), lowBound=0, cat="Integer")

    yd: dict[tuple, pulp.LpVariable] = {}
    yt: dict[tuple, pulp.LpVariable] = {}
    z: dict[tuple, pulp.LpVariable] = {}
    y_ub = max(cars_k.values()) + max(add_cap.values())
    z_ub = int(np.ceil(inst.fleet_snapshot.shape[0] / tc.loc["truck", "capacity"]))
    for (s, t), dep_days in arc_days.items():
        for d in dep_days:
            if "truck" in modes:
                z[(s, t, d)] = model.add_variable(f"z_{s}_{t}_{d}", lowBound=0, upBound=z_ub, cat="Integer")
            for k in cats:
                if "driver" in modes:
                    yd[(s, t, k, d)] = model.add_variable(
                        f"yd_{s}_{t}_{k}_{d}", lowBound=0, upBound=y_ub, cat="Integer"
                    )
                if "truck" in modes:
                    yt[(s, t, k, d)] = model.add_variable(
                        f"yt_{s}_{t}_{k}_{d}", lowBound=0, upBound=y_ub, cat="Integer"
                    )

    # transfer flows per cell, for the fleet balance
    out_flows: dict[tuple, list] = defaultdict(list)
    in_flows: dict[tuple, list] = defaultdict(list)
    for flows in (yd, yt):
        for (s, t, k, d), v in flows.items():
            out_flows[(s, k, d)].append(v)
            in_flows[(t, k, d + arc_lead[(s, t)])].append(v)

    # --- fleet flow (R3/R4) and validity (R5)
    f = model.add_variable_dict("f", (stations, cats, days), lowBound=0)
    for s in stations:
        for k in cats:
            for d in days:
                prev = f0.get((s, k), 0) if d == 1 else f[(s, k, d - 1)]
                model += (
                    f[(s, k, d)]
                    == prev
                    + ow_arr[(s, k, d)]
                    - ow_dep[(s, k, d)]
                    + xadd[(s, k, d)]
                    - xrem[(s, k, d)]
                    - pulp.lpSum(out_flows.get((s, k, d), []))
                    + pulp.lpSum(in_flows.get((s, k, d), [])),
                    f"flow_{s}_{k}_{d}",
                )
                model += (f[(s, k, d)] >= committed[(s, k, d)], f"valid_{s}_{k}_{d}")

    # --- caps (R5)
    for k in cats:
        model += (
            pulp.lpSum(v for (s, kk, d), v in xadd.items() if kk == k) <= add_cap[k],
            f"add_cap_{k}",
        )
        model += (
            pulp.lpSum(v for (s, kk, d), v in xrem.items() if kk == k) <= rem_cap[k],
            f"rem_cap_{k}",
        )

    # --- serving the demand to come (R6/R7)
    a_fr: dict[tuple, pulp.LpVariable] = {}
    p: dict[tuple, pulp.LpVariable] = {}
    q: dict[tuple, pulp.LpVariable] = {}
    theta: dict[tuple, pulp.LpVariable] = {}
    for s in stations:
        for i, k in enumerate(cats):
            below = cats[i - 1] if i > 0 else None
            for d in days:
                D = demand[(s, k, d)]
                needs_capacity = D > 0 or (below is not None and demand[(s, below, d)] > 0)
                if not needs_capacity:
                    continue
                # R6 free capacity a_fr = max(0, u_s f - c): the epigraph below is not a
                # bound on serving, so a starved-or-not binary w makes it exact.
                #   w=1 => a_fr <= u_s f - c   (together with a_fr >= it, a_fr = that, forces it >= 0)
                #   w=0 => a_fr = 0            (scorer: committed > u_s f serves no new demand)
                # Both branches upper-bound the true max(0, .), so every solution is honest;
                # when u_s f - c >= 0, w=1 is exactly as good, so the optimum is the scorer's a.
                a_fr[(s, k, d)] = model.add_variable(f"afr_{s}_{k}_{d}", lowBound=0)
                slack_expr = util[s] * f[(s, k, d)] - committed[(s, k, d)]
                model += (a_fr[(s, k, d)] >= slack_expr, f"afr_lo_{s}_{k}_{d}")
                big_m = max(0.0, util[s] * (cars_k[k] + add_cap[k]) - committed[(s, k, d)])
                w = model.add_variable(f"w_{s}_{k}_{d}", cat="Binary")
                model += (a_fr[(s, k, d)] <= slack_expr + big_m * (1 - w), f"afr_hi_{s}_{k}_{d}")
                model += (a_fr[(s, k, d)] <= big_m * w, f"afr_zero_{s}_{k}_{d}")
                if D > 0:
                    p[(s, k, d)] = model.add_variable(f"p_{s}_{k}_{d}", lowBound=0, upBound=D)
                    if i < len(cats) - 1:
                        q[(s, k, d)] = model.add_variable(f"q_{s}_{k}_{d}", lowBound=0, upBound=D)
                    model += (p[(s, k, d)] + q.get((s, k, d), 0) <= D, f"serve_{s}_{k}_{d}")
                    if exact_greedy:
                        # greedy own-first (R7): theta=1 => p=D (leftover capacity may upgrade);
                        # theta=0 => p=a_fr (own capacity fully used, nothing to upgrade out)
                        theta[(s, k, d)] = model.add_variable(f"th_{s}_{k}_{d}", cat="Binary")
                        model += (p[(s, k, d)] >= D * theta[(s, k, d)], f"greedy_hi_{s}_{k}_{d}")
                        model += (
                            p[(s, k, d)] >= a_fr[(s, k, d)] - big_m * theta[(s, k, d)],
                            f"greedy_lo_{s}_{k}_{d}",
                        )
                # own use + cars of this category stepping down to the one below
                terms = [p.get((s, k, d), 0)]
                if below is not None:
                    terms.append(q.get((s, below, d), 0))
                model += (pulp.lpSum(terms) <= a_fr[(s, k, d)], f"capa_{s}_{k}_{d}")

    # --- fare buckets (R8)
    fills: dict[tuple, pulp.LpVariable] = {}
    prefix: dict[tuple, pulp.LpVariable] = {}
    for cell_key, grp in buckets.groupby(KEY + ["concave"]):
        s, k, d, concave = cell_key
        grp = grp.sort_values("bucket")
        sizes = grp["size"].tolist()
        cell_fills = []
        for b, sz in enumerate(sizes, start=1):
            cell_fills.append(
                model.add_variable(f"sfill_{s}_{k}_{d}_{b}", lowBound=0, upBound=sz)
            )
            fills[(s, k, d, b)] = cell_fills[-1]
        if prefix_all or not concave:
            # delta_b = 1 means "bucket b may be used": it forces bucket b-1 to be full first
            for b in range(2, len(cell_fills) + 1):
                prefix[(s, k, d, b)] = model.add_variable(f"delta_{s}_{k}_{d}_{b}", cat="Binary")
                model += (
                    cell_fills[b - 1] <= sizes[b - 1] * prefix[(s, k, d, b)],
                    f"prefix_up_{s}_{k}_{d}_{b}",
                )
                model += (
                    cell_fills[b - 2] >= sizes[b - 2] * prefix[(s, k, d, b)],
                    f"prefix_lo_{s}_{k}_{d}_{b}",
                )
        model += (
            pulp.lpSum(cell_fills) == p[(s, k, d)] + q.get((s, k, d), 0),
            f"bsum_{s}_{k}_{d}",
        )

    # --- trucks (R10): whole trucks per (origin, destination, departure day)
    for (s, t, d) in z:
        model += (
            pulp.lpSum(
                v for (a, b, k, dd), v in yt.items() if a == s and b == t and dd == d
            )
            <= tc.loc["truck", "capacity"] * z[(s, t, d)],
            f"truck_{s}_{t}_{d}",
        )

    # --- objective (R11 without the constant committed revenue)
    marginal = buckets.set_index([*KEY, "bucket"])["marginal"].to_dict()
    km = inst.distances.set_index(["from_station_id", "to_station_id"])["distance_km"].to_dict()
    driver_car_cost = {
        a: tc.loc["driver", "fixed_cost"] + tc.loc["driver", "cost_per_km"] * km[a] for a in km
    }
    truck_load_cost = {
        a: tc.loc["truck", "fixed_cost"] + tc.loc["truck", "cost_per_km"] * km[a] for a in km
    }
    revenue = pulp.lpSum(marginal[key] * v for key, v in fills.items())
    hold_fleet = pulp.lpSum(holding[k] * v for (s, k, d), v in f.items())
    # a car transferred on day d is in transit on days d .. d+lead-1, all inside the horizon
    hold_transit = pulp.lpSum(
        arc_lead[(s, t)] * holding[k] * v for flows in (yd, yt) for (s, t, k, d), v in flows.items()
    )
    addition = pulp.lpSum(add_cost[k] * v for (s, k, d), v in xadd.items())
    drv_cost = pulp.lpSum(driver_car_cost[(s, t)] * v for (s, t, k, d), v in yd.items())
    trk_cost = pulp.lpSum(truck_load_cost[(s, t)] * v for (s, t, d), v in z.items())
    model += (
        revenue - hold_fleet - hold_transit - addition - drv_cost - trk_cost,
        "profit_ex_committed",
    )

    var = {
        "xadd": xadd, "xrem": xrem, "yd": yd, "yt": yt, "z": z,
        "f": f, "afr": a_fr, "p": p, "q": q, "theta": theta,
        "fills": fills, "prefix": prefix,
    }
    ctx = {
        "model_id": MODEL_ID,
        "inst": inst,
        "dates": dates,
        "days": days,
        "stations": stations,
        "cats": cats,
        "demand": demand,
        "committed": committed,
        "buckets": buckets,
        "marginal": marginal,
        "arc_lead": arc_lead,
        "driver_car_cost": driver_car_cost,
        "truck_load_cost": truck_load_cost,
        "modes": tuple(modes),
        "var": var,
    }
    return model, ctx


# --------------------------------------------------------------------------------------------
# Solve and extract
# --------------------------------------------------------------------------------------------
def solve_plan(
    inst: Instance,
    df_demand: pd.DataFrame,
    df_base: pd.DataFrame,
    *,
    modes: tuple[str, ...] = ("driver", "truck"),
    arcs: Iterable[tuple[str, str]] | None = None,
    solver: str = "highs",
    time_limit: float | None = 120,
    gap_rel: float | None = 0.01,
    msg: bool = False,
    prefix_all: bool = False,
    exact_greedy: bool = False,
) -> ModelRun:
    """Build, solve and turn the solution into a plan. Raises if the solver has no solution."""
    model, ctx = build_model(
        inst, df_demand, df_base, modes=modes, arcs=arcs,
        prefix_all=prefix_all, exact_greedy=exact_greedy,
    )
    stats = model.solve(get_solver(solver, time_limit=time_limit, gap_rel=gap_rel, msg=msg))
    if not stats.has_solution:
        raise RuntimeError(f"no solution: {stats.status}")
    return _extract(ctx, stats)


def _extract(ctx: dict, stats) -> ModelRun:
    """Read values back: plan rows, objective breakdown, solved fleet and served tables."""
    inst, dates, var = ctx["inst"], ctx["dates"], ctx["var"]

    def val(v: pulp.LpVariable) -> float:
        return v.value() or 0.0

    rows = []
    for (s, k, d), v in sorted(var["xadd"].items()):
        if round(val(v)) > 0:
            rows.append(("add", dates[d - 1], k, s, None, None, round(val(v))))
    for (s, k, d), v in sorted(var["xrem"].items()):
        if round(val(v)) > 0:
            rows.append(("remove", dates[d - 1], k, s, None, None, round(val(v))))
    for name, mode in (("yd", "driver"), ("yt", "truck")):
        for (s, t, k, d), v in sorted(var[name].items()):
            if round(val(v)) > 0:
                rows.append(("transfer", dates[d - 1], k, s, t, mode, round(val(v))))
    plan = pd.DataFrame(
        rows, columns=["action", "date", "category", "station_id", "to_station_id", "mode", "cars"]
    )

    breakdown = {
        "new_revenue": sum(ctx["marginal"][key] * val(v) for key, v in var["fills"].items()),
        "holding_fleet": sum(
            inst.categories.set_index("category")["holding_cost_per_day"][k] * val(v)
            for (s, k, d), v in var["f"].items()
        ),
        # in-transit cars pay holding for lead days each (all arrivals are inside the horizon)
        "holding_transit": sum(
            ctx["arc_lead"][(s, t)]
            * inst.categories.set_index("category")["holding_cost_per_day"][k]
            * val(v)
            for flows in (var["yd"], var["yt"])
            for (s, t, k, d), v in flows.items()
        ),
        "addition": sum(
            inst.categories.set_index("category")["addition_cost_per_car"][k] * val(v)
            for (s, k, d), v in var["xadd"].items()
        ),
        "driver": sum(ctx["driver_car_cost"][(s, t)] * val(v) for (s, t, k, d), v in var["yd"].items()),
        "truck": sum(ctx["truck_load_cost"][(s, t)] * val(v) for (s, t, d), v in var["z"].items()),
    }

    def cells(df: pd.DataFrame):
        return zip(df["station_id"], df["category"], df["day"])

    fleet = level0.cell_grid(inst)
    fleet["fleet"] = [round(val(var["f"][key])) for key in cells(fleet)]
    fleet["committed_car_days"] = [ctx["committed"][key] for key in cells(fleet)]
    fleet["slack"] = fleet["fleet"] - fleet["committed_car_days"]

    served = level0.cell_grid(inst)
    served["demand"] = [ctx["demand"][key] for key in cells(served)]
    fill_by_cell: dict[tuple, float] = defaultdict(float)
    for (s, k, d, b), v in var["fills"].items():
        fill_by_cell[(s, k, d)] += val(v)
    served["served"] = [fill_by_cell[key] for key in cells(served)]

    return ModelRun(
        plan=plan,
        status=stats.status.name,
        objective=stats.objective,
        breakdown=breakdown,
        fleet=fleet,
        served=served,
        extra={"model_id": ctx["model_id"], "modes": ctx["modes"]},
    )


# --------------------------------------------------------------------------------------------
# Committed revenue (R9) - a constant, for reporting only
# --------------------------------------------------------------------------------------------
def committed_revenue(inst: Instance) -> float:
    """R9: the share of open and booked rentals' revenue that falls inside the horizon."""
    r = level0.active_rentals(inst)
    share = r["car_days_in_horizon"] / r["car_days_total"]
    return float((r["revenue"] * share).sum())
