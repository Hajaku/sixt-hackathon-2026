"""Expected-revenue curves (fleetopt.fares) against the scorer's revenue rule."""

import numpy as np
import pytest

from fleetopt.evaluate import fare_revenue
from fleetopt.fares import KEY, expected_revenue_curves
from fleetopt.forecast import model_inputs, sample_demand


@pytest.fixture(scope="module")
def setup(inst):
    _, df_base = model_inputs(inst)
    scen = sample_demand(inst, 100, seed=3)
    return df_base, scen, expected_revenue_curves(inst, scen, df_base)


def _scorer_mean(inst, df_base, scen, key, capacity):
    s, k, d = key
    D = scen[(scen.station_id == s) & (scen.category == k) & (scen.day == d)]["demand"].to_numpy(float)
    stype = inst.stations.set_index("station_id").loc[s, "station_type"]
    pf = inst.price_factors[(inst.price_factors.station_type == stype) & (inst.price_factors.category == k)].sort_values("served_share")
    b = df_base.set_index(["station_id", "category"]).loc[(s, k), "base_revenue"]
    return fare_revenue(np.minimum(D, capacity), D, b, pf["served_share"].to_numpy(float), pf["price_factor"].to_numpy(float)).mean()


def test_curve_total_is_mean_full_service_revenue(inst, setup):
    df_base, scen, cb = setup
    for key in [("S02", "economy", 6), ("S04", "midsize", 13), ("S01", "premium", 3)]:
        c = cb.set_index(KEY).loc[key]
        assert (c["size"] * c["marginal"]).sum() == pytest.approx(_scorer_mean(inst, df_base, scen, key, np.inf))


def test_curve_matches_scorer_on_its_grid(inst, setup):
    df_base, scen, cb = setup
    key = ("S02", "compact", 6)
    c = cb.set_index(KEY).loc[key]
    cum_cap = np.cumsum(c["size"].to_numpy())
    cum_rev = np.cumsum((c["size"] * c["marginal"]).to_numpy())
    for cap, rev in list(zip(cum_cap, cum_rev))[::3]:
        assert rev == pytest.approx(_scorer_mean(inst, df_base, scen, key, cap))


def test_curves_nearly_all_concave_and_positive(setup):
    _, _, cb = setup
    assert (cb["marginal"] > 0).all() and (cb["size"] > 0).all()
    per_cell = cb.groupby(KEY)["concave"].first()
    assert per_cell.mean() > 0.95


def test_exact_kink_curves_equal_saa_revenue_anywhere(inst, setup):
    """With max_segments=None the curve is exact at every capacity, not only on a grid."""
    df_base, scen, _ = setup
    small = scen[scen["scenario"] < 10]
    cb = expected_revenue_curves(inst, small, df_base, max_segments=None, concave_tol=1e-6)
    for key in [("S02", "economy", 6), ("S04", "midsize", 13)]:
        c = cb.set_index(KEY).loc[key]
        sizes, margs = c["size"].to_numpy(), c["marginal"].to_numpy()
        for cap in [3.7, 17.3, 41.9]:
            take = np.clip(cap - np.concatenate([[0], np.cumsum(sizes)[:-1]]), 0, sizes)
            assert (take * margs).sum() == pytest.approx(_scorer_mean(inst, df_base, small, key, cap))
