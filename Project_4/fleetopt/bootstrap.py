"""Demand-to-come scenarios by a block bootstrap of the history weeks (no demand model).

Alternative to `forecast.sample_demand`, which samples a fitted Gamma-Poisson model. Here every
horizon week replays one history week as it happened:

- The history has 8 full weeks, aligned with the horizon (both start on a Monday).
- History week h played as horizon week j: each rental picked up in week h at weekday offset o
  gets pickup day p = 7 j + o + 1 and keeps its own length and lead. It is demand to come iff it
  would be booked on or after day 1, i.e. lead <= p - 1, the same rule as `forecast.to_come_kernel`.
  Its car-days count at the pickup station on days p .. p + length - 1, capped at day 14.
- A scenario is one history week per horizon week, drawn with replacement, independent across
  the two horizon weeks (weekly levels don't carry over, Notes/Demand.md).

`block="network"` uses the same history week for every cell, so it keeps whatever correlation
across stations and categories the history has (the parametric model assumes none).
`block="cell"` draws the weeks per cell, which matches the parametric independence assumption.
With `network` there are only 8 x 8 = 64 distinct scenarios; `all_week_pairs` enumerates them.

What the bootstrap does not do: condition on the bookings already made for the horizon (the
booking update of `forecast.week_factors`), or produce anything the 8 weeks have not seen.
"""

from typing import Literal

import numpy as np
import pandas as pd

from fleetkit import Instance
from fleetopt import forecast

WEEK = forecast.WEEK


def week_replays(inst: Instance) -> tuple[np.ndarray, list[tuple[str, str]]]:
    """A[h, j, c, d]: car-days to come on horizon day d+1 in cell c if history week h is horizon week j.

    Returns the array (history weeks x horizon weeks x cells x days) and the cell order.
    """
    h = forecast.rental_history(inst)
    dates = forecast._horizon(inst)
    n_days = len(dates)
    n_hweeks = n_days // WEEK
    first = h.loc[h["status"] == "completed", "pickup_date"].min()
    n_weeks = (dates[0] - first).days // WEEK                       # full history weeks before day 1
    start = dates[0] - pd.Timedelta(days=n_weeks * WEEK)
    cells = forecast._cells(inst)
    cell_idx = {c: i for i, c in enumerate(cells)}

    offset = (h["pickup_date"] - start).dt.days.to_numpy()
    keep = (offset >= 0) & (offset < n_weeks * WEEK)
    h, offset = h[keep], offset[keep]
    week, o = offset // WEEK, offset % WEEK
    c = np.array([cell_idx[(s, k)] for s, k in zip(h["pickup_station_id"], h["category"])])
    L, lead = h["length"].to_numpy(), h["lead"].to_numpy()

    A = np.zeros((n_weeks, n_hweeks, len(cells), n_days), dtype=np.int64)
    for j in range(n_hweeks):
        p = WEEK * j + o + 1                                         # horizon pickup day, 1-based
        to_come = lead <= p - 1
        for t in range(int(L.max())):                                # t-th day on rent
            on = to_come & (L > t) & (p + t <= n_days)
            np.add.at(A, (week[on], j, c[on], p[on] + t - 1), 1)
    return A, cells


def _frame(D: np.ndarray, cells: list[tuple[str, str]]) -> pd.DataFrame:
    """D[n, c, d] -> long table: scenario, station_id, category, day, demand."""
    n, n_cells, n_days = D.shape
    return pd.DataFrame({
        "scenario": np.repeat(np.arange(n), n_cells * n_days),
        "station_id": np.tile(np.repeat([s for s, _ in cells], n_days), n),
        "category": np.tile(np.repeat([k for _, k in cells], n_days), n),
        "day": np.tile(np.arange(1, n_days + 1), n * n_cells),
        "demand": D.ravel(),
    })


def bootstrap_demand(inst: Instance, n_scenarios: int, *, seed: int,
                     block: Literal["network", "cell"] = "network") -> pd.DataFrame:
    """Bootstrap demand-to-come scenarios; same columns as `forecast.sample_demand`.

    Columns: scenario, station_id, category, day, demand (int). Reproducible for a given seed.
    """
    if block not in ("network", "cell"):
        raise ValueError(f"unknown block {block!r}")
    A, cells = week_replays(inst)
    n_weeks, n_hweeks, n_cells, n_days = A.shape
    rng = np.random.default_rng(seed)
    shape = (n_scenarios, n_hweeks) if block == "network" else (n_scenarios, n_hweeks, n_cells)
    draw = rng.integers(n_weeks, size=shape)
    D = np.zeros((n_scenarios, n_cells, n_days), dtype=np.int64)
    for j in range(n_hweeks):
        if block == "network":
            D += A[draw[:, j], j]                                    # (n, cells, days)
        else:
            D += A[draw[:, j, :], j, np.arange(n_cells)[None, :]]
    return _frame(D, cells)


def all_week_pairs(inst: Instance) -> pd.DataFrame:
    """Every network scenario (one history week per horizon week), each once: the exact bootstrap law."""
    A, cells = week_replays(inst)
    n_weeks, n_hweeks = A.shape[:2]
    combos = np.array(np.meshgrid(*[np.arange(n_weeks)] * n_hweeks, indexing="ij")).reshape(n_hweeks, -1).T
    D = sum(A[combos[:, j], j] for j in range(n_hweeks))
    return _frame(D, cells)
