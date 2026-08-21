"""
Cityflo take-home: "Is route X running late right now?"

Pipeline: raw pings -> cleaned vehicle-trip trajectory -> distance-along-route
-> lateness verdict for a (route, as_of) query.

Grain: one row per accepted (vehicle_id, trip_id, ping) after cleaning; the
lateness verdict is computed per (route_id, as_of) by resolving the single
active trip on that route at that timestamp.

See MEMO.md for the reasoning behind every choice below.
"""
import pandas as pd
import numpy as np

R_EARTH_M = 6371000.0


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R_EARTH_M * np.arcsin(np.sqrt(a))


def load_data(data_dir="data"):
    pings = pd.read_csv(f"{data_dir}/gps_pings.csv", parse_dates=["recorded_at", "received_at"])
    trips = pd.read_csv(f"{data_dir}/trips.csv", parse_dates=["scheduled_start", "scheduled_end"])
    routes = pd.read_csv(f"{data_dir}/routes.csv")
    stops = pd.read_csv(f"{data_dir}/stops.csv")
    bookings = pd.read_csv(f"{data_dir}/bookings.csv", parse_dates=["booked_at", "promised_eta"])
    return pings, trips, routes, stops, bookings


def build_route_geometry(stops: pd.DataFrame):
    """route_id -> dict(cum_dist=[...], lat=[...], lon=[...], length_m=float)"""
    geo = {}
    for route_id, g in stops.sort_values("seq").groupby("route_id"):
        lats, lons = g["lat"].to_numpy(), g["lon"].to_numpy()
        seg_len = haversine_m(lats[:-1], lons[:-1], lats[1:], lons[1:])
        cum = np.concatenate([[0.0], np.cumsum(seg_len)])
        geo[route_id] = dict(lat=lats, lon=lons, cum_dist=cum, length_m=cum[-1])
    return geo


def project_to_route(lat, lon, geo_entry):
    """
    Project a point onto the route polyline (stop-to-stop segments).
    Returns (distance_along_route_m, lateral_offset_m) using the nearest
    segment by perpendicular (approximate, equirectangular) distance.
    Good enough at this scale (~km route, ~metres-to-tens-of-metres offsets);
    NOT survey-grade -- see MEMO.md caveat on stop geometry.
    """
    lats, lons, cum = geo_entry["lat"], geo_entry["lon"], geo_entry["cum_dist"]
    best_dist_along = None
    best_offset = None
    # local equirectangular projection around the point for flat-plane segment math
    lat0 = np.radians(lat)
    mx = R_EARTH_M * np.cos(lat0)
    my = R_EARTH_M
    px = np.radians(lon) * mx
    py = np.radians(lat) * my

    for i in range(len(lats) - 1):
        ax, ay = np.radians(lons[i]) * mx, np.radians(lats[i]) * my
        bx, by = np.radians(lons[i + 1]) * mx, np.radians(lats[i + 1]) * my
        abx, aby = bx - ax, by - ay
        seg_len2 = abx ** 2 + aby ** 2
        if seg_len2 == 0:
            t = 0.0
        else:
            t = ((px - ax) * abx + (py - ay) * aby) / seg_len2
            t = max(0.0, min(1.0, t))
        cx, cy = ax + t * abx, ay + t * aby
        offset = np.hypot(px - cx, py - cy)
        dist_along = cum[i] + t * (cum[i + 1] - cum[i])
        if best_offset is None or offset < best_offset:
            best_offset, best_dist_along = offset, dist_along
    return best_dist_along, best_offset


def clean_trip_pings(trip_pings: pd.DataFrame, geo_entry, max_kmph=85.0, max_offset_m=600.0):
    """
    Online outlier gate over a single vehicle-trip's pings, time-ordered by
    received_at (see MEMO.md for why received_at is the canonical clock).

    A ping is accepted only if:
      - it projects within max_offset_m of the route polyline (drops wild
        GPS smear / off-route noise), AND
      - the implied speed from the *last accepted* ping is <= max_kmph.

    Comparing against the last *accepted* ping (not the last *seen* one) is
    what lets this reject a whole cluster of mutually-consistent-but-wrong
    pings (e.g. a duplicate/phantom stream) instead of just its boundary.
    """
    tp = trip_pings.sort_values("received_at").copy()
    dist_along, offset = zip(*[project_to_route(r.lat, r.lon, geo_entry) for r in tp.itertuples()])
    tp["dist_along_m"] = dist_along
    tp["route_offset_m"] = offset

    accepted_idx = []
    last_t, last_d = None, None
    for row in tp.itertuples():
        if row.route_offset_m > max_offset_m:
            continue
        if last_t is not None:
            dt_h = (row.received_at - last_t).total_seconds() / 3600.0
            if dt_h <= 0:
                continue
            implied_kmph = abs(row.dist_along_m - last_d) / 1000.0 / dt_h
            if implied_kmph > max_kmph:
                continue
        accepted_idx.append(row.Index)
        last_t, last_d = row.received_at, row.dist_along_m
    return tp.loc[accepted_idx]


