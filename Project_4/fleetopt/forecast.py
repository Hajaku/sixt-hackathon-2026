"""Forecasts from the rental history: base revenue per car-day and the demand to come.

Demand model (Notes/Demand.md): to-come pickups on horizon day p at cell (s, k) are
Poisson(G[s,k,w(p)] * lambda[s,k,wd(p)] * P(lead <= p-1)), with one Gamma factor G per cell and
calendar week (mean 1, variance v), i.i.d. across cells and weeks. Each pickup draws its
(length, lead) pair from the joint empirical distribution of its station type x category. The
factor of each horizon week is updated with the bookings already made for that week (Gamma-Poisson).

History means `completed` + `open` rentals, i.e. every pickup before day 1. Future bookings (`booked`)
never enter a history-based estimate (base, pickup rates, lengths, shock variance). They may be used to
condition the forecast on what is known at day 1 (committed car-days, week-1 demand level).

Findings behind the choices here: `Notes/Base Revenue.md`, `Notes/Demand.md` and the notebooks.
"""

from typing import Literal

import numpy as np
import pandas as pd

from fleetkit import Instance

HISTORY_STATUSES = ("completed", "open")


def rental_history(inst: Instance) -> pd.DataFrame:
    """Completed and open rentals (no future bookings), with derived columns.

    Added columns:
    - length: car-days, pickup and return day both counted
    - lead: days between booking and pickup
    - rev_per_day: revenue / length
    """
    r = inst.reservations
    r = r[r["status"].isin(HISTORY_STATUSES)].copy()
    for c in ["pickup_date", "return_date", "booking_date"]:
        r[c] = pd.to_datetime(r[c])
    r["length"] = (r["return_date"] - r["pickup_date"]).dt.days + 1
    r["lead"] = (r["pickup_date"] - r["booking_date"]).dt.days
    r["rev_per_day"] = r["revenue"] / r["length"]
    return r.reset_index(drop=True)


def base_revenue(inst: Instance, *, method: Literal["cell", "multiplicative"] = "cell") -> pd.DataFrame:
    """Base revenue per car-day per (station_id, category), estimated from completed rentals.

    The history is at the base price with no lost demand (README, Appendix B), so for each cell
    base_cell = sum(revenue) / sum(car-days). The multiplicative fit alpha_s * beta_k is a two-way
    decomposition of log(base_cell) with equal weights; it agrees with base_cell to within 1.6 %.

    Columns: station_id, category, base (the chosen method), base_cell, base_multiplicative,
    se (standard error of base_cell, ratio estimator), n_rentals, car_days.
    """
    h = rental_history(inst)
    h = h[h["status"] == "completed"]
    keys = ["pickup_station_id", "category"]
    out = h.groupby(keys).agg(revenue=("revenue", "sum"), car_days=("length", "sum"), n_rentals=("revenue", "size"))
    out["base_cell"] = out["revenue"] / out["car_days"]

    # SE of a ratio estimator: sqrt(sum L_i^2 (r_i - b)^2) / sum L_i, with r_i = R_i / L_i.
    b_i = h.set_index(keys).index.map(out["base_cell"]).to_numpy()
    sq = (h["length"] ** 2 * (h["rev_per_day"] - b_i) ** 2).groupby([h[k] for k in keys]).sum()
    out["se"] = np.sqrt(sq) / out["car_days"]

    log_b = np.log(out["base_cell"]).unstack("category")
    mu = log_b.to_numpy().mean()
    fit = np.exp(mu + (log_b.mean(axis=1) - mu).to_numpy()[:, None] + (log_b.mean(axis=0) - mu).to_numpy()[None, :])
    out["base_multiplicative"] = pd.DataFrame(fit, index=log_b.index, columns=log_b.columns).stack()

    if method not in ("cell", "multiplicative"):
        raise ValueError(f"unknown method {method!r}")
    out["base"] = out[f"base_{method}"]

    # Full grid in station / category-rank order; a cell without history would show up as NaN.
    order = inst.categories.sort_values("rank")["category"].tolist()
    idx = pd.MultiIndex.from_product([inst.stations["station_id"], order], names=["station_id", "category"])
    out = out.rename_axis(["station_id", "category"]).reindex(idx).reset_index()
    if out["base"].isna().any():
        raise ValueError("a station x category cell has no completed rentals")
    cols = ["station_id", "category", "base", "base_cell", "base_multiplicative", "se", "n_rentals", "car_days"]
    return out[cols].astype({"n_rentals": int, "car_days": int})


