"""A tiny made-up GTFS feed shaped like the A Line, for tests only (not real schedule data)."""

import io
import zipfile

STATIONS = [
    ("union", "Union Station", 39.7535, -105.0002),
    ("blake", "38th & Blake Station", 39.7685, -104.9805),
    ("colorado", "40th & Colorado Station", 39.7764, -104.9420),
    ("centralpark", "Central Park Station", 39.7695, -104.8869),
    ("peoria", "Peoria Station", 39.7702, -104.8466),
    ("gateway", "40th Ave & Airport Blvd - Gateway Park Station", 39.7697, -104.7859),
    ("pena", "61st & Pena Station", 39.8073, -104.7848),
    ("airport", "Denver Airport Station", 39.8474, -104.6737),
]
# Minutes from the first station.
RUN_MINUTES = [0, 4, 8, 13, 17, 23, 28, 37]


def hms(sec):
    return "%02d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


def make_feed(path, headway_min, first="04:00", last="25:00", start="20260101", end="20261231"):
    h, m = (int(p) for p in first.split(":"))
    lh, lm = (int(p) for p in last.split(":"))
    files = {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nRTD,Test,https://example.com,America/Denver\n",
        "routes.txt": "route_id,agency_id,route_short_name,route_long_name,route_type,route_color\n"
                      "A,RTD,A,Union Station to Denver Airport,2,57C1E9\n"
                      "W,RTD,W,Some other line,2,000000\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                        f"WK,1,1,1,1,1,0,0,{start},{end}\nWE,0,0,0,0,0,1,1,{start},{end}\n",
    }
    stops = ["stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station"]
    for sid, name, lat, lon in STATIONS:
        stops.append(f"{sid},{name},{lat},{lon},1,")
        # Separate platforms per direction, as real feeds often have.
        stops.append(f"{sid}-1,{name} Track 1,{lat + 0.0001},{lon},0,{sid}")
        stops.append(f"{sid}-2,{name} Track 2,{lat - 0.0001},{lon},0,{sid}")
    files["stops.txt"] = "\n".join(stops) + "\n"

    shapes = ["shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence"]
    for i, (_, _, lat, lon) in enumerate(STATIONS):
        shapes.append(f"out,{lat},{lon},{i}")
        shapes.append(f"back,{lat},{lon},{len(STATIONS) - i}")
    files["shapes.txt"] = "\n".join(shapes) + "\n"

    trips = ["route_id,service_id,trip_id,trip_headsign,direction_id,shape_id"]
    stop_times = ["trip_id,arrival_time,departure_time,stop_id,stop_sequence"]
    n = 0
    for service in ("WK", "WE"):
        t = h * 3600 + m * 60
        while t <= lh * 3600 + lm * 60:
            for direction in (0, 1):
                n += 1
                trip_id = f"{service}-{n}"
                order = list(range(len(STATIONS))) if direction == 0 else list(reversed(range(len(STATIONS))))
                head = STATIONS[order[-1]][1]
                trips.append(f"A,{service},{trip_id},{head},{direction},{'out' if direction == 0 else 'back'}")
                for seq, idx in enumerate(order):
                    offset = RUN_MINUTES[idx] if direction == 0 else RUN_MINUTES[-1] - RUN_MINUTES[idx]
                    arr = t + offset * 60
                    dep = arr + (0 if seq in (0, len(order) - 1) else 30)
                    stop_times.append(f"{trip_id},{hms(arr)},{hms(dep)},{STATIONS[idx][0]}-{direction + 1},{seq + 1}")
            t += headway_min * 60
    trips.append("W,WK,other-1,Elsewhere,0,")
    stop_times.append("other-1,08:00:00,08:00:00,union-1,1")
    stop_times.append("other-1,08:10:00,08:10:00,blake-1,2")
    files["trips.txt"] = "\n".join(trips) + "\n"
    files["stop_times.txt"] = "\n".join(stop_times) + "\n"

    with zipfile.ZipFile(path, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
