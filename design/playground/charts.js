/* Chart primitives for the design playground. Each chart is drawn as SVG at the
   container's real pixel size, so text stays legible on desktop and phone widths.
   Colours come from the active concept's CSS variables. */
(function () {
  'use strict';
  const M = window.MOCK;
  const registry = {};
  const pending = new Map();
  let nextId = 1;

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const pct = (v, d = 0) => v == null ? '—' : (v * 100).toFixed(d) + '%';
  const scale = (d0, d1, r0, r1) => (v) => r0 + (v - d0) / (d1 - d0 || 1) * (r1 - r0);
  const team = (code) => M.byCode[code];
  const dash = (code) => team(code).second ? ' stroke-dasharray="5 3"' : '';
  function svg(w, h, body, label) {
    return '<svg class="svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="' + esc(label) + '">' + body + '</svg>';
  }
  function text(x, y, s, cls, anchor) {
    return '<text x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" class="' + (cls || 't') + '"' + (anchor ? ' text-anchor="' + anchor + '"' : '') + '>' + esc(s) + '</text>';
  }

  // Concepts call C.chart(name, opts) in their templates, then C.mount(root).
  function chart(name, opts) {
    const id = nextId++;
    pending.set(id, { name, opts: opts || {} });
    const h = (opts && opts.h) ? 'height:' + opts.h + 'px;' : '';
    return '<div class="chart chart-' + name + '" data-cid="' + id + '" style="' + h + '"></div>';
  }
  function mount(root) {
    (root || document).querySelectorAll('.chart[data-cid]').forEach((el) => draw(el));
  }
  function draw(el) {
    const item = pending.get(Number(el.dataset.cid));
    if (!item) return;
    const w = Math.max(120, Math.floor(el.clientWidth));
    const h = item.opts.h || Math.max(120, Math.floor(el.clientHeight));
    el.innerHTML = registry[item.name](w, h, item.opts, el);
  }
  function redraw(name) {
    document.querySelectorAll('.chart-' + name + '[data-cid]').forEach((el) => draw(el));
  }
  function update(el, patch) {
    const item = pending.get(Number(el.dataset.cid));
    if (!item) return;
    Object.assign(item.opts, patch);
    draw(el);
  }

  // ---------- finish range: P10–P90 whisker, P25–P75 bar, median dot ----------
  registry.range = function (w, h, o) {
    const rows = o.rows, padL = o.padL || 46, padR = 54, top = 18, rowH = (h - top - 18) / rows.length;
    const x = scale(1, 22, padL, w - padR);
    let b = '';
    [1, 5, 10, 15, 20].forEach((p) => { b += '<line x1="' + x(p) + '" x2="' + x(p) + '" y1="' + top + '" y2="' + (h - 16) + '" class="grid"/>' + text(x(p), h - 3, 'P' + p, 'tm', 'middle'); });
    rows.forEach((s, i) => {
      const y = top + rowH * i + rowH / 2, d = team(s.code);
      b += '<g data-driver="' + s.code + '">' + text(6, y + 4, s.code, 'tl');
      b += '<line x1="' + x(s.p10) + '" x2="' + x(s.p90) + '" y1="' + y + '" y2="' + y + '" class="whisker"/>';
      b += '<rect x="' + x(s.p25) + '" y="' + (y - Math.min(5, rowH / 3)) + '" width="' + Math.max(3, x(s.p75) - x(s.p25)) + '" height="' + Math.min(10, rowH / 1.5) + '" rx="3" style="fill:' + (o.teamColour ? d.colour : 'var(--c-accent2)') + ';opacity:.85"/>';
      b += '<circle cx="' + x(s.p50) + '" cy="' + y + '" r="4" class="median"/>';
      b += text(w - padR + 8, y + 4, 'P' + Math.round(s.p25) + '–' + Math.round(s.p75), 'tm') + '</g>';
    });
    return svg(w, h, b, 'Finish range per driver: P10 to P90 line, middle half bar, median dot');
  };

  // ---------- quantile dot plot: 50 dots, each 2% of simulated races ----------
  registry.dots = function (w, h, o) {
    const code = o.code, sims = o.sim || M.base, arr = Array.from(sims.finish[team(code).idx]);
    const per = Math.max(1, Math.floor(arr.length / 50));
    const sorted = arr.slice().sort((a, b) => (a || 99) - (b || 99));
    const picks = [];
    for (let i = 0; i < 50; i++) picks.push(sorted[Math.min(sorted.length - 1, Math.floor((i + 0.5) * per))]);
    const cols = 23, x = scale(0.5, cols + 0.5, 30, w - 10), stack = {}, tally = {};
    picks.forEach((p) => { tally[p || 23] = (tally[p || 23] || 0) + 1; });
    const r = Math.min(7, (w - 40) / cols / 2.4, (h - 26) / (Math.max(...Object.values(tally)) * 2.2));
    let b = '';
    picks.forEach((p) => {
      const key = p || 23; stack[key] = (stack[key] || 0) + 1;
      const cy = h - 22 - (stack[key] - 0.5) * r * 2.2;
      b += '<circle cx="' + x(key) + '" cy="' + cy + '" r="' + r + '" style="fill:' + (p ? (o.colour || team(code).colour) : 'var(--c-neg)') + '"/>';
    });
    [1, 3, 5, 10, 15, 20].forEach((p) => { b += text(x(p), h - 4, 'P' + p, 'tm', 'middle'); });
    b += text(x(23), h - 4, 'DNF', 'tm', 'middle');
    return svg(w, h, b, '50 dots for ' + code + ', each one 2% of simulated races');
  };

  // ---------- position heatmap (HTML so it stays readable to screen readers) ----------
  registry.heat = function (w, h, o) {
    const rows = o.rows, upto = o.upto || 10;
    let t = '<table class="heat"><caption class="sr">Finish probability by position</caption><thead><tr><th scope="col">Driver</th>';
    for (let p = 1; p <= upto; p++) t += '<th scope="col">P' + p + '</th>';
    t += '</tr></thead><tbody>';
    rows.forEach((s) => {
      t += '<tr data-driver="' + s.code + '"><th scope="row">' + s.code + '</th>';
      for (let p = 0; p < upto; p++) {
        const v = s.matrix[p];
        t += '<td style="--a:' + Math.min(1, v * 2.4).toFixed(3) + '"><span>' + (v < 0.005 ? '·' : Math.round(v * 100)) + '</span></td>';
      }
      t += '</tr>';
    });
    return t + '</tbody></table>';
  };

  // ---------- race position progression (bump chart) ----------
  registry.bump = function (w, h, o) {
    const race = M.race, upto = Math.floor(o.lap || race.laps), showN = o.showN || 22;
    const padL = 34, padR = 44, top = 10, bottom = 20;
    const x = scale(1, race.laps, padL, w - padR), y = scale(1, showN, top, h - bottom);
    let b = '';
    race.scLaps.length && (b += '<rect x="' + x(race.scLaps[0] - 0.5) + '" y="' + top + '" width="' + (x(race.scLaps[race.scLaps.length - 1] + 0.5) - x(race.scLaps[0] - 0.5)) + '" height="' + (h - top - bottom) + '" class="band-sc"/>' + text(x(race.scLaps[0]), top + 10, 'SC', 'tm'));
    [1, 10, 20, 30, 40, 50, race.laps].forEach((l) => { b += text(x(l), h - 4, 'L' + l, 'tm', 'middle'); });
    const order = race.positions[Math.max(0, upto - 1)];
    const focus = o.focus || [];
    M.drivers.forEach((d) => {
      let path = '', started = false;
      for (let l = 1; l <= upto; l++) {
        const p = race.positions[l - 1][d.code];
        if (p == null || p > showN) { started = false; continue; }
        path += (started ? 'L' : 'M') + x(l).toFixed(1) + ' ' + y(p).toFixed(1);
        started = true;
      }
      const dim = focus.length && !focus.includes(d.code);
      b += '<path d="' + path + '" data-driver="' + d.code + '" class="bump-line' + (dim ? ' dim' : '') + '" style="stroke:' + d.colour + '"' + dash(d.code) + '/>';
      const p = order[d.code];
      if (p && p <= showN) b += '<g data-driver="' + d.code + '">' + text(Math.min(x(upto) + 6, w - padR + 6), y(p) + 4, d.code, dim ? 'tm' : 'tl') + '</g>';
    });
    for (let p = 1; p <= showN; p += showN > 12 ? 3 : 1) b += text(4, y(p) + 4, 'P' + p, 'tm');
    (o.pins ? race.events.filter((e) => ['sc', 'dnf', 'fastest', 'start'].includes(e.kind) && e.lap <= upto) : []).forEach((e, i) => {
      const px = x(Math.max(1, e.lap));
      b += '<g class="pin pin-' + e.kind + '"><line x1="' + px + '" x2="' + px + '" y1="' + top + '" y2="' + (h - bottom) + '" class="pin-line"/><circle cx="' + px + '" cy="' + (top + 2) + '" r="9" class="pin-dot"/><text x="' + px + '" y="' + (top + 6) + '" text-anchor="middle" class="pin-n">' + (i + 1) + '</text><title>' + esc('Lap ' + e.lap + ': ' + e.text) + '</title></g>';
    });
    if (o.cursor) b += '<line x1="' + x(Math.max(1, o.lap)) + '" x2="' + x(Math.max(1, o.lap)) + '" y1="' + top + '" y2="' + (h - bottom) + '" class="cursor"/>';
    return svg(w, h, b, 'Running position by lap for every driver');
  };

  // ---------- tyre strategy timeline ----------
  registry.tyres = function (w, h, o) {
    const race = M.race, rows = o.order || race.startOrder, padL = 40, top = 6, bottom = 18;
    const x = scale(0, race.laps, padL, w - 8), rowH = (h - top - bottom) / rows.length;
    let b = '<rect x="' + x(race.scLaps[0] - 1) + '" y="' + top + '" width="' + (x(race.scLaps[race.scLaps.length - 1]) - x(race.scLaps[0] - 1)) + '" height="' + (h - top - bottom) + '" class="band-sc"/>';
    rows.forEach((code, i) => {
      const r = race.rows.find((q) => q.code === code), y = top + i * rowH;
      b += '<g data-driver="' + code + '">' + text(4, y + rowH * 0.72, code, 'tl');
      r.plan.forEach((s) => {
        const end = r.retiredLap ? Math.min(s.to, r.retiredLap - 1) : s.to;
        if (end < s.from) return;
        b += '<rect x="' + (x(s.from - 1) + 1) + '" y="' + (y + rowH * 0.18) + '" width="' + Math.max(1, x(end) - x(s.from - 1) - 2) + '" height="' + (rowH * 0.64) + '" rx="' + Math.min(4, rowH * 0.3) + '" class="tyre tyre-' + s.compound + '"><title>' + code + ' ' + s.compound + ' laps ' + s.from + '–' + end + '</title></rect>';
        if (rowH > 13 && x(end) - x(s.from - 1) > 22) b += text(x(s.from - 1) + 5, y + rowH * 0.66, s.compound, 'tyre-label');
      });
      if (r.retiredLap) b += text(x(r.retiredLap) + 4, y + rowH * 0.72, 'DNF L' + r.retiredLap, 'tneg');
      b += '</g>';
    });
    [1, 10, 20, 30, 40, 50].forEach((l) => { b += text(x(l), h - 4, 'L' + l, 'tm', 'middle'); });
    if (o.lap) b += '<line x1="' + x(o.lap) + '" x2="' + x(o.lap) + '" y1="' + top + '" y2="' + (h - bottom) + '" class="cursor"/>';
    return svg(w, h, b, 'Tyre stints by driver. S soft, M medium, H hard. Shaded band is the safety car.');
  };

  // ---------- generic scatter (fantasy risk/reward) ----------
  registry.scatter = function (w, h, o) {
    const pts = o.points, padL = 44, padB = 30, top = 12, right = 14;
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    const x = scale(Math.min(...xs) * 0.9, Math.max(...xs) * 1.05, padL, w - right);
    const y = scale(Math.min(0, ...ys), Math.max(...ys) * 1.1, h - padB, top);
    let b = '<line x1="' + padL + '" x2="' + (w - right) + '" y1="' + (h - padB) + '" y2="' + (h - padB) + '" class="axis"/>';
    b += text(w - right, h - 6, o.xLabel, 'tm', 'end') + text(4, top + 4, o.yLabel, 'tm');
    if (o.frontier) {
      const f = pts.slice().sort((a, b) => a.x - b.x);
      let best = -Infinity, path = '';
      f.forEach((p) => { if (p.y > best) { best = p.y; path += (path ? 'L' : 'M') + x(p.x).toFixed(1) + ' ' + y(p.y).toFixed(1); } });
      b += '<path d="' + path + '" class="frontier"/>';
    }
    pts.forEach((p) => {
      const r = o.sizeKey ? 3 + Math.sqrt(p.size) * 1.1 : 5;
      b += '<g data-driver="' + p.label + '"><circle cx="' + x(p.x) + '" cy="' + y(p.y) + '" r="' + r + '" style="fill:' + (p.colour || 'var(--c-accent)') + ';fill-opacity:.8" class="dot"><title>' + esc(p.title || p.label) + '</title></circle>';
      if (p.y > (o.labelAbove || 0)) b += text(x(p.x) + r + 3, y(p.y) + 4, p.label, 'tl');
      b += '</g>';
    });
    return svg(w, h, b, o.aria || 'Scatter chart');
  };

  // ---------- line chart (telemetry, lap times, RPS) ----------
  registry.lines = function (w, h, o) {
    const padL = o.padL || 40, padB = o.hideX ? 6 : 22, top = 10, right = 10;
    const all = o.series.flatMap((s) => s.values.filter((v) => v.y != null));
    const xMin = o.xMin != null ? o.xMin : Math.min(...all.map((v) => v.x)), xMax = o.xMax != null ? o.xMax : Math.max(...all.map((v) => v.x));
    let yMin = o.yMin != null ? o.yMin : Math.min(...all.map((v) => v.y)), yMax = o.yMax != null ? o.yMax : Math.max(...all.map((v) => v.y));
    if (o.symmetric) { const m = Math.max(Math.abs(yMin), Math.abs(yMax)); yMin = -m; yMax = m; }
    const x = scale(xMin, xMax, padL, w - right), y = scale(yMin, yMax, h - padB, top);
    let b = '';
    (o.yTicks || [yMin, (yMin + yMax) / 2, yMax]).forEach((t) => { b += '<line x1="' + padL + '" x2="' + (w - right) + '" y1="' + y(t) + '" y2="' + y(t) + '" class="grid"/>' + text(padL - 6, y(t) + 4, o.yFmt ? o.yFmt(t) : t.toFixed(0), 'tm', 'end'); });
    if (!o.hideX) (o.xTicks || []).forEach((t) => { b += text(x(t), h - 5, o.xFmt ? o.xFmt(t) : String(t), 'tm', 'middle'); });
    (o.bands || []).forEach((band) => { b += '<rect x="' + x(band[0]) + '" y="' + top + '" width="' + (x(band[1]) - x(band[0])) + '" height="' + (h - padB - top) + '" class="band-sc"/>'; });
    if (o.area) { const s = o.series[0]; b += '<path d="M' + x(s.values[0].x) + ' ' + y(0) + s.values.map((v) => 'L' + x(v.x).toFixed(1) + ' ' + y(v.y).toFixed(1)).join('') + 'L' + x(s.values[s.values.length - 1].x) + ' ' + y(0) + 'Z" class="area"/>'; }
    o.series.forEach((s) => {
      let d = '', on = false;
      s.values.forEach((v) => { if (v.y == null) { on = false; return; } d += (on ? 'L' : 'M') + x(v.x).toFixed(1) + ' ' + y(v.y).toFixed(1); on = true; });
      b += '<path d="' + d + '" class="line ' + (s.cls || '') + '"' + (s.code ? ' data-driver="' + s.code + '"' : '') + ' style="stroke:' + (s.colour || 'var(--c-accent)') + '"' + (s.dashed ? ' stroke-dasharray="5 3"' : '') + '/>';
      if (s.label) { const last = s.values.filter((v) => v.y != null).slice(-1)[0]; if (last && o.endLabels) b += text(Math.min(x(last.x) + 4, w - 40), y(last.y) + 4, s.label, 'tl'); }
    });
    if (o.cursor != null) b += '<line x1="' + x(o.cursor) + '" x2="' + x(o.cursor) + '" y1="' + top + '" y2="' + (h - padB) + '" class="cursor"/>';
    return svg(w, h, b, o.aria || 'Line chart');
  };

  // ---------- calibration (reliability) diagram ----------
  registry.calib = function (w, h, o) {
    const pad = 36, x = scale(0, 1, pad, w - 12), y = scale(0, 1, h - 26, 10);
    let b = '<line x1="' + x(0) + '" y1="' + y(0) + '" x2="' + x(1) + '" y2="' + y(1) + '" class="diag"/>';
    [0, 0.5, 1].forEach((t) => { b += text(x(t), h - 8, pct(t), 'tm', 'middle') + text(pad - 6, y(t) + 4, pct(t), 'tm', 'end'); });
    let path = '';
    M.calibration.forEach((c, i) => {
      path += (i ? 'L' : 'M') + x(c.predicted) + ' ' + y(c.observed);
      b += '<circle cx="' + x(c.predicted) + '" cy="' + y(c.observed) + '" r="' + (2.5 + Math.sqrt(c.n) / 3) + '" class="calib-dot"><title>Predicted ' + pct(c.predicted) + ', happened ' + pct(c.observed) + ' (' + c.n + ' forecasts)</title></circle>';
    });
    b = '<path d="' + path + '" class="line" style="stroke:var(--c-accent)"/>' + b;
    b += text(w - 12, h - 30, 'Predicted', 'tm', 'end') + text(pad + 4, 20, 'Happened', 'tm');
    return svg(w, h, b, 'Calibration: predicted top-3 probability against how often it happened. Dot size is number of forecasts.');
  };

  // ---------- paired bars: model vs baseline per round ----------
  registry.paired = function (w, h, o) {
    const rows = M.evaluation, padL = 34, padB = 22, top = 10;
    const max = Math.max(...rows.map((r) => Math.max(r.rpsModel, r.rpsGrid))) * 1.08;
    const bw = (w - padL - 8) / rows.length, y = scale(0, max, h - padB, top);
    let b = '';
    [0, max / 2, max].forEach((t) => { b += '<line x1="' + padL + '" x2="' + (w - 8) + '" y1="' + y(t) + '" y2="' + y(t) + '" class="grid"/>' + text(padL - 4, y(t) + 4, t.toFixed(2), 'tm', 'end'); });
    rows.forEach((r, i) => {
      const x0 = padL + i * bw;
      b += '<rect x="' + (x0 + bw * 0.12) + '" y="' + y(r.rpsGrid) + '" width="' + bw * 0.36 + '" height="' + (y(0) - y(r.rpsGrid)) + '" class="bar-base"><title>R' + r.round + ' grid baseline ' + r.rpsGrid.toFixed(3) + '</title></rect>';
      b += '<rect x="' + (x0 + bw * 0.5) + '" y="' + y(r.rpsModel) + '" width="' + bw * 0.36 + '" height="' + (y(0) - y(r.rpsModel)) + '" class="bar-model"><title>R' + r.round + ' model ' + r.rpsModel.toFixed(3) + '</title></rect>';
      if (bw > 18 || i % 3 === 0) b += text(x0 + bw / 2, h - 6, String(r.round), 'tm', 'middle');
    });
    return svg(w, h, b, 'Ranked probability score per round, model against grid-order baseline. Lower is better.');
  };

  // ---------- interval chart (championship P10–P90 points) ----------
  registry.interval = function (w, h, o) {
    const rows = o.rows, padL = 44, padR = 54, top = 8, rowH = (h - top - 18) / rows.length;
    const min = Math.min(...rows.map((r) => r.points)) * 0.95, max = Math.max(...rows.map((r) => r.p90)) * 1.02;
    const x = scale(min, max, padL, w - padR);
    let b = '';
    rows.forEach((r, i) => {
      const y = top + rowH * i + rowH / 2, d = team(r.code);
      b += '<g data-driver="' + r.code + '">' + text(4, y + 4, r.code, 'tl');
      b += '<line x1="' + x(r.points) + '" x2="' + x(r.p10) + '" y1="' + y + '" y2="' + y + '" class="whisker" stroke-dasharray="2 3"/>';
      b += '<rect x="' + x(r.p10) + '" y="' + (y - 5) + '" width="' + (x(r.p90) - x(r.p10)) + '" height="10" rx="5" style="fill:' + d.colour + ';opacity:.75"/>';
      b += '<circle cx="' + x(r.points) + '" cy="' + y + '" r="3.5" class="median"/>';
      b += text(w - padR + 6, y + 4, pct(r.title), 'tl') + '</g>';
    });
    b += text(padL, h - 3, 'Dot: points now · bar: final points P10–P90 · right: title chance', 'tm');
    return svg(w, h, b, 'Championship points now and the simulated final points range');
  };

  // ---------- track map with cars ----------
  function catmull(points, w, h, pad) {
    const P = points.map(([a, b]) => [pad + a * (w - pad * 2), pad + b * (h - pad * 2)]);
    let d = 'M' + P[0][0].toFixed(1) + ' ' + P[0][1].toFixed(1);
    for (let i = 0; i < P.length; i++) {
      const p0 = P[(i - 1 + P.length) % P.length], p1 = P[i], p2 = P[(i + 1) % P.length], p3 = P[(i + 2) % P.length];
      const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6], c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
      d += 'C' + c1.map((v) => v.toFixed(1)).join(' ') + ' ' + c2.map((v) => v.toFixed(1)).join(' ') + ' ' + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1);
    }
    return d;
  }
  registry.track = function (w, h, o, el) {
    const d = catmull(M.trackPoints, w, h, o.pad || 22);
    let b = '<path d="' + d + '" class="track-outer"/><path d="' + d + '" class="track-inner" id="trk-' + el.dataset.cid + '"/>';
    b += '<g class="cars"></g>';
    if (!o.noLabel) b += text(10, h - 10, 'Schematic circuit, not to scale (mock)', 'tm');
    setTimeout(() => placeCars(el, o.lap || 0, o), 0);
    return svg(w, h, b, 'Track map with car positions');
  };
  function placeCars(el, lap, o) {
    const path = el.querySelector('.track-inner'), g = el.querySelector('.cars');
    if (!path || !g) return;
    const len = path.getTotalLength(), state = Replay.state(lap);
    let s = '';
    state.order.slice().reverse().forEach((r) => {
      const p = path.getPointAtLength(((r.progress % 1) + 1) % 1 * len), d = team(r.code);
      const focus = o.focus && o.focus.includes(r.code);
      s += '<g data-driver="' + r.code + '" class="car' + (focus ? ' car-focus' : '') + '" transform="translate(' + p.x.toFixed(1) + ' ' + p.y.toFixed(1) + ')">';
      s += '<circle r="' + (o.carR || 6) + '" style="fill:' + d.colour + '"' + (d.second ? ' class="car-second"' : '') + '/>';
      if (o.labels !== false && (r.pos <= (o.labelTop || 3) || focus)) s += '<text x="9" y="4" class="tl">' + r.code + '</text>';
      s += '</g>';
    });
    g.innerHTML = s;
  }

  // ---------- sparkline ----------
  registry.spark = function (w, h, o) {
    const v = o.values, x = scale(0, v.length - 1, 2, w - 2);
    const lo = o.min != null ? o.min : Math.min(...v), hi = o.max != null ? o.max : Math.max(...v);
    const y = o.invert ? scale(lo, hi, 3, h - 3) : scale(lo, hi, h - 3, 3);
    const d = v.map((p, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(p == null ? hi : p).toFixed(1)).join('');
    return svg(w, h, '<path d="' + d + '" class="line" style="stroke:' + (o.colour || 'var(--c-accent)') + '"/><circle cx="' + x(v.length - 1) + '" cy="' + y(v[v.length - 1] == null ? hi : v[v.length - 1]) + '" r="2.5" style="fill:' + (o.colour || 'var(--c-accent)') + '"/>', o.aria || 'Trend');
  };

  // ---------- histogram of team fantasy totals ----------
  registry.hist = function (w, h, o) {
    const v = o.values, bins = o.bins || 24, lo = Math.min(...v), hi = Math.max(...v), counts = new Array(bins).fill(0);
    v.forEach((p) => { counts[Math.min(bins - 1, Math.floor((p - lo) / (hi - lo || 1) * bins))]++; });
    const max = Math.max(...counts), bw = (w - 20) / bins, y = scale(0, max, h - 20, 6);
    let b = '';
    counts.forEach((c, i) => {
      const mid = lo + (i + 0.5) * (hi - lo) / bins, inBand = mid >= o.p10 && mid <= o.p90;
      b += '<rect x="' + (10 + i * bw + 1) + '" y="' + y(c) + '" width="' + (bw - 2) + '" height="' + (y(0) - y(c)) + '" class="' + (inBand ? 'bar-model' : 'bar-base') + '"/>';
    });
    b += text(10, h - 4, Math.round(lo) + ' pts', 'tm') + text(w - 10, h - 4, Math.round(hi) + ' pts', 'tm', 'end');
    if (o.mean != null) { const mx = 10 + (o.mean - lo) / (hi - lo) * (w - 20); b += '<line x1="' + mx + '" x2="' + mx + '" y1="6" y2="' + (h - 20) + '" class="cursor"/>' + text(mx + 4, 16, 'mean ' + o.mean.toFixed(0), 'tl'); }
    return svg(w, h, b, 'Distribution of simulated team points; highlighted bars are the P10 to P90 range');
  };

  // ---------- ridgeline of finish distributions ----------
  registry.ridge = function (w, h, o) {
    const rows = o.rows, padL = 40, k = o.amp || 2.2, step = (h - 28) / (rows.length + k * 0.9), amp = step * k, x = scale(1, 22, padL, w - 10);
    let b = '';
    rows.forEach((s, i) => {
      const base = 14 + amp * 0.9 + step * i, d = team(s.code);
      let path = 'M' + x(1) + ' ' + base;
      for (let p = 1; p <= 22; p++) path += 'L' + x(p).toFixed(1) + ' ' + (base - s.matrix[p - 1] * amp / Math.max(0.2, Math.max(...s.matrix.slice(0, 22))) * 0.9).toFixed(1);
      path += 'L' + x(22) + ' ' + base + 'Z';
      b += '<g data-driver="' + s.code + '"><path d="' + path + '" style="fill:' + d.colour + ';fill-opacity:.35;stroke:' + d.colour + '" class="ridge"/>' + text(4, base - 2, s.code, 'tl') + '</g>';
    });
    [1, 5, 10, 15, 20].forEach((p) => { b += text(x(p), h - 2, 'P' + p, 'tm', 'middle'); });
    return svg(w, h, b, 'Finish position distribution per driver');
  };

  // ---------- fifty futures: each tile is one simulated race's podium ----------
  registry.futures = function (w, h, o) {
    const sim = o.sim || M.base, n = o.n || 50, cols = o.cols || 10, gap = 6;
    const tw = (w - gap * (cols - 1)) / cols, th = Math.max(40, tw * 0.62);
    const step = Math.floor(sim.sims / n);
    let b = '';
    for (let k = 0; k < n; k++) {
      const s = k * step, podium = [];
      M.drivers.forEach((d) => { const p = sim.finish[d.idx][s]; if (p >= 1 && p <= 3) podium[p - 1] = d.code; });
      const x0 = (k % cols) * (tw + gap), y0 = Math.floor(k / cols) * (th + gap);
      b += '<g class="future"><rect x="' + x0 + '" y="' + y0 + '" width="' + tw + '" height="' + th + '" rx="3" class="future-bg"/>';
      podium.forEach((code, p) => {
        const bh = (th - 8) / 3, yy = y0 + 4 + p * bh;
        b += '<g data-driver="' + code + '"><rect x="' + (x0 + 4) + '" y="' + (yy + 1) + '" width="' + (tw - 8) * [1, 0.78, 0.6][p] + '" height="' + (bh - 2) + '" rx="2" style="fill:' + team(code).colour + '"/>' + (tw > 54 ? text(x0 + 8, yy + bh / 2 + 3.5, code, 'future-t') : '') + '</g>';
      });
      b += '</g>';
    }
    return svg(w, Math.ceil(n / cols) * (th + gap), b, n + ' simulated races. Each tile shows that race\'s podium, longest bar is the winner.');
  };

  // ---------- probability bars (HTML) ----------
  function bars(rows, opts) {
    const o = Object.assign({ key: 'win', max: null, n: 10, fmt: (v) => pct(v, 1) }, opts);
    const list = rows.slice(0, o.n), max = o.max || Math.max(...list.map((r) => r[o.key]));
    return '<div class="pbars">' + list.map((r) => {
      const d = team(r.code);
      return '<div class="pbar" data-driver="' + r.code + '"><span class="pbar-code"><i style="background:' + d.colour + '"></i>' + r.code + '</span><span class="pbar-track"><span class="pbar-fill" style="width:' + (r[o.key] / max * 100).toFixed(1) + '%"></span></span><span class="pbar-val">' + o.fmt(r[o.key]) + '</span></div>';
    }).join('') + '</div>';
  }

  // ---------- replay state at a fractional lap ----------
  const Replay = {
    timeAt(lap) {
      const r = M.race, L = Math.max(0, Math.min(r.laps, lap)), i = Math.floor(L), f = L - i;
      const t0 = i === 0 ? 0 : r.leaderEnd[i - 1], t1 = r.leaderEnd[Math.min(r.laps - 1, i)];
      return t0 + (t1 - t0) * f;
    },
    state(lap) {
      const r = M.race, t = Replay.timeAt(lap);
      const rows = r.rows.map((row) => {
        let k = row.lapEnd.findIndex((e) => e > t);
        const done = k === -1 ? row.lapEnd.length : k;
        const prevEnd = done === 0 ? 0 : row.lapEnd[done - 1];
        const nextEnd = row.lapEnd[done];
        const frac = nextEnd ? Math.max(0, Math.min(1, (t - prevEnd) / (nextEnd - prevEnd))) : 0;
        const out = !!row.retiredLap && done >= row.lapEnd.length;
        const stint = row.plan.find((p) => done + 1 >= p.from && done + 1 <= p.to) || row.plan[row.plan.length - 1];
        return { code: row.code, completed: done, progress: out ? -1 : done + frac, out, compound: stint.compound, tyreAge: done + 1 - stint.from, last: row.lapTime[done - 1], lapEnd: row.lapEnd };
      });
      const live = rows.filter((x) => !x.out).sort((a, b) => b.progress - a.progress);
      const lead = live[0];
      live.forEach((x, i) => {
        x.pos = i + 1;
        const k = x.completed;
        x.gap = i === 0 ? 'Leader' : (k > 0 && lead.lapEnd[k - 1] != null ? '+' + Math.max(0, x.lapEnd[k - 1] - lead.lapEnd[k - 1]).toFixed(1) + 's' : '—');
        if (lead.completed - x.completed >= 1 && i > 0) x.gap = '+' + (lead.completed - x.completed) + ' lap';
      });
      const outRows = rows.filter((x) => x.out).map((x) => Object.assign(x, { pos: null, gap: 'DNF' }));
      const sc = r.scLaps.includes(Math.floor(lap) + 1) && lap >= r.scLaps[0] - 1;
      return { lap, leaderLap: Math.min(r.laps, Math.floor(lead.progress) + 1), order: live, out: outRows, sc };
    },
    placeCars
  };

  window.C = { chart, mount, redraw, update, registry, bars, pct, esc, Replay, team };
})();
