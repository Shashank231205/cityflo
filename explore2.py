import pandas as pd
import numpy as np

pings = pd.read_csv("data/gps_pings.csv", parse_dates=["recorded_at", "received_at"])
trips = pd.read_csv("data/trips.csv", parse_dates=["scheduled_start", "scheduled_end"])
routes = pd.read_csv("data/routes.csv")
stops = pd.read_csv("data/stops.csv")

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dlmb/2)**2
    return 2*R*np.arcsin(np.sqrt(a))

# point-to-point implied speed vs reported speed_kmph -> flags GPS jumps
pings_sorted = pings.sort_values(["vehicle_id","recorded_at"]).reset_index(drop=True)
pings_sorted["prev_lat"] = pings_sorted.groupby("vehicle_id")["lat"].shift(1)
pings_sorted["prev_lon"] = pings_sorted.groupby("vehicle_id")["lon"].shift(1)
pings_sorted["prev_t"] = pings_sorted.groupby("vehicle_id")["recorded_at"].shift(1)
pings_sorted["dt_s"] = (pings_sorted["recorded_at"] - pings_sorted["prev_t"]).dt.total_seconds()
pings_sorted["dist_m"] = haversine_m(pings_sorted["prev_lat"], pings_sorted["prev_lon"], pings_sorted["lat"], pings_sorted["lon"])
pings_sorted["implied_kmph"] = (pings_sorted["dist_m"]/1000) / (pings_sorted["dt_s"]/3600)

# only within-trip consecutive pings (dt < 60s, i.e. not the overnight boundary)
within = pings_sorted[(pings_sorted["dt_s"] > 0) & (pings_sorted["dt_s"] < 60)]

print("=== implied speed vs reported speed: biggest mismatches ===")
within = within.copy()
within["speed_diff"] = (within["implied_kmph"] - within["speed_kmph"]).abs()
print(within.reindex(within["speed_diff"].sort_values(ascending=False).index).head(15)
      [["vehicle_id","recorded_at","dt_s","dist_m","implied_kmph","speed_kmph"]])

print("\n=== implausible implied speeds (>80 kmph, i.e. GPS jump/teleport) ===")
jumps = within[within["implied_kmph"] > 80]
print(jumps[["vehicle_id","recorded_at","dt_s","dist_m","implied_kmph","speed_kmph"]])

print("\n=== near-zero displacement bursts (speed>0 reported but not moving) ===")
stuck = within[(within["dist_m"] < 2) & (within["speed_kmph"] > 5)]
print(stuck[["vehicle_id","recorded_at","dt_s","dist_m","implied_kmph","speed_kmph"]].head(20))
print(f"count: {len(stuck)}")

print("\n=== idling clusters: consecutive near-zero speed runs per vehicle/day ===")
pings_sorted["date"] = pings_sorted["recorded_at"].dt.date
pings_sorted["is_idle"] = pings_sorted["speed_kmph"] < 2
idle_runs = []
for (veh, date), g in pings_sorted.groupby(["vehicle_id","date"]):
    g = g.sort_values("recorded_at")
    run_id = (g["is_idle"] != g["is_idle"].shift()).cumsum()
    for rid, seg in g.groupby(run_id):
        if seg["is_idle"].iloc[0] and len(seg) >= 3:
            dur = (seg["recorded_at"].iloc[-1] - seg["recorded_at"].iloc[0]).total_seconds()
            if dur >= 60:
                idle_runs.append((veh, date, seg["recorded_at"].iloc[0], seg["recorded_at"].iloc[-1], dur, len(seg)))
idle_df = pd.DataFrame(idle_runs, columns=["vehicle_id","date","start","end","dur_s","n_pings"])
print(idle_df.sort_values("dur_s", ascending=False).head(20))
