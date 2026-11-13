"""Base revenue estimator (fleetopt.forecast)."""

import numpy as np
import pytest

from fleetopt.forecast import base_revenue, rental_history


def test_history_has_no_future_bookings(inst):
    h = rental_history(inst)
    assert set(h["status"]) == {"completed", "open"}
    assert (h["pickup_date"] < inst.horizon["first_date"].iloc[0]).all()


def test_full_grid_and_positive(inst):
    b = base_revenue(inst)
    assert len(b) == len(inst.stations) * len(inst.categories)
    assert not b.duplicated(["station_id", "category"]).any()
    assert b.notna().all().all()
    assert (b["base"] > 0).all()


def test_cell_is_revenue_over_car_days(inst):
    r = inst.reservations
    r = r[(r["status"] == "completed") & (r["pickup_station_id"] == "S03") & (r["category"] == "midsize")]
    days = (np.asarray(r["return_date"], "datetime64[D]") - np.asarray(r["pickup_date"], "datetime64[D]")).astype(int) + 1
    b = base_revenue(inst).set_index(["station_id", "category"])
    assert b.loc[("S03", "midsize"), "base_cell"] == pytest.approx(r["revenue"].sum() / days.sum())


def test_multiplicative_close_to_cell(inst):
    b = base_revenue(inst, method="multiplicative")
    assert (b["base"] == b["base_multiplicative"]).all()
    assert ((b["base_multiplicative"] / b["base_cell"] - 1).abs() < 0.03).all()


def test_category_order_by_price(inst):
    """Higher categories earn more per car-day at every station."""
    b = base_revenue(inst)
    for _, g in b.groupby("station_id"):
        assert g["base"].is_monotonic_increasing


# --- demand to come -----------------------------------------------------------------------

from fleetopt.forecast import (  # noqa: E402
    expected_demand, history_pickups, model_inputs, pickup_rates, sample_demand, to_come_kernel,
    week_factors, weekly_shock_variance,
)


def test_pickup_rates_are_weekday_means(inst):
    p = history_pickups(inst)
    assert p["date"].nunique() == 56 and p["date"].min().day_of_week == 0
    rates = pickup_rates(p).set_index(["station_id", "category", "weekday"])["rate"]
    assert len(rates) == len(inst.stations) * len(inst.categories) * 7
    r = inst.reservations
    sat = r[r["status"].isin(["completed", "open"]) & (r["pickup_station_id"] == "S02")
            & (r["category"] == "economy") & (r["pickup_date"].dt.day_of_week == 5)]
    assert rates[("S02", "economy", 5)] == pytest.approx(len(sat) / 8)


def test_kernel_is_a_sub_probability(inst):
    for K in to_come_kernel(inst).values():
        share = K.sum(axis=1)
        assert (np.diff(share) >= -1e-12).all()           # P(lead <= p-1) grows with p
        assert 0 < share[0] < share[-1] <= 1


def test_shock_variance_in_range(inst):
    assert 0.005 < weekly_shock_variance(inst) < 0.05


def test_week_factors_prior_and_update(inst):
    prior = week_factors(inst, booking_update=False)
    assert np.allclose(prior["mean"], 1.0) and (prior["n_booked"] == 0).all()
    upd = week_factors(inst)
    assert set(upd["week"]) == {1, 2}
    assert np.allclose(upd["shape"] - upd["n_booked"], upd["rate"] - upd["mu_booked"])
    assert upd["n_booked"].sum() == (inst.reservations["status"] == "booked").sum()


def test_expected_demand_grid(inst):
    d = expected_demand(inst)
    assert len(d) == len(inst.stations) * len(inst.categories) * 14
    assert (d["demand"] >= 0).all() and (d["demand_sd"] ** 2 >= d["demand"] - 1e-9).all()  # overdispersed
    day = d.groupby("day")["demand"].sum()
    assert day[1] < day[7]                                  # ramp: near days are mostly booked


def test_scenarios_reproducible_and_match_expectation(inst):
    a = sample_demand(inst, 50, seed=7)
    assert a.equals(sample_demand(inst, 50, seed=7))
    assert (a["demand"] >= 0).all() and a["demand"].dtype.kind == "i"
    big = sample_demand(inst, 1000, seed=1)
    mc = big.groupby("day")["demand"].sum() / 1000
    ex = expected_demand(inst).groupby("day")["demand"].sum()
    assert np.allclose(mc.to_numpy(), ex.to_numpy(), rtol=0.02)


def test_model_inputs_format(inst):
    df_demand, df_base = model_inputs(inst)
    assert list(df_demand.columns) == ["station_id", "category", "day", "demand"]
    assert list(df_base.columns) == ["station_id", "category", "base_revenue"]
