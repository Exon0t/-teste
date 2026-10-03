# A Line Simulator

Shows where RTD's A Line trains (Union Station ⇄ Denver Airport) should be at any time of day,
estimated from the published timetable, and compares two timetables (for example the schedule
before and after the 2026 change) on the same map.

- **Map**: one dot per train. The first schedule is drawn as hollow dots, the second as solid dots.
- **Time slider and playback**: scrub through the service day or play it at up to 5 minutes per second.
- **Per-schedule stats**: how many trains are running and roughly how often they come.
- **Time–distance chart**: one line per train (time across, distance down), which makes changes in
  frequency and running time easy to compare.

Positions are an estimate: each train is assumed to wait at a station from its scheduled arrival to
its scheduled departure and to move at a steady speed in between. It is not live tracking.

## Building the schedule data

The page reads `data/schedules.js`, which `tools/build_data.py` makes from GTFS feeds (the timetable
files transit agencies publish). Give it one `--feed` per schedule as `LABEL=SOURCE[@YYYYMMDD]`,
where SOURCE is a path or URL to a GTFS zip and the optional date picks which service day to show
(by default the first Wednesday the A Line runs in that feed):

```sh
python3 tools/build_data.py \
  --feed "Old schedule=feeds/rtd-old.zip@20260107" \
  --feed "New schedule=https://www.rtd-denver.com/files/gtfs/google_transit.zip"
```

- **New schedule**: RTD's current feed, <https://www.rtd-denver.com/files/gtfs/google_transit.zip>.
- **Old schedule**: RTD replaces that file when a new schedule starts, so the old timetable has to
  come from an archived copy, such as the historical RTD feeds kept by the
  [Mobility Database](https://mobilitydatabase.org/), or a copy saved before the change.

`--route` picks a different line (route id, short name or long name), e.g. `--route W`.

Only Python 3 is needed; there are no dependencies.

## Viewing

Open `index.html` in a browser, or serve the folder (`python3 -m http.server`) and go to
<http://localhost:8000>. The map uses Leaflet and OpenStreetMap tiles, so it needs an internet
connection.

## Tests

```sh
python3 -m unittest discover -s tests
node --test tests/sim.test.js
```

The tests use a small made-up feed (`tests/fixture.py`), not real RTD data.
