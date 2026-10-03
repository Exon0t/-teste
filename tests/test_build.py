import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import build_data  # noqa: E402
from fixture import make_feed  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


class BuildDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.feed = os.path.join(self.tmp.name, "feed.zip")
        make_feed(self.feed, headway_min=15)

    def tearDown(self):
        self.tmp.cleanup()

    def test_picks_a_wednesday_and_only_a_line_trips(self):
        data = build_data.build("Test", self.feed, None, "A")
        self.assertEqual(dt.date.fromisoformat(data["date"]).weekday(), 2)
        self.assertTrue(all(t["id"].startswith("WK-") for t in data["trips"]))
        # 04:00 to 25:00 every 15 minutes, both directions.
        self.assertEqual(len(data["trips"]), 2 * (21 * 4 + 1))

    def test_weekend_date_uses_weekend_service(self):
        data = build_data.build("Test", self.feed, dt.date(2026, 3, 7), "A")
        self.assertTrue(all(t["id"].startswith("WE-") for t in data["trips"]))

    def test_calls_use_parent_station_names_and_increasing_distances(self):
        data = build_data.build("Test", self.feed, None, "A")
        for trip in data["trips"]:
            names = [c[0] for c in trip["calls"]]
            self.assertNotIn("Track", " ".join(names))
            dists = [c[3] for c in trip["calls"]]
            self.assertEqual(dists, sorted(dists))
        outbound = next(t for t in data["trips"] if t["dir"] == 0)
        self.assertEqual(outbound["calls"][0][0], "Union Station")
        self.assertEqual(outbound["headsign"], "Denver Airport Station")
        # Union Station to the airport is roughly 37 km along these straight segments.
        self.assertAlmostEqual(outbound["calls"][-1][3] / 1000, 37, delta=6)
        self.assertEqual(len(data["stations"]), 8)

    def test_after_midnight_times_are_kept_past_24h(self):
        data = build_data.build("Test", self.feed, None, "A")
        self.assertEqual(max(t["calls"][-1][2] for t in data["trips"]), 25 * 3600 + 37 * 60)

    def test_cli_writes_schedules_js(self):
        out = os.path.join(self.tmp.name, "schedules.js")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_data.py"),
                        "--feed", f"Old={self.feed}@20260304", "--feed", f"New={self.feed}",
                        "--out", out], check=True, capture_output=True)
        with open(out) as f:
            text = f.read()
        payload = json.loads(text[text.index("=") + 1:].strip().rstrip(";"))
        self.assertEqual([s["label"] for s in payload], ["Old", "New"])
        self.assertEqual(payload[0]["date"], "2026-03-04")


if __name__ == "__main__":
    unittest.main()