def lateness_for_route(route_id, as_of, trips, routes, geo, cleaned_pings_by_trip, service_date=None):
    """
    Definition of "late": progress-deficit-at-scheduled-pace.
    expected_dist(as_of) = route_length * (as_of - scheduled_start) / scheduled_runtime_min
    actual_dist(as_of)   = distance-along-route of the latest accepted ping at/before as_of
    lateness_min = (expected_dist - actual_dist) / (route_length / scheduled_runtime_min)
    i.e. "how many minutes of scheduled-pace running does the position gap represent."
    See MEMO.md "the verdict path" for why this definition was chosen over the
    three alternatives (timetable-only, promised_eta, distance-remaining-at-current-speed).
    """
    if service_date is None:
        service_date = as_of.date()
    route_trips = trips[(trips.route_id == route_id) & (trips.scheduled_start.dt.date == service_date)]
    if route_trips.empty:
        return {"verdict": "no_trip", "reason": f"no scheduled trip for route {route_id} on {service_date}"}

    # active trip = as_of within [scheduled_start - 10min, scheduled_end + 20min]
    active = route_trips[
        (as_of >= route_trips.scheduled_start - pd.Timedelta(minutes=10))
        & (as_of <= route_trips.scheduled_end + pd.Timedelta(minutes=20))
    ]
    if active.empty:
        return {"verdict": "no_active_trip", "reason": f"no route-{route_id} trip active at {as_of}"}
    trip = active.iloc[0]

    route_row = routes[routes.route_id == route_id].iloc[0]
    geo_entry = geo[route_id]
    length_m = geo_entry["length_m"]
    runtime_min = route_row.scheduled_runtime_min
    scheduled_pace_m_per_min = length_m / runtime_min

    if as_of < trip.scheduled_start:
        return {"verdict": "not_departed", "trip_id": trip.trip_id,
                "reason": f"as_of is before scheduled_start ({trip.scheduled_start})"}

    elapsed_min = (as_of - trip.scheduled_start).total_seconds() / 60.0
    expected_dist_m = min(length_m, scheduled_pace_m_per_min * elapsed_min)

    cp = cleaned_pings_by_trip.get(trip.trip_id)
    if cp is None or cp.empty:
        return {"verdict": "no_signal", "trip_id": trip.trip_id, "reason": "no accepted pings for this trip"}

    live = cp[cp.received_at <= as_of]
    if live.empty:
        return {"verdict": "no_signal_yet", "trip_id": trip.trip_id,
                "reason": f"no accepted ping at/before {as_of} (earliest accepted: {cp.received_at.min()})"}

    last_ping = live.iloc[-1]
    staleness_s = (as_of - last_ping.received_at).total_seconds()
    actual_dist_m = last_ping.dist_along_m

    gap_m = expected_dist_m - actual_dist_m
    lateness_min = gap_m / scheduled_pace_m_per_min

    # STALE_SIGNAL_S: past this, the last-known position is too old to stand
    # in for "right now" -- report it as a stale HISTORICAL read, not a live
    # verdict. Threshold: at the nominal ~10s cadence, 5 min of silence is
    # ~30 missed pings in a row -- well past normal jitter/GSM reconnect,
    # into "device/vehicle went dark" territory. See MEMO.md.
    STALE_SIGNAL_S = 300
    if staleness_s > STALE_SIGNAL_S:
        return {
            "verdict": "stale_unconfirmed",
            "trip_id": trip.trip_id,
            "vehicle_id": trip.vehicle_id,
            "as_of": as_of,
            "reason": f"last accepted ping is {staleness_s:.0f}s ({staleness_s/60:.0f} min) old -- "
                      f"withholding a live lateness number rather than extrapolating it.",
            "last_known_lateness_min_AT_last_ping": round(
                (min(length_m, scheduled_pace_m_per_min * (last_ping.received_at - trip.scheduled_start).total_seconds() / 60.0)
                 - actual_dist_m) / scheduled_pace_m_per_min, 1),
            "last_ping_at": last_ping.received_at,
            "staleness_s": round(staleness_s, 0),
        }

    freshness_flag = "stale" if staleness_s > 90 else "fresh"

    return {
        "verdict": "ok",
        "trip_id": trip.trip_id,
        "vehicle_id": trip.vehicle_id,
        "as_of": as_of,
        "lateness_min": round(lateness_min, 1),
        "expected_dist_m": round(expected_dist_m, 0),
        "actual_dist_m": round(actual_dist_m, 0),
        "route_length_m": round(length_m, 0),
        "last_ping_at": last_ping.received_at,
        "staleness_s": round(staleness_s, 0),
        "freshness": freshness_flag,
        "route_offset_m": round(last_ping.route_offset_m, 0),
    }


