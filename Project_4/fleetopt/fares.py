"""Fare adjustment as model input: expected-revenue curves from demand scenarios.

`model_base.demand_buckets` turns the price factors into buckets for a *point* forecast of the
demand D. Here the buckets come from the *distribution* of D instead: for free capacity a of a
cell (cars available for demand to come, own category only),

    Rbar(a) = mean over scenarios w of  rev(min(D_w, a), D_w)          (R8, per scenario)

is the expected revenue. On a capacity grid a_0 = 0 < a_1 < ... it becomes buckets of size
a_{j+1} - a_j with marginal (Rbar(a_{j+1}) - Rbar(a_j)) / size, in the same format as
`demand_buckets`, so the MIP can use either. Upgrades are not in these curves (see
Project Plan section 3: objective comparison).
"""

import numpy as np
import pandas as pd

from fleetkit import Instance
from fleetopt.evaluate import fare_revenue

KEY = ["station_id", "category", "day"]
EPS = 1e-9


def expected_revenue_curves(
    inst: Instance,
    scenarios: pd.DataFrame,
    df_base: pd.DataFrame,
    *,
    max_segments: int | None = 20,
    concave_tol: float = 1.0,
) -> pd.DataFrame:
    """Buckets of the expected-revenue curve per (station_id, category, day).

    scenarios: scenario, station_id, category, day, demand (e.g. `forecast.sample_demand`).
    df_base: station_id, category, base_revenue.
    The grid has integer steps of max(1, ceil(A / max_segments)), where A = the largest demand
    of the cell over the scenarios; beyond A an extra car earns nothing. With
    `max_segments=None` the grid is every kink of every scenario's revenue (D * share and D),
    so the curve is exactly the SAA revenue without upgrades (use with a tiny `concave_tol`). Buckets with a
    zero marginal are dropped. A cell counts as concave if no marginal rises by more than
    `concave_tol` (EUR per car-day): averaging over scenarios leaves only numerical wiggles. Columns as `model_base.demand_buckets`: station_id, category,
    day, bucket, size, marginal, concave.
    """
    stype = inst.stations.set_index("station_id")["station_type"]
    base = df_base.set_index(["station_id", "category"])["base_revenue"]
    pf = inst.price_factors.sort_values("served_share")
    pf_by = {key: (g["served_share"].to_numpy(float), g["price_factor"].to_numpy(float))
             for key, g in pf.groupby(["station_type", "category"])}

    rows = []
    for (s, k, d), g in scenarios.groupby(KEY, sort=True):
        D = g["demand"].to_numpy(float)
        top = D.max()
        if top <= 0:
            continue
        shares, factors = pf_by[(stype[s], k)]
        if max_segments is None:
            grid = np.unique(np.concatenate([[0.0], (D[:, None] * shares[None, :]).ravel()]))
        else:
            step = max(1, int(np.ceil(top / max_segments)))
            grid = np.unique(np.minimum(np.arange(0, top + step, step, dtype=float), top))
        served = np.minimum(D[None, :], grid[:, None])                      # (grid, scenarios)
        rbar = fare_revenue(served, np.broadcast_to(D, served.shape), base[(s, k)], shares, factors).mean(axis=1)
        size = np.diff(grid)
        marg = np.diff(rbar) / size
        keep = marg > EPS
        size, marg = size[keep], marg[keep]
        concave = bool(np.all(np.diff(marg) <= concave_tol))
        for b, (sz, mg) in enumerate(zip(size, marg), start=1):
            rows.append({"station_id": s, "category": k, "day": int(d), "bucket": b,
                         "size": float(sz), "marginal": float(mg), "concave": concave})
    return pd.DataFrame(rows, columns=[*KEY, "bucket", "size", "marginal", "concave"])


def curve_value(buckets: pd.DataFrame, capacity: pd.DataFrame) -> float:
    """Expected revenue the curves promise for given free capacities (station_id, category, day, free)."""
    cap = capacity.set_index(KEY)["free"]
    total = 0.0
    for key, g in buckets.groupby(KEY):
        left = float(cap.get(key, 0.0))
        for sz, mg in zip(g["size"], g["marginal"]):
            take = min(sz, max(left, 0.0))
            total += take * mg
            left -= take
    return total
