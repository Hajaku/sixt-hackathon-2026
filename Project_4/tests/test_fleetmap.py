"""The animation data (fleetopt.fleetmap) must show the scorer's numbers."""

import numpy as np

from fleetopt import fleetmap, forecast
from fleetopt.evaluate import read_plan, score_plan


def test_daily_profits_add_up_to_the_scorer(inst, project):
    plan = read_plan(project / "plans" / "final.csv")
    _, base = forecast.model_inputs(inst)
    scen = forecast.sample_demand(inst, 20, seed=1)
    baseline = read_plan(project / "plans" / "baseline.csv")
    data = fleetmap.map_data(inst, plan, scen, base, reference=baseline, reference_label="Baseline", n_single=3)   # raises if days do not add up
    assert np.isclose(sum(data["plans"]["plan"]["profit"]), score_plan(inst, plan, scen, base)["profit"].mean(), atol=1.0)
    assert np.isclose(sum(data["plans"]["ref"]["profit"]), score_plan(inst, baseline, scen, base)["profit"].mean(), atol=1.0)
    assert sum(t["cars"] for t in data["plans"]["plan"]["transfers"]) == data["totals"]["plan"]["transferred"]
    assert sum(r["cars"] for r in data["plans"]["plan"]["removals"]) == data["totals"]["plan"]["removed"]
    assert sum(r["cars"] for r in data["plans"]["ref"]["additions"]) == data["totals"]["ref"]["added"]
    assert len(data["scenarios"]) == 3
    assert np.isclose(sum(data["scenarios"][2]["plan"]["profit"]), score_plan(inst, plan, scen, base)["profit"].iloc[2], atol=20)
    assert data["initial"]["fleet"] == [row[0] for row in fleetmap.map_data(inst, plan, scen, base)["plans"]["ref"]["fleet"]]
    assert fleetmap.DATA_MARKER not in fleetmap.render_html(data)
