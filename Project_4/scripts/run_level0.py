"""Level 0: check our tables against check_values.csv and print a short summary.

Usage: Project_4/.venv/bin/python Project_4/scripts/run_level0.py [plan.csv ...]
Any plan CSVs given are also checked for validity (R5).
"""

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fleetkit import load_instance  # noqa: E402
from fleetopt.evaluate import check_validity, read_plan  # noqa: E402
from fleetopt.level0 import check_against_reference, level0_table, max_removable  # noqa: E402


def main() -> None:
    inst = load_instance(data_dir=PROJECT / "data")
    bad = check_against_reference(inst)
    print(f"check_values.csv: {len(inst.check_values) - len(bad)}/{len(inst.check_values)} rows match")
    if not bad.empty:
        print(bad.to_string(index=False))

    t = level0_table(inst)
    t["max_removable"] = max_removable(t)
    day1 = t[t["day"] == 1]
    summary = t.groupby("category").agg(
        committed_car_days=("committed_car_days", "sum"),
        min_slack=("slack", "min"),
        zero_slack_cells=("slack", lambda s: int((s == 0).sum())),
    )
    summary.insert(0, "fleet_day1", day1.groupby("category")["station_fleet"].sum())
    summary["removable_day1"] = day1.groupby("category")["max_removable"].sum()
    print("\nDo-nothing plan per category (cells = station x day):")
    print(summary.loc[inst.categories.sort_values("rank")["category"]].to_string())

    for arg in sys.argv[1:]:
        errors = check_validity(inst, read_plan(Path(arg)))
        print(f"\n{arg}: {'VALID' if not errors else f'INVALID ({len(errors)} violations)'}")
        for e in errors[:50]:
            print("  " + e)


if __name__ == "__main__":
    main()