def build_pipeline():
    pings, trips, routes, stops, bookings = load_data()
    geo = build_route_geometry(stops)

    # attach trip_id to pings: a vehicle's ping belongs to whichever of its
    # trips has the closest scheduled window (buffer +/- 20 min), by received_at
    trips_by_vehicle = {v: g.sort_values("scheduled_start") for v, g in trips.groupby("vehicle_id")}

    def assign_trip(row):
        vt = trips_by_vehicle.get(row.vehicle_id)
        if vt is None:
            return None
        window = vt[
            (row.received_at >= vt.scheduled_start - pd.Timedelta(minutes=20))
            & (row.received_at <= vt.scheduled_end + pd.Timedelta(minutes=20))
        ]
        if window.empty:
            return None
        return window.iloc[0].trip_id

    pings = pings.copy()
    pings["trip_id"] = pings.apply(assign_trip, axis=1)
    pings = pings.dropna(subset=["trip_id"])

    cleaned_by_trip = {}
    for trip_id, g in pings.groupby("trip_id"):
        route_id = trips.loc[trips.trip_id == trip_id, "route_id"].iloc[0]
        cleaned_by_trip[trip_id] = clean_trip_pings(g, geo[route_id])

    return dict(pings=pings, trips=trips, routes=routes, stops=stops,
                bookings=bookings, geo=geo, cleaned_by_trip=cleaned_by_trip)


if __name__ == "__main__":
    ctx = build_pipeline()
    print("Trips with accepted pings:", sum(1 for v in ctx["cleaned_by_trip"].values() if not v.empty),
          "/", len(ctx["trips"]))

    # sanity: how many pings did cleaning drop for V-02's trip (the phantom-stream case)?
    v02_trip = ctx["trips"][ctx["trips"].vehicle_id == "V-02"].iloc[0].trip_id
    raw_n = (ctx["pings"].trip_id == v02_trip).sum()
    clean_n = len(ctx["cleaned_by_trip"][v02_trip])
    print(f"\nV-02 / {v02_trip}: raw pings {raw_n} -> accepted {clean_n} (dropped {raw_n - clean_n})")

    print("\n=== example verdicts ===")
    examples = [
        (9, pd.Timestamp("2026-06-15 08:10:00+05:30")),
        (12, pd.Timestamp("2026-06-15 07:40:00+05:30")),
        (12, pd.Timestamp("2026-06-16 07:40:00+05:30")),
        (12, pd.Timestamp("2026-06-17 07:40:00+05:30")),
        (14, pd.Timestamp("2026-06-16 08:00:00+05:30")),   # V-04, broken recorded_at day
        (17, pd.Timestamp("2026-06-15 09:00:00+05:30")),   # operator 7 vehicle (V-11)
        (21, pd.Timestamp("2026-06-15 09:00:00+05:30")),   # operator 7 vehicle (V-12)
    ]
    for route_id, as_of in examples:
        v = lateness_for_route(route_id, as_of, ctx["trips"], ctx["routes"], ctx["geo"], ctx["cleaned_by_trip"])
        print(f"route {route_id} @ {as_of}: {v}")