# --------------------------------------------------------------------------------------------
# Demand to come
# --------------------------------------------------------------------------------------------
KEY = ["station_id", "category", "day"]
WEEK = 7


def _horizon(inst: Instance) -> pd.DatetimeIndex:
    return pd.date_range(inst.horizon["first_date"].iloc[0], inst.horizon["last_date"].iloc[0])


def _categories(inst: Instance) -> list[str]:
    return inst.categories.sort_values("rank")["category"].tolist()


def _cells(inst: Instance) -> list[tuple[str, str]]:
    return [(s, k) for s in inst.stations["station_id"] for k in _categories(inst)]


def history_pickups(inst: Instance) -> pd.DataFrame:
    """Daily pickups per (station_id, category, date) over the history window, zeros included.

    The window runs from the first completed pickup to the day before day 1 (8 full weeks).
    Columns: station_id, category, date, weekday (0 = Monday), pickups.
    """
    h = rental_history(inst)
    first = h.loc[h["status"] == "completed", "pickup_date"].min()
    dates = pd.date_range(first, _horizon(inst)[0] - pd.Timedelta(days=1))
    idx = pd.MultiIndex.from_tuples(
        [(s, k, d) for s, k in _cells(inst) for d in dates], names=["station_id", "category", "date"]
    )
    out = (h.groupby(["pickup_station_id", "category", "pickup_date"]).size()
             .rename_axis(["station_id", "category", "date"]).reindex(idx, fill_value=0)
             .rename("pickups").reset_index())
    out["weekday"] = out["date"].dt.day_of_week
    return out


def pickup_rates(pickups: pd.DataFrame) -> pd.DataFrame:
    """Mean daily pickups lambda per (station_id, category, weekday) from a `history_pickups` table.

    Plain mean over the history weeks: weekly levels don't carry over, so recent weeks get no
    extra weight (Notes/Demand.md, section 4).
    """
    return (pickups.groupby(["station_id", "category", "weekday"])["pickups"].mean()
                   .rename("rate").reset_index())


def weekly_shock_variance(inst: Instance) -> float:
    """Var[G] of the weekly demand factor, method of moments on weekly pickup totals.

    Given the weekday rates, the weekly total W of a cell is NegBin with Var W = E W + v (E W)^2,
    so v = sum(Var W - mean W) / sum(mean W^2) over cells. About 0.017 (+-13 %).
    """
    p = history_pickups(inst)
    p["week"] = (p["date"] - p["date"].min()).dt.days // WEEK
    w = p.groupby(["station_id", "category", "week"])["pickups"].sum()
    g = w.groupby(level=[0, 1]).agg(["mean", "var"])
    return float(max((g["var"] - g["mean"]).sum() / (g["mean"] ** 2).sum(), 0.0))


def to_come_kernel(inst: Instance) -> dict[tuple[str, str], np.ndarray]:
    """K[p-1, l-1] = P(length = l, lead <= p-1) per (station_type, category), for p = 1..14.

    A pickup on horizon day p is demand to come iff it is booked on or after day 1, i.e.
    lead <= p - 1. Row sums are the to-come share P(lead <= p-1); one minus that is the share
    already booked before day 1. Joint empirical distribution, so no independence of length
    and lead is assumed.
    """
    h = rental_history(inst)
    h["station_type"] = h["pickup_station_id"].map(inst.stations.set_index("station_id")["station_type"])
    n_days, max_len = len(_horizon(inst)), int(h["length"].max())
    out = {}
    for (t, k), g in h.groupby(["station_type", "category"]):
        L, lead = g["length"].to_numpy(), g["lead"].to_numpy()
        K = np.zeros((n_days, max_len))
        for p in range(1, n_days + 1):
            sel = lead <= p - 1
            K[p - 1] = np.bincount(L[sel] - 1, minlength=max_len)[:max_len] / len(g)
        out[(t, k)] = K
    return out


def _cell_inputs(inst: Instance, rates: pd.DataFrame | None = None) -> dict[tuple[str, str], dict]:
    """Per cell: lambda for each horizon day, the to-come kernel, and the week of each day."""
    rates = pickup_rates(history_pickups(inst)) if rates is None else rates
    lam = rates.set_index(["station_id", "category", "weekday"])["rate"]
    kernel = to_come_kernel(inst)
    stype = inst.stations.set_index("station_id")["station_type"]
    dates = _horizon(inst)
    wd = dates.day_of_week.to_numpy()
    week = np.arange(len(dates)) // WEEK
    return {
        (s, k): {"lam": np.array([lam[(s, k, d)] for d in wd]), "K": kernel[(stype[s], k)], "week": week}
        for s, k in _cells(inst)
    }


