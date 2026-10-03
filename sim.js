// Schedule-based train positions. Shared by the page (window.Sim) and the tests (require).
(function (root) {
  "use strict";

  // Where a trip is at time t (seconds into the service day), or null if it isn't running.
  // calls are [stationName, arrival, departure, metresAlongShape]. Between stations the
  // train is assumed to move at a steady speed; at a station it waits until departure.
  function tripState(trip, t) {
    const c = trip.calls;
    if (t < c[0][1] || t > c[c.length - 1][2]) return null;
    for (let i = 0; i < c.length; i++) {
      const [name, arr, dep, d] = c[i];
      if (t > dep) continue;
      if (t >= arr) return { dist: d, at: name, next: c[i + 1] ? c[i + 1][0] : null };
      const p = c[i - 1];
      const f = (t - p[2]) / (arr - p[2]);
      return { dist: p[3] + f * (d - p[3]), at: null, next: name };
    }
    return null;
  }

  // [lat, lon] of the point d metres along a shape of [lat, lon, metres] points.
  function pointAt(shape, d) {
    let lo = 0, hi = shape.length - 1;
    if (d <= shape[lo][2]) return [shape[lo][0], shape[lo][1]];
    if (d >= shape[hi][2]) return [shape[hi][0], shape[hi][1]];
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (shape[mid][2] <= d) lo = mid; else hi = mid;
    }
    const a = shape[lo], b = shape[hi];
    const f = (d - a[2]) / (b[2] - a[2] || 1);
    return [a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])];
  }

  function trainsAt(schedule, t) {
    const out = [];
    for (const trip of schedule.trips) {
      const s = tripState(trip, t);
      if (!s) continue;
      const [lat, lon] = pointAt(schedule.shapes[trip.shape], s.dist);
      out.push({ trip, lat, lon, at: s.at, next: s.next });
    }
    return out;
  }

  // Average minutes between departures from each direction's first station within an hour of t.
  function headwayMinutes(schedule, t, dir) {
    const deps = schedule.trips
      .filter((trip) => trip.dir === dir)
      .map((trip) => trip.calls[0][2])
      .filter((d) => Math.abs(d - t) <= 3600)
      .sort((a, b) => a - b);
    if (deps.length < 2) return null;
    return (deps[deps.length - 1] - deps[0]) / (deps.length - 1) / 60;
  }

  function serviceSpan(schedules) {
    let first = Infinity, last = -Infinity;
    for (const s of schedules) {
      for (const trip of s.trips) {
        first = Math.min(first, trip.calls[0][1]);
        last = Math.max(last, trip.calls[trip.calls.length - 1][2]);
      }
    }
    return [first, last];
  }

  function formatTime(sec, withSeconds) {
    sec = Math.floor(sec);
    const day = ((sec % 86400) + 86400) % 86400;
    const h = Math.floor(day / 3600), m = Math.floor((day % 3600) / 60), s = day % 60;
    const pad = (n) => String(n).padStart(2, "0");
    const h12 = h % 12 === 0 ? 12 : h % 12;
    return `${h12}:${pad(m)}${withSeconds ? ":" + pad(s) : ""} ${h < 12 ? "AM" : "PM"}`;
  }

  const api = { tripState, pointAt, trainsAt, headwayMinutes, serviceSpan, formatTime };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Sim = api;
})(this);
