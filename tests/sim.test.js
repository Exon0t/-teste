const test = require("node:test");
const assert = require("node:assert");
const Sim = require("../sim.js");

const shape = [
  [39.0, -105.0, 0],
  [39.0, -104.0, 1000],
  [40.0, -104.0, 2000],
];
const trip = {
  id: "t1",
  dir: 0,
  headsign: "C",
  shape: "s",
  calls: [
    ["A", 100, 100, 0],
    ["B", 200, 260, 1000],
    ["C", 360, 360, 2000],
  ],
};
const schedule = { label: "x", shapes: { s: shape }, trips: [trip] };

test("not running before the first departure or after the last arrival", () => {
  assert.strictEqual(Sim.tripState(trip, 99), null);
  assert.strictEqual(Sim.tripState(trip, 361), null);
});

test("moves steadily between stations", () => {
  const s = Sim.tripState(trip, 150);
  assert.strictEqual(s.dist, 500);
  assert.strictEqual(s.at, null);
  assert.strictEqual(s.next, "B");
  assert.strictEqual(Sim.tripState(trip, 310).dist, 1500);
});

test("waits at a station between arrival and departure", () => {
  for (const t of [200, 230, 260]) {
    const s = Sim.tripState(trip, t);
    assert.strictEqual(s.dist, 1000);
    assert.strictEqual(s.at, "B");
    assert.strictEqual(s.next, "C");
  }
});

test("pointAt interpolates along the shape and clamps at its ends", () => {
  assert.deepStrictEqual(Sim.pointAt(shape, 500), [39.0, -104.5]);
  assert.deepStrictEqual(Sim.pointAt(shape, 1500), [39.5, -104.0]);
  assert.deepStrictEqual(Sim.pointAt(shape, -5), [39.0, -105.0]);
  assert.deepStrictEqual(Sim.pointAt(shape, 9999), [40.0, -104.0]);
});

test("trainsAt places running trains on the map", () => {
  const trains = Sim.trainsAt(schedule, 150);
  assert.strictEqual(trains.length, 1);
  assert.deepStrictEqual([trains[0].lat, trains[0].lon], [39.0, -104.5]);
  assert.strictEqual(Sim.trainsAt(schedule, 50).length, 0);
});

test("headway averages departures within an hour", () => {
  const trips = [0, 900, 1800, 2700].map((d, i) => ({ dir: 0, calls: [["A", 3600 + d, 3600 + d, 0]], id: String(i) }));
  assert.strictEqual(Sim.headwayMinutes({ trips }, 4500, 0), 15);
  assert.strictEqual(Sim.headwayMinutes({ trips }, 4500, 1), null);
});

test("formatTime wraps service-day times past midnight", () => {
  assert.strictEqual(Sim.formatTime(8 * 3600 + 5 * 60), "8:05 AM");
  assert.strictEqual(Sim.formatTime(13 * 3600 + 7, true), "1:00:07 PM");
  assert.strictEqual(Sim.formatTime(24 * 3600 + 30 * 60), "12:30 AM");
});
