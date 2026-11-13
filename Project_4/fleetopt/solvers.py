"""One place where a solver name becomes a PuLP solver ([[Decisions]]).

The submission must run open source: `highs` is the default, `cbc` the fallback.
`gurobi` is here as an escape hatch only (never in requirements.txt, use after we agree).
"""

import math

import pulp
from pulp import constants


class _FastGUROBI(pulp.GUROBI):
    """pulp.GUROBI with a batched model build.

    PuLP's own build adds one variable at a time and looks up each objective coefficient
    separately: about 9 minutes on the L1 SAA, against a 46 s solve. Here the variables go in
    with one `addVars` call and the rows with `addLConstr`. Values and status are read back
    by pulp.GUROBI unchanged.
    """

    def buildSolverModel(self, lp: pulp.LpProblem):
        import gurobipy as gp

        GRB = gp.GRB
        self.initGurobi()
        m = self.model
        m.ModelName = lp.name
        lp.solverModel = m
        self._silence(m)
        if lp.sense == constants.LpMaximize:
            m.ModelSense = -1
        self._set_params(m)

        xs = lp.exported_variables()
        col = {v.id: j for j, v in enumerate(xs)}
        obj = [0.0] * len(xs)
        for v, a in lp.objective.items():
            if v.id in col:
                obj[col[v.id]] = a
        m.ObjCon = lp.objective.constant

        def bound(b, default):
            return default if b is None or not math.isfinite(b) else b

        added = m.addVars(
            len(xs),
            lb=[bound(v.lowBound, -GRB.INFINITY) for v in xs],
            ub=[bound(v.upBound, GRB.INFINITY) for v in xs],
            obj=obj,
            vtype=[GRB.INTEGER if v.cat == constants.LpInteger and self.mip else GRB.CONTINUOUS for v in xs],
            name=[v.name for v in xs],
        )
        m.update()
        var_handles = [added[j] for j in range(len(xs))]

        sense = {constants.LpConstraintLE: GRB.LESS_EQUAL, constants.LpConstraintGE: GRB.GREATER_EQUAL,
                 constants.LpConstraintEQ: GRB.EQUAL}
        constr_handles = []
        for c in lp.constraints():   # same order pulp.GUROBI reads the slacks back in
            coefs, gvars = [], []
            for v, a in c.items():
                if a != 0:
                    coefs.append(a)
                    gvars.append(var_handles[col[v.id]])
            constr_handles.append(m.addLConstr(gp.LinExpr(coefs, gvars), sense[c.sense], -c.constant, name=c.name))
        m.update()
        return var_handles, constr_handles


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
            return _FastGUROBI(**kwargs)
        case _:
            raise ValueError(f"unknown solver {name!r}: use highs, cbc or gurobi")