def week_factors(inst: Instance, *, booking_update: bool = True) -> pd.DataFrame:
    """Gamma(shape, rate) of the demand factor G per (station_id, category, horizon week).

    Prior: shape = rate = 1/v (mean 1, variance v). With `booking_update`, each week is
    conditioned on its bookings made before day 1, which come from the same G (Gamma-Poisson):
      shape = 1/v + n_booked,  rate = 1/v + mu_booked,
    where n_booked = booked rentals picked up in that week and mu_booked = sum over its days of
    lambda * P(lead >= p). Future bookings are only used here, never in the history estimates.
    Columns: station_id, category, week (1, 2), n_booked, mu_booked, shape, rate, mean, v.
    """
    v = weekly_shock_variance(inst)
    prior = 1 / v if v > 0 else 1e9
    inputs = _cell_inputs(inst)
    dates = _horizon(inst)
    booked = inst.reservations[inst.reservations["status"] == "booked"]
    p_day = (pd.to_datetime(booked["pickup_date"]) - dates[0]).dt.days + 1
    booked = booked.assign(week=(p_day - 1) // WEEK + 1)
    n_b = booked.groupby(["pickup_station_id", "category", "week"]).size()
    rows = []
    for (s, k), c in inputs.items():
        already = c["lam"] * (1 - c["K"].sum(axis=1))          # expected pickups booked before day 1
        for w in np.unique(c["week"]):
            n = int(n_b.get((s, k, w + 1), 0)) if booking_update else 0
            mu = float(already[c["week"] == w].sum()) if booking_update else 0.0
            rows.append({"station_id": s, "category": k, "week": int(w + 1), "n_booked": n, "mu_booked": mu,
                         "shape": prior + n, "rate": prior + mu})
    out = pd.DataFrame(rows)
    out["mean"] = out["shape"] / out["rate"]
    out["v"] = v
    return out


def expected_demand(inst: Instance, *, booking_update: bool = True) -> pd.DataFrame:
    """E[D] and sd of the demand to come per (station_id, category, day): the model's `demand`.

    D[d] = cars on rent on day d from to-come pickups on days p <= d. Given the factors,
    m[d] = sum_p G[w(p)] lambda[p] P(length >= d-p+1, lead <= p-1) and D is Poisson(m), so
    E D = sum over weeks of E[G_w] m_w[d] and Var D = E D + sum_w Var[G_w] m_w[d]^2.
    Columns: station_id, category, day, demand, demand_sd.
    """
    inputs = _cell_inputs(inst)
    fac = week_factors(inst, booking_update=booking_update).set_index(["station_id", "category", "week"])
    rows = []
    for (s, k), c in inputs.items():
        n_days = len(c["lam"])
        m = np.zeros((n_days, n_days))                          # m[p, d]: from pickups on day p
        for p in range(n_days):
            surv = c["K"][p][::-1].cumsum()[::-1]               # P(length >= j+1, lead <= p)
            span = min(len(surv), n_days - p)
            m[p, p:p + span] = c["lam"][p] * surv[:span]
        mean, var = np.zeros(n_days), np.zeros(n_days)
        for w in np.unique(c["week"]):
            f = fac.loc[(s, k, int(w + 1))]
            m_w = m[c["week"] == w].sum(axis=0)
            mean += f["mean"] * m_w
            var += f["mean"] * m_w + f["shape"] / f["rate"] ** 2 * m_w ** 2
        rows += [{"station_id": s, "category": k, "day": d + 1, "demand": mean[d], "demand_sd": np.sqrt(var[d])}
                 for d in range(n_days)]
    return pd.DataFrame(rows)


def sample_demand(inst: Instance, n_scenarios: int, *, seed: int, booking_update: bool = True) -> pd.DataFrame:
    """Demand-to-come scenarios for our scorer and for SAA, from the model in the module docstring.

    Per scenario and cell: draw G for each horizon week, then to-come pickups per day
    ~ Poisson(G * lambda * P(lead <= p-1)), split them over lengths with P(length | lead <= p-1),
    and count the cars on rent per day (capped at day 14). Reproducible for a given seed.
    Columns: scenario, station_id, category, day, demand (int).
    """
    rng = np.random.default_rng(seed)
    inputs = _cell_inputs(inst)
    fac = week_factors(inst, booking_update=booking_update).set_index(["station_id", "category", "week"])
    frames = []
    for (s, k), c in inputs.items():
        n_days = len(c["lam"])
        weeks = np.unique(c["week"])
        G = np.column_stack([rng.gamma(fac.loc[(s, k, int(w + 1)), "shape"], 1 / fac.loc[(s, k, int(w + 1)), "rate"],
                                       size=n_scenarios) for w in weeks])           # (n, weeks)
        share = c["K"].sum(axis=1)                                                    # P(lead <= p-1)
        cond = c["K"] / np.where(share > 0, share, 1)[:, None]                        # P(length | to come)
        N = rng.poisson(G[:, c["week"]] * c["lam"] * share)                          # (n, days)
        M = rng.multinomial(N, cond)                                                  # (n, days, max_len)
        D = np.zeros((n_scenarios, n_days), dtype=np.int64)
        for p in range(n_days):
            on_rent = M[:, p, ::-1].cumsum(axis=1)[:, ::-1]                           # length >= j+1
            span = min(on_rent.shape[1], n_days - p)
            D[:, p:p + span] += on_rent[:, :span]
        frames.append(pd.DataFrame({
            "scenario": np.repeat(np.arange(n_scenarios), n_days), "station_id": s, "category": k,
            "day": np.tile(np.arange(1, n_days + 1), n_scenarios), "demand": D.ravel(),
        }))
    return pd.concat(frames, ignore_index=True)


def model_inputs(inst: Instance, *, booking_update: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(df_demand, df_base) in the format of `fleetopt.model_base`: expected demand and base revenue."""
    df_demand = expected_demand(inst, booking_update=booking_update)[KEY + ["demand"]]
    df_base = base_revenue(inst)[["station_id", "category", "base"]].rename(columns={"base": "base_revenue"})
    return df_demand, df_base


def booking_update_backtest(inst: Instance) -> pd.DataFrame:
    """Does conditioning on the bookings predict to-come pickups better? Pseudo-snapshot backtest.

    Every Monday t0 of the history plays day 1. For each cell and week w = 1, 2 inside the window:
    actual = pickups in week w booked on or after t0, n_booked = those booked before t0.
    Rates come from the history without the two weeks being predicted. Prediction without update:
    sum lambda * P(lead <= p-1); with update: times (1/v + n_booked) / (1/v + mu_booked).
    Returns one row per (t0, week, cell) with actual, pred_plain, pred_update.
    """
    h = rental_history(inst)
    pk = history_pickups(inst)
    v = weekly_shock_variance(inst)
    prior = 1 / v
    kernel = to_come_kernel(inst)
    stype = inst.stations.set_index("station_id")["station_type"]
    last = pk["date"].max()
    rows = []
    for t0 in sorted(d for d in pk["date"].unique() if pd.Timestamp(d).day_of_week == 0):
        t0 = pd.Timestamp(t0)
        held_out = (pk["date"] >= t0) & (pk["date"] < t0 + pd.Timedelta(days=2 * WEEK))
        lam = pickup_rates(pk[~held_out]).set_index(["station_id", "category", "weekday"])["rate"]
        for w in range(2):
            start = t0 + pd.Timedelta(days=w * WEEK)
            if start + pd.Timedelta(days=WEEK - 1) > last:
                continue
            in_week = h[(h["pickup_date"] >= start) & (h["pickup_date"] < start + pd.Timedelta(days=WEEK))]
            is_booked = in_week["booking_date"] < t0
            act = in_week[~is_booked].groupby(["pickup_station_id", "category"]).size()
            nb = in_week[is_booked].groupby(["pickup_station_id", "category"]).size()
            for s, k in _cells(inst):
                K = kernel[(stype[s], k)]
                lam_d = np.array([lam[(s, k, (start + pd.Timedelta(days=i)).day_of_week)] for i in range(WEEK)])
                share = K[w * WEEK:(w + 1) * WEEK].sum(axis=1)
                plain = float((lam_d * share).sum())
                mu_b = float((lam_d * (1 - share)).sum())
                n = int(nb.get((s, k), 0))
                rows.append({"t0": t0, "week": w + 1, "station_id": s, "category": k,
                             "actual": int(act.get((s, k), 0)), "n_booked": n, "mu_booked": mu_b,
                             "pred_plain": plain, "pred_update": plain * (prior + n) / (prior + mu_b)})
    return pd.DataFrame(rows)
