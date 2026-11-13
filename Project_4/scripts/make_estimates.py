"""Write all forecast estimates to estimates/: base revenue, demand parameters and scenarios.

Usage: Project_4/.venv/bin/python Project_4/scripts/make_estimates.py [--scenarios 200] [--seed 2026]
       [--no-booking-update]

The CSVs are for reading and for tools outside Python. Model and scorer code should call
`fleetopt.forecast` directly (model_inputs, sample_demand), which is the single source of truth.
Findings behind the numbers: Notes/Base Revenue.md and Notes/Demand.md.
"""

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fleetkit import load_instance  # noqa: E402
from fleetopt import forecast  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenarios", type=int, default=200, help="number of demand scenarios to write")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-booking-update", action="store_true", help="don't condition the weekly factors on bookings")
    args = ap.parse_args()
    update = not args.no_booking_update

    inst = load_instance(data_dir=PROJECT / "data")
    out = PROJECT / "estimates"
    out.mkdir(exist_ok=True)

    base = forecast.base_revenue(inst)
    base.round({"base": 2, "base_cell": 2, "base_multiplicative": 2, "se": 3}).to_csv(out / "base_revenue.csv", index=False)
    forecast.pickup_rates(forecast.history_pickups(inst)).round(4).to_csv(out / "pickup_rates.csv", index=False)
    factors = forecast.week_factors(inst, booking_update=update)
    factors.round(4).to_csv(out / "week_factors.csv", index=False)
    demand = forecast.expected_demand(inst, booking_update=update)
    demand.round(4).to_csv(out / "expected_demand.csv", index=False)
    scen = forecast.sample_demand(inst, args.scenarios, seed=args.seed, booking_update=update)
    scen.to_csv(out / "demand_scenarios.csv", index=False)

    print(f"base revenue: {len(base)} cells, max rel. SE {(base['se'] / base['base']).max():.2%}")
    print(f"weekly shock: v = {factors['v'].iloc[0]:.4f} (sd {factors['v'].iloc[0] ** 0.5:.1%}); "
          f"booking update {'on' if update else 'off'}, posterior means "
          f"{factors['mean'].min():.2f} .. {factors['mean'].max():.2f}")
    print(f"expected demand to come: {demand['demand'].sum():,.0f} car-days over 14 days")
    print(f"scenarios: {args.scenarios} (seed {args.seed}), mean total "
          f"{scen.groupby('scenario')['demand'].sum().mean():,.0f}, sd {scen.groupby('scenario')['demand'].sum().std():,.0f}")

    bt = forecast.booking_update_backtest(inst)
    for w, g in bt.groupby("week"):
        plain, upd = ((g["actual"] - g["pred_plain"]) ** 2).mean(), ((g["actual"] - g["pred_update"]) ** 2).mean()
        print(f"backtest week {w}: MSE of to-come pickups {plain:.1f} -> {upd:.1f} with the booking update ({upd / plain - 1:+.0%})")
    print(f"wrote {', '.join(sorted(p.name for p in out.glob('*.csv')))} to {out.relative_to(PROJECT.parent)}/")


if __name__ == "__main__":
    main()
