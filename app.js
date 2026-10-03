(function () {
  "use strict";

  const schedules = window.SCHEDULES || [];
  if (!schedules.length) {
    document.getElementById("missing").hidden = false;
    return;
  }

  const COLORS = ["#2563eb", "#ea580c", "#16a34a", "#9333ea"];
  const $ = (id) => document.getElementById(id);
  const svgNS = "http://www.w3.org/2000/svg";

  schedules.forEach((s, i) => {
    s.color = COLORS[i % COLORS.length];
    s.visible = true;
    // The first schedule is drawn hollow so the two are told apart by shape as well as colour.
    s.hollow = schedules.length > 1 && i === 0;
  });

  const [spanStart, spanEnd] = Sim.serviceSpan(schedules);
  let t = startTime();
  let playing = false;
  let lastFrame = null;

  // ---- Map ----------------------------------------------------------------
  const map = L.map("map", { zoomControl: true });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  const bounds = L.latLngBounds([]);
  const drawnShapes = new Set();
  for (const s of schedules) {
    for (const [id, shape] of Object.entries(s.shapes)) {
      const key = JSON.stringify([shape[0], shape[shape.length - 1], shape.length]);
      if (drawnShapes.has(key)) continue;
      drawnShapes.add(key);
      const line = shape.map((p) => [p[0], p[1]]);
      L.polyline(line, { color: "#7a7a74", weight: 4, opacity: 0.6 }).addTo(map);
      line.forEach((p) => bounds.extend(p));
    }
  }
  const stationNames = new Set();
  for (const s of schedules) {
    for (const st of s.stations) {
      if (stationNames.has(st.name)) continue;
      stationNames.add(st.name);
      L.circleMarker([st.lat, st.lon], { radius: 5, color: "#3a3a37", weight: 2, fillColor: "#fff", fillOpacity: 1 })
        .bindTooltip(st.name)
        .addTo(map);
    }
  }
  map.fitBounds(bounds, { padding: [20, 20] });

  const markers = new Map();

  function drawTrains() {
    const seen = new Set();
    for (const s of schedules) {
      if (!s.visible) continue;
      for (const train of Sim.trainsAt(s, t)) {
        const key = s.label + "|" + train.trip.id;
        seen.add(key);
        let m = markers.get(key);
        if (!m) {
          m = L.circleMarker([train.lat, train.lon], {
            radius: 8,
            color: s.color,
            weight: 3,
            fillColor: s.hollow ? "#ffffff" : s.color,
            fillOpacity: 1,
          }).bindTooltip("");
          m.addTo(map);
          markers.set(key, m);
        } else {
          m.setLatLng([train.lat, train.lon]);
        }
        const where = train.at ? `At ${train.at}` : `Next stop: ${train.next}`;
        m.setTooltipContent(`<strong>${escapeHtml(s.label)}</strong><br>To ${escapeHtml(train.trip.headsign)}<br>${escapeHtml(where)}`);
      }
    }
    for (const [key, m] of markers) {
      if (!seen.has(key)) {
        m.remove();
        markers.delete(key);
      }
    }
  }

  // ---- Schedule cards -----------------------------------------------------
  const cards = schedules.map((s) => {
    const label = document.createElement("label");
    label.className = "schedule";
    label.style.setProperty("--color", s.color);
    label.innerHTML = `
      <input type="checkbox" checked>
      <span>
        <strong></strong>
        <span class="meta"></span>
        <span class="stats"></span>
      </span>`;
    label.querySelector("strong").textContent = s.label + (s.hollow ? " (hollow dots)" : "");
    label.querySelector(".meta").textContent =
      `Service day ${s.date} · ${s.trips.length} trips` + (s.source ? ` · ${s.source}` : "");
    label.querySelector("input").addEventListener("change", (e) => {
      s.visible = e.target.checked;
      render();
    });
    $("schedules").appendChild(label);
    return label.querySelector(".stats");
  });

  function updateStats() {
    schedules.forEach((s, i) => {
      const running = Sim.trainsAt(s, t).length;
      const hw = [0, 1]
        .map((dir) => Sim.headwayMinutes(s, t, dir))
        .filter((h) => h !== null);
      const every = hw.length ? `about every ${Math.round(Math.max(...hw))} min` : "no trains this hour";
      cards[i].textContent = `${running} train${running === 1 ? "" : "s"} running · ${every}`;
    });
  }

  // ---- Time–distance (Marey) chart ------------------------------------------
  // All schedules share one vertical axis: distance along a reference trip, by station.
  const stationPos = referenceStationPositions();
  const lineLength = Math.max(...Object.values(stationPos));

  function referenceStationPositions() {
    const ref = schedules[0].trips.reduce((a, b) => (b.calls.length > a.calls.length ? b : a));
    const shape = schedules[0].shapes[ref.shape];
    const pos = {};
    const firstName = ref.calls[0][0];
    for (const s of schedules) {
      for (const st of s.stations) {
        let best = Infinity, dist = 0;
        for (const p of shape) {
          const d = (p[0] - st.lat) ** 2 + ((p[1] - st.lon) * Math.cos((st.lat * Math.PI) / 180)) ** 2;
          if (d < best) { best = d; dist = p[2]; }
        }
        pos[st.name] = dist;
      }
    }
    // Put Union Station (or whichever end the reference trip starts at, if it's not in the feed) at the top.
    const top = Object.keys(pos).find((n) => /union station/i.test(n)) || firstName;
    const total = Math.max(...Object.values(pos));
    if (pos[top] > total / 2) for (const n in pos) pos[n] = total - pos[n];
    return pos;
  }

  function drawChart() {
    const svg = $("marey");
    const W = svg.clientWidth, H = svg.clientHeight;
    const left = W < 500 ? 96 : 150, right = 8, top = 10, bottom = 24;
    const span = (W < 500 ? 1.5 : 3) * 3600; // seconds of timetable shown
    const t0 = t - span / 2, t1 = t + span / 2;
    const x = (time) => left + ((time - t0) / (t1 - t0)) * (W - left - right);
    const y = (d) => top + (d / lineLength) * (H - top - bottom);
    svg.textContent = "";
    const tickStep = W < 500 ? 3600 : 1800;

    const add = (tag, attrs, text) => {
      const el = document.createElementNS(svgNS, tag);
      for (const k in attrs) el.setAttribute(k, attrs[k]);
      if (text) el.textContent = text;
      svg.appendChild(el);
      return el;
    };

    for (const [name, d] of Object.entries(stationPos)) {
      add("line", { class: "grid", x1: left, x2: W - right, y1: y(d), y2: y(d) });
      add("text", { x: left - 6, y: y(d) + 4, "text-anchor": "end" }, shorten(name));
    }
    for (let h = Math.ceil(t0 / tickStep) * tickStep; h <= t1; h += tickStep) {
      add("line", { class: "grid", x1: x(h), x2: x(h), y1: top, y2: H - bottom });
      add("text", { x: x(h), y: H - 6, "text-anchor": "middle" }, Sim.formatTime(h));
    }

    // Trains are drawn inside a clipped plot area so they don't run over the station labels.
    const clip = add("clipPath", { id: "plot" });
    const rect = document.createElementNS(svgNS, "rect");
    Object.entries({ x: left, y: 0, width: W - left - right, height: H }).forEach(([k, v]) => rect.setAttribute(k, v));
    clip.appendChild(rect);
    const plot = add("g", { "clip-path": "url(#plot)" });

    for (const s of schedules) {
      if (!s.visible) continue;
      for (const trip of s.trips) {
        const c = trip.calls;
        if (c[c.length - 1][2] < t0 || c[0][1] > t1) continue;
        const pts = [];
        for (const [name, arr, dep] of c) {
          if (!(name in stationPos)) continue;
          pts.push(`${x(arr).toFixed(1)},${y(stationPos[name]).toFixed(1)}`);
          pts.push(`${x(dep).toFixed(1)},${y(stationPos[name]).toFixed(1)}`);
        }
        plot.appendChild(add("polyline", {
          points: pts.join(" "),
          fill: "none",
          stroke: s.color,
          "stroke-width": 1.75,
          "stroke-dasharray": s.hollow ? "5 3" : "",
        }));
      }
    }
    add("line", { class: "now", x1: x(t), x2: x(t), y1: top, y2: H - bottom });
  }

  function shorten(name) {
    // "40th Ave & Airport Blvd - Gateway Park Station" -> "Gateway Park"
    return name.split(/\s+[-–]\s+/).pop().replace(/\s+(Station|Track \w+)$/i, "").replace(/\s*\(.*\)$/, "");
  }

  // ---- Controls & loop ------------------------------------------------------
  const slider = $("time");
  slider.min = spanStart;
  slider.max = spanEnd;
  slider.addEventListener("input", () => {
    t = Number(slider.value);
    render();
  });
  $("play").addEventListener("click", () => {
    playing = !playing;
    $("play").textContent = playing ? "❚❚" : "▶";
    $("play").setAttribute("aria-label", playing ? "Pause" : "Play");
    lastFrame = null;
    if (playing) requestAnimationFrame(tick);
  });
  $("now").addEventListener("click", () => {
    t = startTime();
    render();
  });
  window.addEventListener("resize", drawChart);

  function startTime() {
    const now = new Date();
    const sec = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
    if (sec >= spanStart && sec <= spanEnd) return sec;
    if (sec + 86400 <= spanEnd) return sec + 86400; // after midnight, still the previous service day
    return 8 * 3600;
  }

  function tick(ts) {
    if (!playing) return;
    if (lastFrame !== null) {
      t += ((ts - lastFrame) / 1000) * Number($("speed").value);
      if (t > spanEnd) t = spanStart;
    }
    lastFrame = ts;
    render();
    requestAnimationFrame(tick);
  }

  let lastChartDraw = 0;
  function render() {
    slider.value = t;
    $("clock").textContent = Sim.formatTime(t, true);
    drawTrains();
    updateStats();
    const now = performance.now();
    if (!playing || now - lastChartDraw > 100) {
      drawChart();
      lastChartDraw = now;
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
  }

  render();
})();
