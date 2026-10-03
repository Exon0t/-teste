#!/usr/bin/env python3
"""Build the simulator's schedule data from GTFS feeds.

Reads one or more GTFS zips (local paths or URLs), keeps only the trips of one
route (RTD's A Line by default) that run on a chosen service date, and writes
them to data/schedules.js, which index.html loads.

Example:
    python3 tools/build_data.py \
        --feed "Old schedule=feeds/rtd-2025.zip@20251015" \
        --feed "New schedule=https://www.rtd-denver.com/files/gtfs/google_transit.zip"

Each --feed is LABEL=SOURCE[@YYYYMMDD]. Without a date, the first Wednesday on
which the route runs in that feed is used (a typical weekday).
"""

import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import sys
import tempfile
import urllib.request
import zipfile

EARTH_RADIUS_M = 6371000.0


def open_feed(source):
    if source.startswith(("http://", "https://")):
        print(f"Downloading {source} ...", file=sys.stderr)
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        with urllib.request.urlopen(source) as resp:
            tmp.write(resp.read())
        tmp.close()
        source = tmp.name
    return zipfile.ZipFile(source)


def rows(zf, name):
    """Yield dict rows of a GTFS table, or nothing if the table is absent."""
    if name not in zf.namelist():
        return
    with zf.open(name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        for row in csv.DictReader(text):
            yield {k.strip(): (v or "").strip() for k, v in row.items() if k}


def parse_time(value):
    """GTFS HH:MM:SS (hours may exceed 23 for after-midnight trips) -> seconds."""
    h, m, s = (int(p) for p in value.split(":"))
    return h * 3600 + m * 60 + s


def find_route_ids(zf, route):
    wanted = route.lower()
    found = {}
    for r in rows(zf, "routes.txt"):
        names = {r.get("route_id", ""), r.get("route_short_name", ""), r.get("route_long_name", "")}
        if wanted in {n.lower() for n in names}:
            found[r["route_id"]] = r
    if not found:
        sys.exit(f"No route matching {route!r} in routes.txt")
    return found


def active_services(zf, service_ids, date):
    day = date.strftime("%Y%m%d")
    weekday = date.strftime("%A").lower()
    active = set()
    for c in rows(zf, "calendar.txt"):
        if c["service_id"] in service_ids and c["start_date"] <= day <= c["end_date"] and c.get(weekday) == "1":
            active.add(c["service_id"])
    for c in rows(zf, "calendar_dates.txt"):
        if c["service_id"] in service_ids and c["date"] == day:
            if c["exception_type"] == "1":
                active.add(c["service_id"])
            elif c["exception_type"] == "2":
                active.discard(c["service_id"])
    return active


def service_date_range(zf, service_ids):
    days = []
    for c in rows(zf, "calendar.txt"):
        if c["service_id"] in service_ids:
            days += [c["start_date"], c["end_date"]]
    for c in rows(zf, "calendar_dates.txt"):
        if c["service_id"] in service_ids and c["exception_type"] == "1":
            days.append(c["date"])
    if not days:
        sys.exit("The route has no service dates in this feed")
    to_date = lambda s: dt.datetime.strptime(s, "%Y%m%d").date()
    return to_date(min(days)), to_date(max(days))


def pick_date(zf, service_ids):
    start, end = service_date_range(zf, service_ids)
    day = start
    while day <= end:
        if day.weekday() == 2 and active_services(zf, service_ids, day):
            return day
        day += dt.timedelta(days=1)
    day = start
    while day <= end:
        if active_services(zf, service_ids, day):
            return day
        day += dt.timedelta(days=1)
    sys.exit("The route never runs in this feed")


def to_xy(lat, lon, lat0):
    """Local equirectangular projection in metres; fine over a single line."""
    x = math.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = math.radians(lat) * EARTH_RADIUS_M
    return x, y


def with_distances(points):
    """[(lat, lon)] -> [[lat, lon, metres along line]]."""
    lat0 = points[0][0]
    out, total, prev = [], 0.0, None
    for lat, lon in points:
        xy = to_xy(lat, lon, lat0)
        if prev:
            total += math.dist(prev, xy)
        out.append([round(lat, 6), round(lon, 6), round(total, 1)])
        prev = xy
    return out


def project(shape, lat, lon, start_seg):
    """Distance along shape of the point nearest (lat, lon), searching from start_seg on."""
    lat0 = shape[0][0]
    p = to_xy(lat, lon, lat0)
    best = (float("inf"), shape[start_seg][2], start_seg)
    for i in range(start_seg, len(shape) - 1):
        a, b = to_xy(shape[i][0], shape[i][1], lat0), to_xy(shape[i + 1][0], shape[i + 1][1], lat0)
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg2 = dx * dx + dy * dy
        f = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / seg2))
        d = math.dist(p, (a[0] + f * dx, a[1] + f * dy))
        if d < best[0]:
            best = (d, shape[i][2] + f * (shape[i + 1][2] - shape[i][2]), i)
    return best[1], best[2]


