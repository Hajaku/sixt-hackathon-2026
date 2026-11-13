"""Profit part of our scorer (R6-R11) in fleetopt.evaluate."""

import numpy as np
import pandas as pd
import pytest

from fleetopt.evaluate import (
    committed_revenue, fare_revenue, new_revenue, plan_costs, score_plan, serve_demand,
)
from fleetopt.forecast import expected_demand, model_inputs
from fleetopt.level0 import horizon_dates, level0_table
from fleetopt.model_base import committed_revenue as committed_revenue_model

SHARES = np.array([0.6, 0.7, 0.8, 0.9, 1.0])
PF = np.array([1.30, 1.21, 1.14, 1.07, 1.00])     # README Appendix C


def plan(*rows):
    cols = ["action", "date", "category", "station_id", "to_station_id", "mode", "cars"]
    return pd.DataFrame([{c: r.get(c) for c in cols} for r in rows], columns=cols)


def test_fare_revenue_matches_appendix_c():
    served = np.array([60, 70, 75, 80, 90, 100, 40, 0], float)
    got = fare_revenue(served, np.full(8, 100.0), 250.0, SHARES, PF)
    assert got == pytest.approx([19500, 21175, 21987.5, 22800, 24075, 25000, 13000, 0])
    assert fare_revenue(np.array([0.0]), np.array([0.0]), 250.0, SHARES, PF)[0] == 0


def test_serve_demand_one_step_upgrades_only():
    D = np.array([[10.0, 0, 0, 0]])
    a = np.array([[0.0, 0, 5, 0]])            # midsize free, economy short: no two-step upgrade
    assert serve_demand(D, a).tolist() == [[0, 0, 0, 0]]
    D = np.array([[10.0, 5, 3, 1]])
    a = np.array([[4.0, 9, 2, 6]])
    assert serve_demand(D, a).tolist() == [[8, 5, 3, 1]]   # compact upgrades 4 economy, premium 1 midsize


def test_committed_revenue_matches_model(inst):
    assert committed_revenue(inst) == pytest.approx(committed_revenue_model(inst))


def test_do_nothing_holding_cost(inst):
    c = plan_costs(inst, plan())
    t = level0_table(inst)
    h = inst.categories.set_index("category")["holding_cost_per_day"]
    expected = (t.groupby("category")["station_fleet"].sum() * h).sum()
    assert c["holding_cost"] == pytest.approx(expected)
    assert c["addition_cost"] == c["transfer_cost"] == 0


def test_transfer_costs_and_truck_sharing(inst):
    d = str(horizon_dates(inst)[2].date())
    base = plan_costs(inst, plan())
    p = plan({"action": "transfer", "date": d, "category": "economy", "station_id": "S01", "to_station_id": "S05", "mode": "truck", "cars": 5},
             {"action": "transfer", "date": d, "category": "premium", "station_id": "S01", "to_station_id": "S05", "mode": "truck", "cars": 5},
             {"action": "transfer", "date": d, "category": "economy", "station_id": "S01", "to_station_id": "S02", "mode": "driver", "cars": 2})
    c = plan_costs(inst, p)
    tc = inst.transfer_costs.set_index("mode")
    dist = inst.distances.set_index(["from_station_id", "to_station_id"])["distance_km"]
    truck = 2 * (tc.loc["truck", "fixed_cost"] + tc.loc["truck", "cost_per_km"] * dist[("S01", "S05")])   # 10 cars -> 2 trucks
    driver = 2 * (tc.loc["driver", "fixed_cost"] + tc.loc["driver", "cost_per_km"] * dist[("S01", "S02")])
    assert c["trucks"] == 2 and c["transfer_cost"] == pytest.approx(truck + driver)
    # transfers that arrive inside the horizon keep every car in a fleet or in transit: same holding
    assert c["holding_cost"] == pytest.approx(base["holding_cost"])


def test_removal_and_addition_change_holding(inst):
    d = str(horizon_dates(inst)[9].date())          # day 10: 5 days left
    h = inst.categories.set_index("category")
    base = plan_costs(inst, plan())["holding_cost"]
    rem = plan_costs(inst, plan({"action": "remove", "date": d, "category": "premium", "station_id": "S01", "cars": 3}))
    assert rem["holding_cost"] == pytest.approx(base - 3 * 5 * h.loc["premium", "holding_cost_per_day"])
    add = plan_costs(inst, plan({"action": "add", "date": d, "category": "economy", "station_id": "S02", "cars": 2}))
    assert add["holding_cost"] == pytest.approx(base + 2 * 5 * h.loc["economy", "holding_cost_per_day"])
    assert add["addition_cost"] == pytest.approx(2 * h.loc["economy", "addition_cost_per_car"])


def test_new_revenue_zero_demand_and_monotone_in_fleet(inst):
    _, df_base = model_inputs(inst)
    d = expected_demand(inst)[["station_id", "category", "day", "demand"]]
    assert new_revenue(inst, plan(), d.assign(demand=0.0), df_base)[0] == 0
    r0 = new_revenue(inst, plan(), d, df_base)[0]
    day1 = str(horizon_dates(inst)[0].date())
    r1 = new_revenue(inst, plan({"action": "add", "date": day1, "category": "economy", "station_id": "S02", "cars": 10}), d, df_base)[0]
    assert r1 > r0                                    # S02 economy is short of cars


def test_score_plan_breakdown(inst):
    _, df_base = model_inputs(inst)
    d = expected_demand(inst)[["station_id", "category", "day", "demand"]]
    s = score_plan(inst, plan(), d, df_base).iloc[0]
    assert bool(s["valid"])
    assert s["profit"] == pytest.approx(s["committed_revenue"] + s["new_revenue"] - s["holding_cost"]
                                        - s["addition_cost"] - s["transfer_cost"])
