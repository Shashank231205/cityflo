import pandas as pd
import numpy as np

pings = pd.read_csv("data/gps_pings.csv", parse_dates=["recorded_at", "received_at"])
trips = pd.read_csv("data/trips.csv", parse_dates=["scheduled_start", "scheduled_end"])
routes = pd.read_csv("data/routes.csv")
stops = pd.read_csv("data/stops.csv")
bookings = pd.read_csv("data/bookings.csv", parse_dates=["booked_at", "promised_eta"])

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)

print("=== clock skew: recorded_at vs received_at ===")
pings["skew_s"] = (pings["received_at"] - pings["recorded_at"]).dt.total_seconds()
print(pings["skew_s"].describe())
print("\nlargest |skew| rows:")
print(pings.reindex(pings["skew_s"].abs().sort_values(ascending=False).index).head(15)
      [["ping_id","vehicle_id","operator_id","recorded_at","received_at","skew_s","speed_kmph"]])

print("\n=== speed distribution ===")
print(pings["speed_kmph"].describe())

print("\n=== zero-speed ping counts per vehicle ===")
print(pings.groupby("vehicle_id").apply(lambda g: (g["speed_kmph"] == 0).sum()))

print("\n=== pings per vehicle per day ===")
pings["date"] = pings["recorded_at"].dt.date
print(pings.groupby(["vehicle_id","date"]).size())

print("\n=== ping interval gaps (potential dropout) ===")
pings_sorted = pings.sort_values(["vehicle_id","recorded_at"])
pings_sorted["gap_s"] = pings_sorted.groupby("vehicle_id")["recorded_at"].diff().dt.total_seconds()
big_gaps = pings_sorted[pings_sorted["gap_s"] > 60]
print(big_gaps[["vehicle_id","recorded_at","gap_s"]])
