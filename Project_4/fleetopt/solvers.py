"""One place where a solver name becomes a PuLP solver ([[Decisions]]).

The submission must run open source: `highs` is the default, `cbc` the fallback.
`gurobi` is here as an escape hatch only (never in requirements.txt, use after we agree).
"""

import pulp


def get_solver(
    name: str = "highs",
    *,
    time_limit: float | None = None,
    gap_rel: float | None = None,
    msg: bool = False,
) -> pulp.LpSolver:
    """Build a solver by name with the usual limits."""
    kwargs: dict = {"msg": msg}
    if time_limit is not None:
        kwargs["timeLimit"] = time_limit
    if gap_rel is not None:
        kwargs["gapRel"] = gap_rel
    match name.lower():
        case "highs":
            return pulp.HiGHS(**kwargs)
        case "cbc":
            return pulp.COIN_CMD(**kwargs)
        case "gurobi":
            return pulp.GUROBI(**kwargs)
        case _:
            raise ValueError(f"unknown solver {name!r}: use highs, cbc or gurobi")
