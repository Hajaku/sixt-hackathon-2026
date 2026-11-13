"""Data for the animated fleet map (submission/fleet_map.html): a plan next to a reference plan, day by day.

Everything comes from our scorer's rules (evaluate.py) on seeded demand scenarios; this module only
keeps the day and station axes that `score_plan` sums over. `map_data` checks that the daily profits
add up to `score_plan`'s mean profit, so the animation shows the same numbers as the results table.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fleetkit import Instance
from fleetopt.evaluate import _to_array, fare_revenue, plan_costs, score_plan, serve_demand
from fleetopt.level0 import active_rentals, categories_in_order, date_to_day, fleet_with_plan, horizon_dates, n_days

TEMPLATE = Path(__file__).with_name("fleet_map_template.html")
DATA_MARKER = "/*__FLEET_MAP_DATA__*/"


def daily_breakdown(inst: Instance, plan: pd.DataFrame, demand: pd.DataFrame, base: pd.DataFrame,
                    n_single: int = 0) -> dict:
    """Per station and day (categories summed, mean over scenarios), plus the profit per day.

    Returns arrays (station, day): fleet, free, demand, served; and (day,): profit and its parts.
    Costs are booked on the day they are caused (transfers on the departure day).
    `scenarios` holds demand, served and profit of the first `n_single` scenarios one by one.
    """
    cats, days = categories_in_order(inst), n_days(inst)
    t = fleet_with_plan(inst, plan)
    u = t["station_id"].map(inst.stations.set_index("station_id")["max_utilization"])
    t["free"] = np.maximum(0.0, u * t["station_fleet"] - t["committed_car_days"])          # R6
    free = _to_array(inst, t, "free")[0]                                                    # (station, day, cat)
    fleet = _to_array(inst, t, "station_fleet")[0]
    D = _to_array(inst, demand, "demand", "scenario" if "scenario" in demand.columns else None)
    served = serve_demand(D, free[None])                                                     # R7

    # R8, as in evaluate.new_revenue but keeping station and day
    stype = inst.stations["station_type"].to_numpy()
    b = base.set_index(["station_id", "category"])["base_revenue"]
    pf = inst.price_factors.sort_values("served_share")
    rev_s = np.zeros((D.shape[0],) + free.shape[:2])                                        # (scenario, station, day)
    for j, k in enumerate(cats):
        for t_ in np.unique(stype):
            g = pf[(pf["station_type"] == t_) & (pf["category"] == k)]
            rows = np.flatnonzero(stype == t_)
            base_s = np.array([b[(s, k)] for s in inst.stations["station_id"].iloc[rows]])[None, :, None]
            r = fare_revenue(served[..., j][:, rows], D[..., j][:, rows], base_s,
                             g["served_share"].to_numpy(float), g["price_factor"].to_numpy(float))
            rev_s[:, rows] += r
    rev = rev_s.mean(axis=0)

    # R9: committed revenue, spread evenly over each rental's car-days in the horizon
    committed = np.zeros(days)
    a = active_rentals(inst)
    per_day = (a["revenue"] / a["car_days_total"]).to_numpy()
    for first, last, x in zip(a["first_day"].to_numpy(), a["last_day"].to_numpy(), per_day):
        committed[first - 1:last] += x

    # R10: holding per day; addition and transfer costs on the day of the action
    hold = t["category"].map(inst.categories.set_index("category")["holding_cost_per_day"])
    holding = ((t["station_fleet"] + t["in_transit"]) * hold).groupby(t["day"]).sum().reindex(range(1, days + 1)).to_numpy()
    action_cost = np.zeros(days)
    if len(plan):
        plan_day = date_to_day(inst, plan["date"]).to_numpy()
        for d in np.unique(plan_day):
            c = plan_costs(inst, plan[plan_day == d])
            action_cost[d - 1] = c["addition_cost"] + c["transfer_cost"]

    single = [{"demand": D[w].sum(-1), "served": served[w].sum(-1),
               "profit": committed + rev_s[w].sum(0) - holding - action_cost} for w in range(min(n_single, D.shape[0]))]
    return {"fleet": fleet.sum(-1), "free": free.sum(-1), "demand": D.mean(0).sum(-1), "served": served.mean(0).sum(-1),
            "new_revenue": rev.sum(0), "committed_revenue": committed, "holding_cost": holding,
            "action_cost": action_cost, "profit": committed + rev.sum(0) - holding - action_cost, "scenarios": single}


def plan_moves(inst: Instance, plan: pd.DataFrame) -> dict[str, list[dict]]:
    """Transfers per (from, to, day, mode) with lead time and truck count; additions and removals per (station, day)."""
    if len(plan) == 0:
        return {"transfers": [], "removals": [], "additions": []}
    p = plan.copy()
    p["cars"] = p["cars"].astype(int)
    p["day"] = date_to_day(inst, p["date"]).astype(int)
    cap = int(inst.transfer_costs.set_index("mode").loc["truck", "capacity"])
    tr = (p[p["action"] == "transfer"].groupby(["station_id", "to_station_id", "day", "mode"])["cars"].sum().reset_index()
          .merge(inst.distances, left_on=["station_id", "to_station_id"], right_on=["from_station_id", "to_station_id"]))
    transfers = [{"from": r.station_id, "to": r.to_station_id, "day": int(r.day), "lead": int(r.lead_time_days),
                  "mode": r.mode, "cars": int(r.cars), "units": int(-(-r.cars // cap)) if r.mode == "truck" else int(r.cars)}
                 for r in tr.itertuples()]
    out = {"transfers": transfers}
    for action, name in [("remove", "removals"), ("add", "additions")]:
        g = p[p["action"] == action].groupby(["station_id", "day"])["cars"].sum().reset_index()
        out[name] = [{"station": r.station_id, "day": int(r.day), "cars": int(r.cars)} for r in g.itertuples()]
    return out


def map_data(inst: Instance, plan: pd.DataFrame, scenarios: pd.DataFrame, base: pd.DataFrame,
             reference: pd.DataFrame | None = None, reference_label: str = "Do nothing", n_single: int = 0) -> dict:
    """Everything the animation needs, as plain lists: `reference` (default do-nothing) vs. `plan`, same scenarios.

    `initial` is the state before any plan acts (do-nothing on day 1); both maps start from it.
    `scenarios` has the first `n_single` scenarios one by one (for the scenario picker), next to the mean.
    """
    def rounded(x: np.ndarray, digits: int) -> list:
        return np.round(x, digits).tolist()

    nothing = plan.iloc[0:0]
    reference = nothing if reference is None else reference
    out: dict = {"dates": [d.strftime("%Y-%m-%d") for d in horizon_dates(inst)],
                 "stations": inst.stations[["station_id", "station_name", "station_type"]].to_dict("records"),
                 "n_scenarios": int(scenarios["scenario"].nunique()), "ref_label": reference_label, "plans": {}, "totals": {}}
    b0 = daily_breakdown(inst, nothing, scenarios, base, n_single)
    out["initial"] = {k: rounded(b0[k][:, 0], 2) for k in ["fleet", "free", "demand", "served"]}
    out["scenarios"] = [{"label": f"Scenario {w + 1}", "initial": {k: rounded(s[k][:, 0], 1) for k in ["demand", "served"]}}
                        for w, s in enumerate(b0["scenarios"])]
    for name, p in {"ref": reference, "plan": plan}.items():
        b = daily_breakdown(inst, p, scenarios, base, n_single)
        scores = score_plan(inst, p, scenarios, base)
        if not np.isclose(b["profit"].sum(), scores["profit"].mean(), rtol=1e-9):
            raise AssertionError(f"daily profits of '{name}' do not add up to the scorer's mean profit")
        for w, s in enumerate(b.pop("scenarios")):
            if not np.isclose(s["profit"].sum(), scores["profit"].iloc[w], rtol=1e-9):
                raise AssertionError(f"daily profits of '{name}' in scenario {w} do not add up to the scorer's profit")
            out["scenarios"][w][name] = {"demand": rounded(s["demand"], 1), "served": rounded(s["served"], 1),
                                         "profit": rounded(s["profit"], 0)}
        out["plans"][name] = {k: rounded(v, 2) for k, v in b.items()} | plan_moves(inst, p)
        row = scores.iloc[0]
        out["totals"][name] = {"profit": float(scores["profit"].mean()),
                               "profit_se": float(scores["profit"].std(ddof=1) / np.sqrt(len(scores))),
                               "valid": bool(row["valid"]), "removed": int(row["cars_removed"]),
                               "added": int(row["cars_added"]), "transferred": int(row["cars_transferred"]),
                               "trucks": int(row["trucks"])}
    return out


def render_html(data: dict, template: Path = TEMPLATE) -> str:
    """The self-contained page: the template with the data inlined as JSON."""
    html = template.read_text(encoding="utf-8")
    if DATA_MARKER not in html:
        raise ValueError(f"{template} has no {DATA_MARKER} marker")
    return html.replace(DATA_MARKER, json.dumps(data, separators=(",", ":")))
