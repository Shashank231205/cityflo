"""
CLI: is route X running late right now?

Usage:
    py query.py --route 21 --as-of "2026-06-15T09:00:00+05:30"
    py query.py --route 12 --as-of "2026-06-16T07:40:00+05:30"
"""
import argparse
import pandas as pd
from lateness import build_pipeline, lateness_for_route


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", type=int, required=True)
    ap.add_argument("--as-of", type=str, required=True, help="ISO timestamp, e.g. 2026-06-15T09:00:00+05:30")
    args = ap.parse_args()

    as_of = pd.Timestamp(args.__dict__["as_of"])
    ctx = build_pipeline()
    result = lateness_for_route(args.route, as_of, ctx["trips"], ctx["routes"], ctx["geo"], ctx["cleaned_by_trip"])

    print(f"\nRoute {args.route} as of {as_of}\n" + "-" * 40)
    if result["verdict"] == "ok":
        sign = "late" if result["lateness_min"] >= 0 else "early"
        print(f"  {abs(result['lateness_min'])} min {sign}")
        print(f"  actual position:   {result['actual_dist_m']:.0f} m / {result['route_length_m']:.0f} m along route")
        print(f"  expected position: {result['expected_dist_m']:.0f} m along route (at scheduled pace)")
        print(f"  last ping:         {result['last_ping_at']}  ({result['staleness_s']:.0f}s old, {result['freshness']})")
        print(f"  trip / vehicle:    {result['trip_id']} / {result['vehicle_id']}")
    elif result["verdict"] == "stale_unconfirmed":
        print("  VERDICT WITHHELD -- signal too stale to trust a live number.")
        print(f"  {result['reason']}")
        print(f"  last known lateness (at {result['last_ping_at']}): {result['last_known_lateness_min_AT_last_ping']} min")
        print(f"  trip / vehicle: {result['trip_id']} / {result['vehicle_id']}")
    else:
        print(f"  {result['verdict']}: {result.get('reason','')}")
    print()


if __name__ == "__main__":
    main()