def build(label, source, date, route):
    zf = open_feed(source)
    routes = find_route_ids(zf, route)
    trips = {t["trip_id"]: t for t in rows(zf, "trips.txt") if t["route_id"] in routes}
    service_ids = {t["service_id"] for t in trips.values()}
    date = date or pick_date(zf, service_ids)
    active = active_services(zf, service_ids, date)
    trips = {k: t for k, t in trips.items() if t["service_id"] in active}
    if not trips:
        sys.exit(f"{label}: no {route} trips run on {date}")

    stop_times = {}
    for st in rows(zf, "stop_times.txt"):
        if st["trip_id"] in trips and (st.get("arrival_time") or st.get("departure_time")):
            arr = st.get("arrival_time") or st["departure_time"]
            dep = st.get("departure_time") or arr
            stop_times.setdefault(st["trip_id"], []).append(
                (int(st["stop_sequence"]), st["stop_id"], parse_time(arr), parse_time(dep)))

    stops = {s["stop_id"]: s for s in rows(zf, "stops.txt")}

    def station_of(stop_id):
        s = stops[stop_id]
        parent = s.get("parent_station")
        return stops[parent] if parent in stops else s

    shape_ids = {t.get("shape_id") for t in trips.values()} - {"", None}
    raw_shapes = {}
    for p in rows(zf, "shapes.txt"):
        if p["shape_id"] in shape_ids:
            raw_shapes.setdefault(p["shape_id"], []).append(
                (int(p["shape_pt_sequence"]), float(p["shape_pt_lat"]), float(p["shape_pt_lon"])))
    shapes = {sid: with_distances([(lat, lon) for _, lat, lon in sorted(pts)])
              for sid, pts in raw_shapes.items()}

    out_trips, stations = [], {}
    for trip_id, t in trips.items():
        times = sorted(stop_times.get(trip_id, []))
        if len(times) < 2:
            continue
        shape_id = t.get("shape_id")
        if shape_id not in shapes:
            # No geometry in the feed: draw straight lines between the stops.
            shape_id = "stops:" + trip_id
            shapes[shape_id] = with_distances(
                [(float(stops[s].get("stop_lat")), float(stops[s].get("stop_lon"))) for _, s, _, _ in times])
        shape, seg, calls = shapes[shape_id], 0, []
        for _, stop_id, arr, dep in times:
            s = stops[stop_id]
            dist, seg = project(shape, float(s["stop_lat"]), float(s["stop_lon"]), seg)
            station = station_of(stop_id)
            stations[station["stop_name"]] = [round(float(station["stop_lat"]), 6), round(float(station["stop_lon"]), 6)]
            calls.append([station["stop_name"], arr, dep, round(dist, 1)])
        out_trips.append({
            "id": trip_id,
            "dir": int(t.get("direction_id") or 0),
            "headsign": t.get("trip_headsign") or calls[-1][0],
            "shape": shape_id,
            "calls": calls,
        })
    out_trips.sort(key=lambda t: t["calls"][0][1])

    used = {t["shape"] for t in out_trips}
    route_row = next(iter(routes.values()))
    print(f"{label}: {len(out_trips)} trips on {date} from {source}", file=sys.stderr)
    return {
        "label": label,
        "source": os.path.basename(source),
        "date": date.isoformat(),
        "route": {
            "name": route_row.get("route_long_name") or route_row.get("route_short_name"),
            "color": "#" + route_row["route_color"] if route_row.get("route_color") else None,
        },
        "shapes": {k: v for k, v in shapes.items() if k in used},
        "stations": [{"name": n, "lat": ll[0], "lon": ll[1]} for n, ll in stations.items()],
        "trips": out_trips,
    }


def parse_feed_arg(value):
    label, sep, rest = value.partition("=")
    if not sep:
        raise argparse.ArgumentTypeError("expected LABEL=SOURCE[@YYYYMMDD]")
    source, date = rest, None
    head, at, tail = rest.rpartition("@")
    if at and len(tail) == 8 and tail.isdigit():
        source, date = head, dt.datetime.strptime(tail, "%Y%m%d").date()
    return label, source, date


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--feed", action="append", required=True, type=parse_feed_arg,
                        help="LABEL=SOURCE[@YYYYMMDD]; repeat for each schedule to compare")
    parser.add_argument("--route", default="A", help="route_id, short name or long name (default: A)")
    parser.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "data", "schedules.js"))
    args = parser.parse_args()

    schedules = [build(label, source, date, args.route) for label, source, date in args.feed]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        f.write("// Generated by tools/build_data.py. Do not edit by hand.\n")
        f.write("window.SCHEDULES = ")
        json.dump(schedules, f, separators=(",", ":"))
        f.write(";\n")
    print(f"Wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
