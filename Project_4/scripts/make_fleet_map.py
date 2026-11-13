"""Build the animated fleet map for the talk: a reference plan (default: the baseline) vs. our plan over the 14 days.

Usage: Project_4/.venv/bin/python Project_4/scripts/make_fleet_map.py [plans/final.csv]
       [--reference plans/baseline.csv] [--reference-label Baseline]
       [--scenarios 500] [--seed 2026] [--out submission/fleet_map.html]

Writes one self-contained HTML file (open it in a browser; Space plays, arrows step a day).
The numbers are means over the same seeded scenarios as scripts/score_plans.py.
"""

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fleetkit import load_instance  # noqa: E402
from fleetopt import fleetmap, forecast  # noqa: E402
from fleetopt.evaluate import check_validity, read_plan  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plan", nargs="?", type=Path, default=PROJECT / "plans" / "final.csv")
    ap.add_argument("--reference", type=Path, default=PROJECT / "plans" / "baseline.csv",
                    help="plan shown in the upper map (plans/do_nothing.csv for no actions)")
    ap.add_argument("--reference-label", default=None, help="its title; default: from the file name")
    ap.add_argument("--scenarios", type=int, default=500)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", type=Path, default=PROJECT / "submission" / "fleet_map.html")
    args = ap.parse_args()

    inst = load_instance(data_dir=PROJECT / "data")
    plan, reference = read_plan(args.plan), read_plan(args.reference)
    for path, p in [(args.plan, plan), (args.reference, reference)]:
        errors = check_validity(inst, p)
        if errors:
            raise SystemExit(f"{path}: INVALID, {len(errors)} violations, e.g. {errors[0]}")
    label = args.reference_label or args.reference.stem.replace("_", " ").capitalize()
    _, base = forecast.model_inputs(inst)
    scen = forecast.sample_demand(inst, args.scenarios, seed=args.seed)

    data = fleetmap.map_data(inst, plan, scen, base, reference=reference, reference_label=label)
    data["plan_file"], data["ref_file"], data["seed"] = args.plan.name, args.reference.name, args.seed
    args.out.write_text(fleetmap.render_html(data), encoding="utf-8")
    t = data["totals"]
    print(f"{args.out}: {args.reference.name} {t['ref']['profit']:,.0f}, {args.plan.name} {t['plan']['profit']:,.0f} "
          f"(mean over {args.scenarios} scenarios, seed {args.seed})")


if __name__ == "__main__":
    main()
