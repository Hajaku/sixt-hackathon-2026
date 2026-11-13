"""Structure of the fleet MIP (fleetopt.model_base.build_model) against R7 and R10. Build only, no solve."""

import pytest

from fleetopt.fares import expected_revenue_curves
from fleetopt.forecast import model_inputs, sample_demand
from fleetopt.model_base import build_model

ARCS = [("S01", "S02"), ("S02", "S01")]   # a small network keeps the build fast


@pytest.fixture(scope="module")
def inputs(inst):
    return model_inputs(inst)


def test_level3_has_drivers_and_trucks(inst, inputs):
    model, ctx = build_model(inst, *inputs, modes=("driver", "truck"), arcs=ARCS)
    v = ctx["var"]
    assert v["yd"] and v["yt"] and v["z"]
    # R10: trucks = ceil(cars / 8), i.e. sum_k yt <= 8 z with z integer; not cars = 8 z
    cap = int(inst.transfer_costs.set_index("mode").loc["truck", "capacity"])
    (s, t, d), z = next(iter(v["z"].items()))
    con = model.get_constraint_by_name(f"truck_{s}_{t}_{d}")
    assert con.sense == -1  # <=
    assert con[z] == -cap and z.cat == "Integer"
    # transfers that would arrive after day 14 are not modelled (they cannot earn anything)
    lead = ctx["arc_lead"]
    assert all(dd + lead[(a, b)] <= len(ctx["days"]) for (a, b, k, dd) in v["yd"])


def test_level2_drivers_only(inst, inputs):
    _, ctx = build_model(inst, *inputs, modes=("driver",), arcs=ARCS)
    assert ctx["var"]["yd"] and not ctx["var"]["yt"] and not ctx["var"]["z"]


def test_exact_greedy_with_curves(inst, inputs):
    df_mean, df_base = inputs
    curves = expected_revenue_curves(inst, sample_demand(inst, 5, seed=1), df_base)
    model, ctx = build_model(inst, df_mean, df_base, arcs=ARCS, buckets=curves, exact_greedy=True)
    theta = ctx["var"]["theta"]
    assert theta and set(theta) <= set(ctx["var"]["p"])
    # with curves the own-demand bound of the greedy is the curve's absorb capacity (max_w D^w)
    absorb = curves.groupby(["station_id", "category", "day"])["size"].sum()
    key = next(iter(theta))
    assert ctx["demand"][key] == pytest.approx(absorb[key])
