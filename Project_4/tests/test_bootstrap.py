"""Bootstrap scenarios: shape, reproducibility, and agreement with the parametric mean."""

import numpy as np

from fleetopt import bootstrap, forecast

KEY = ["station_id", "category", "day"]


def test_week_replays_shape(inst):
    A, cells = bootstrap.week_replays(inst)
    assert A.shape == (8, 2, len(cells), 14)
    assert (A >= 0).all()


def test_bootstrap_reproducible_and_on_grid(inst):
    for block in ("network", "cell"):
        a = bootstrap.bootstrap_demand(inst, 5, seed=3, block=block)
        b = bootstrap.bootstrap_demand(inst, 5, seed=3, block=block)
        assert a.equals(b)
        assert list(a.columns) == ["scenario", *KEY, "demand"]
        assert len(a) == 5 * len(forecast._cells(inst)) * 14


def test_all_week_pairs_mean_matches_parametric(inst):
    """The bootstrap law and the parametric model (no booking update) come from the same weeks."""
    boot = bootstrap.all_week_pairs(inst).groupby("day")["demand"].sum() / 64
    par = forecast.expected_demand(inst, booking_update=False).groupby("day")["demand"].sum()
    assert np.allclose(boot.to_numpy(), par.to_numpy(), rtol=0.03, atol=3)
