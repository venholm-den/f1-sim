/* MOCK DATA for the design playground only.
   Every number here is generated from a seeded toy simulation so the screens stay
   internally consistent. None of it comes from the Race Workbench model, and the
   toy engine below is not the production simulator. */
(function () {
  'use strict';

  function rng(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function normal(r) {
    let u = 0, v = 0;
    while (u === 0) u = r();
    while (v === 0) v = r();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  const quantile = (sorted, q) => {
    if (!sorted.length) return null;
    const i = (sorted.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
  };

  // Approximate team colours for data-vis use only.
  const teams = [
    { id: 'MCL', name: 'McLaren', colour: '#FF8000', price: 32.4 },
    { id: 'MER', name: 'Mercedes', colour: '#27F4D2', price: 34.0 },
    { id: 'RBR', name: 'Red Bull Racing', colour: '#3671C6', price: 32.7 },
    { id: 'FER', name: 'Ferrari', colour: '#E8002D', price: 28.2 },
    { id: 'RBS', name: 'Racing Bulls', colour: '#6692FF', price: 16.5 },
    { id: 'ALP', name: 'Alpine', colour: '#2293D1', price: 18.8 },
    { id: 'AST', name: 'Aston Martin', colour: '#229971', price: 4.5 },
    { id: 'HAA', name: 'Haas', colour: '#B6BABD', price: 12.0 },
    { id: 'AUD', name: 'Audi', colour: '#9B1C31', price: 10.4 },
    { id: 'WIL', name: 'Williams', colour: '#64C4FF', price: 12.6 },
    { id: 'CAD', name: 'Cadillac', colour: '#C9A227', price: 3.0 }
  ];
  const teamById = Object.fromEntries(teams.map((t) => [t.id, t]));

  // pace: toy seconds-per-lap deficit to the quickest car. quali: one-lap deficit.
  const raw = [
    ['PIA', 'Oscar Piastri', 81, 'MCL', 0.00, 0.05, 23.4],
    ['NOR', 'Lando Norris', 4, 'MCL', 0.16, 0.00, 26.1],
    ['RUS', 'George Russell', 63, 'MER', 0.06, 0.08, 27.9],
    ['ANT', 'Kimi Antonelli', 12, 'MER', 0.14, 0.20, 27.1],
    ['VER', 'Max Verstappen', 1, 'RBR', 0.07, 0.10, 28.2],
    ['HAD', 'Isack Hadjar', 6, 'RBR', 0.55, 0.50, 16.3],
    ['LEC', 'Charles Leclerc', 16, 'FER', 0.24, 0.15, 24.1],
    ['HAM', 'Lewis Hamilton', 44, 'FER', 0.30, 0.32, 24.4],
    ['LAW', 'Liam Lawson', 30, 'RBS', 0.62, 0.60, 9.9],
    ['LIN', 'Arvid Lindblad', 41, 'RBS', 0.86, 0.80, 10.0],
    ['GAS', 'Pierre Gasly', 10, 'ALP', 0.80, 0.70, 10.2],
    ['COL', 'Franco Colapinto', 43, 'ALP', 0.95, 0.90, 8.8],
    ['ALO', 'Fernando Alonso', 14, 'AST', 0.76, 0.78, 5.4],
    ['STR', 'Lance Stroll', 18, 'AST', 1.02, 1.05, 3.0],
    ['OCO', 'Esteban Ocon', 31, 'HAA', 0.82, 0.86, 9.9],
    ['BEA', 'Oliver Bearman', 87, 'HAA', 0.78, 0.74, 6.4],
    ['HUL', 'Nico Hülkenberg', 27, 'AUD', 0.80, 0.83, 6.6],
    ['BOR', 'Gabriel Bortoleto', 5, 'AUD', 0.88, 0.84, 7.0],
    ['ALB', 'Alexander Albon', 23, 'WIL', 0.70, 0.72, 4.6],
    ['SAI', 'Carlos Sainz', 55, 'WIL', 0.72, 0.68, 8.4],
    ['PER', 'Sergio Pérez', 11, 'CAD', 1.15, 1.20, 3.6],
    ['BOT', 'Valtteri Bottas', 77, 'CAD', 1.24, 1.22, 3.0]
  ];
  const drivers = raw.map(([code, name, number, team, pace, quali, price], i) => ({
    code, name, number, team, teamName: teamById[team].name, colour: teamById[team].colour,
    pace, quali, price, idx: i,
    second: raw.findIndex((r) => r[3] === team) !== i // second car of the team: dashed line
  }));
  const N = drivers.length;

  // ---------- toy Monte Carlo ----------
  const RACE_PTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1];
  const QUALI_PTS = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1];

  function simulate(opts) {
    const o = Object.assign({ sims: 4000, seed: 2026, driverNoise: 0.24, dnfRate: 0.045, gridWeight: 0.35, safetyCar: 0.45 }, opts || {});
    const r = rng(o.seed);
    const finish = drivers.map(() => new Int16Array(o.sims));
    const grid = drivers.map(() => new Int16Array(o.sims));
    const fantasy = drivers.map(() => new Float32Array(o.sims));
    const matrix = drivers.map(() => new Float64Array(N + 1)); // last column = DNF
    const scIdx = [];
    for (let s = 0; s < o.sims; s++) {
      const q = drivers.map((d) => ({ i: d.idx, v: d.quali + normal(r) * 0.22 })).sort((a, b) => a.v - b.v);
      const gpos = new Int16Array(N);
      q.forEach((x, p) => { gpos[x.i] = p + 1; grid[x.i][s] = p + 1; });
      const sc = r() < o.safetyCar;
      if (sc) scIdx.push(s);
      const noise = sc ? o.driverNoise * 1.35 : o.driverNoise;
      const rows = drivers.map((d) => ({
        i: d.idx,
        dnf: r() < o.dnfRate,
        v: d.pace * (1 - o.gridWeight) + (gpos[d.idx] - 1) * 0.06 * o.gridWeight * 4 + normal(r) * noise
      }));
      rows.sort((a, b) => (a.dnf - b.dnf) || (a.v - b.v));
      rows.forEach((x, p) => {
        const pos = p + 1;
        finish[x.i][s] = x.dnf ? 0 : pos;
        matrix[x.i][x.dnf ? N : p] += 1;
        const g = gpos[x.i];
        let pts = g <= 10 ? QUALI_PTS[g - 1] : 0;
        if (x.dnf) pts -= 20;
        else pts += (pos <= 10 ? RACE_PTS[pos - 1] : 0) + (g - pos);
        fantasy[x.i][s] = pts;
      });
    }
    const summary = drivers.map((d) => {
      const f = Array.from(finish[d.idx]);
      const fin = f.filter((x) => x > 0).sort((a, b) => a - b);
      const pts = Array.from(fantasy[d.idx]).sort((a, b) => a - b);
      const g = Array.from(grid[d.idx]).sort((a, b) => a - b);
      const count = (fn) => f.filter(fn).length / o.sims;
      return {
        code: d.code,
        win: count((x) => x === 1), podium: count((x) => x > 0 && x <= 3), points: count((x) => x > 0 && x <= 10),
        dnf: count((x) => x === 0), avgFinish: fin.reduce((a, b) => a + b, 0) / Math.max(1, fin.length),
        p10: quantile(fin, 0.1), p25: quantile(fin, 0.25), p50: quantile(fin, 0.5), p75: quantile(fin, 0.75), p90: quantile(fin, 0.9),
        gridMedian: quantile(g, 0.5), poleChance: g.filter((x) => x === 1).length / o.sims,
        fantasyMean: pts.reduce((a, b) => a + b, 0) / o.sims,
        fantasyP10: quantile(pts, 0.1), fantasyP50: quantile(pts, 0.5), fantasyP90: quantile(pts, 0.9),
        fantasySd: Math.sqrt(pts.reduce((a, b) => a + b * b, 0) / o.sims - Math.pow(pts.reduce((a, b) => a + b, 0) / o.sims, 2)),
        matrix: Array.from(matrix[d.idx], (c) => c / o.sims)
      };
    });
    return { opts: o, sims: o.sims, finish, grid, fantasy, summary, safetyCarShare: scIdx.length / o.sims };
  }

  // ---------- toy race for the replay ----------
  const LAPS = 56, PIT_LOSS = 21.5, BASE = 98.6, SC_LAPS = [24, 25, 26];
  const COMPOUND_DEG = { S: 0.085, M: 0.055, H: 0.035 };
  const COMPOUND_OFFSET = { S: -0.55, M: 0, H: 0.45 };
  function buildRace() {
    const r = rng(77);
    const plans = [
      [['M', 1, 21], ['H', 22, 56]], [['M', 1, 19], ['H', 20, 56]], [['S', 1, 14], ['H', 15, 38], ['M', 39, 56]],
      [['M', 1, 23], ['H', 24, 56]], [['M', 1, 20], ['H', 21, 56]], [['S', 1, 13], ['H', 14, 56]]
    ];
    const order = drivers.map((d) => ({ d, q: d.quali + normal(r) * 0.18 })).sort((a, b) => a.q - b.q);
    const startPos = {};
    order.forEach((x, i) => { startPos[x.d.code] = i + 1; });
    const out = drivers.map((d) => {
      const plan = plans[(d.idx * 7 + 3) % plans.length].map(([c, a, b]) => ({ compound: c, from: a, to: b }));
      return { code: d.code, plan, lapEnd: [], lapTime: [], retiredLap: null, grid: startPos[d.code] };
    });
    const retire = { BOT: 31, COL: 47 };
    // Lap-by-lap cumulative times. Grid order sets the start offset.
    out.forEach((row) => { row.cum = (row.grid - 1) * 0.35; });
    for (let lap = 1; lap <= LAPS; lap++) {
      const sc = SC_LAPS.includes(lap);
      out.forEach((row) => {
        if (row.retiredLap) return;
        const d = drivers.find((x) => x.code === row.code);
        if (retire[row.code] === lap) { row.retiredLap = lap; return; }
        const stint = row.plan.find((p) => lap >= p.from && lap <= p.to);
        const age = lap - stint.from;
        let t = BASE + d.pace + COMPOUND_OFFSET[stint.compound] + COMPOUND_DEG[stint.compound] * age - lap * 0.055 + normal(r) * 0.22;
        if (lap === 1) t += 6 + (row.grid - 1) * 0.12;
        if (row.plan.some((p) => p.from === lap + 1)) t += PIT_LOSS * (sc ? 0.55 : 1);
        if (sc) t = BASE + 24;
        row.cum += t;
        row.lapTime.push(t);
        row.lapEnd.push(row.cum);
      });
      if (sc) {
        // Field bunches up behind the safety car.
        const live = out.filter((x) => !x.retiredLap && x.lapEnd.length === lap).sort((a, b) => a.cum - b.cum);
        const lead = live[0].cum;
        live.forEach((x, i) => { x.cum = lead + i * 0.9; x.lapEnd[lap - 1] = x.cum; });
      }
    }
    const positions = []; // positions[lap-1][code] = position
    for (let lap = 1; lap <= LAPS; lap++) {
      const running = out.filter((x) => x.lapEnd.length >= lap).sort((a, b) => a.lapEnd[lap - 1] - b.lapEnd[lap - 1]);
      const row = {};
      running.forEach((x, i) => { row[x.code] = i + 1; });
      out.filter((x) => x.lapEnd.length < lap).forEach((x) => { row[x.code] = null; });
      positions.push(row);
    }
    const leaderEnd = positions.map((row, i) => Math.min(...out.filter((x) => x.lapEnd.length > i).map((x) => x.lapEnd[i])));
    let fastest = { code: null, lap: 0, time: Infinity };
    out.forEach((x) => x.lapTime.forEach((t, i) => { if (!SC_LAPS.includes(i + 1) && i > 0 && t < fastest.time && !x.plan.some((p) => p.from === i + 2)) fastest = { code: x.code, lap: i + 1, time: t }; }));
    const events = [{ lap: 1, kind: 'start', text: 'Lights out. ' + order[0].d.code + ' leads from pole.' }];
    out.forEach((x) => x.plan.slice(1).forEach((p) => events.push({ lap: p.from - 1, kind: 'pit', code: x.code, text: x.code + ' pits for ' + ({ S: 'softs', M: 'mediums', H: 'hards' })[p.compound] + '.' })));
    events.push({ lap: SC_LAPS[0], kind: 'sc', text: 'Safety car: debris at Turn 12.' });
    events.push({ lap: SC_LAPS[SC_LAPS.length - 1] + 1, kind: 'green', text: 'Green flag. Racing resumes.' });
    Object.entries(retire).forEach(([code, lap]) => events.push({ lap, kind: 'dnf', code, text: code + ' retires (mock: hydraulics).' }));
    for (let lap = 2; lap <= LAPS; lap++) {
      const prev = positions[lap - 2], cur = positions[lap - 1];
      Object.keys(cur).forEach((code) => {
        if (cur[code] && prev[code] && cur[code] <= 3 && cur[code] < prev[code] && !events.some((e) => e.kind === 'pit' && Math.abs(e.lap - lap) <= 1)) {
          events.push({ lap, kind: 'move', code, text: code + ' up to P' + cur[code] + '.' });
        }
      });
    }
    events.push({ lap: fastest.lap, kind: 'fastest', code: fastest.code, text: 'Fastest lap so far: ' + fastest.code + ' ' + fmtLap(fastest.time) + '.' });
    events.sort((a, b) => a.lap - b.lap);
    return { laps: LAPS, scLaps: SC_LAPS, rows: out, positions, leaderEnd, events, fastest, startOrder: order.map((x) => x.d.code) };
  }
  function fmtLap(t) {
    const m = Math.floor(t / 60), s = t - m * 60;
    return m + ':' + (s < 10 ? '0' : '') + s.toFixed(3);
  }

  // Schematic circuit (not a real track map).
  const trackPoints = [[0.08, 0.62], [0.30, 0.66], [0.52, 0.70], [0.62, 0.86], [0.74, 0.88], [0.80, 0.72], [0.70, 0.58], [0.76, 0.46], [0.90, 0.40], [0.94, 0.24], [0.84, 0.14], [0.66, 0.16], [0.52, 0.24], [0.40, 0.18], [0.26, 0.12], [0.12, 0.20], [0.10, 0.34], [0.20, 0.42], [0.10, 0.50]];

  // Telemetry: speed against distance for two fastest laps.
  function telemetry(code, offset) {
    const r = rng(code.charCodeAt(0) * 31 + code.charCodeAt(1));
    const corners = [[480, 85], [1180, 180], [1450, 150], [1720, 165], [2230, 110], [2650, 95], [3390, 70], [3900, 125], [4300, 140], [4680, 105], [5150, 92]];
    const pts = [];
    for (let x = 0; x <= 5500; x += 25) {
      let v = 318;
      corners.forEach(([at, min]) => {
        const dist = Math.abs(x - at);
        const brakeZone = 260, exitZone = 420;
        if (x <= at && dist < brakeZone) v = Math.min(v, min + (318 - min) * Math.pow(dist / brakeZone, 0.9));
        if (x > at && dist < exitZone) v = Math.min(v, min + (318 - min) * Math.pow(dist / exitZone, 0.75));
      });
      v += normal(r) * 0.8 + offset * Math.sin(x / 700) * (v < 200 ? 1.6 : 0.5);
      pts.push({ d: x, speed: Math.max(60, v) });
    }
    for (let i = 0; i < pts.length; i++) {
      const prev = pts[Math.max(0, i - 1)].speed, next = pts[Math.min(pts.length - 1, i + 1)].speed;
      pts[i].throttle = next >= prev - 0.5 ? Math.min(100, 60 + (pts[i].speed - 60) / 2.6) : 0;
      pts[i].brake = next < prev - 2 ? 1 : 0;
    }
    return pts;
  }
  function deltaTrace(a, b) {
    let ta = 0, tb = 0;
    return a.map((p, i) => {
      if (i > 0) {
        const dx = p.d - a[i - 1].d;
        ta += dx / (p.speed / 3.6);
        tb += dx / (b[i].speed / 3.6);
      }
      return { d: p.d, delta: tb - ta };
    });
  }

  // ---------- season, evaluation and weekend (mock) ----------
  const rounds = ['Australia', 'China', 'Japan', 'Bahrain', 'Saudi Arabia', 'Miami', 'Canada', 'Monaco', 'Barcelona', 'Austria', 'Britain', 'Belgium', 'Hungary', 'Netherlands', 'Italy', 'Madrid', 'Azerbaijan', 'Singapore'];
  const er = rng(404);
  const evaluation = rounds.map((name, i) => {
    const model = 0.072 + er() * 0.03 - i * 0.0007;
    const grid = model + 0.004 + er() * 0.016 - 0.004;
    return { round: i + 1, name, rpsModel: model, rpsGrid: grid, winnerProb: 0.12 + er() * 0.45, top3Hit: Math.round(1 + er() * 2) };
  });
  const calibration = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95].map((p, i) => {
    const n = Math.round(160 * Math.exp(-i * 0.32)) + 6;
    const obs = Math.min(0.99, Math.max(0.01, p + (er() - 0.5) * 0.09 - (p > 0.6 ? 0.04 : 0)));
    return { predicted: p, observed: obs, n };
  });
  // Season form: each round re-ranks the field so positions are unique.
  const fr = rng(911);
  const perRound = rounds.map(() => {
    const q = drivers.map((d) => ({ c: d.code, v: d.quali + normal(fr) * 0.25 })).sort((a, b) => a.v - b.v);
    const race = drivers.map((d) => ({ c: d.code, v: d.pace + normal(fr) * 0.3, dnf: fr() < 0.05, delta: d.pace + normal(fr) * 0.12 })).sort((a, b) => (a.dnf - b.dnf) || (a.v - b.v));
    const out = {};
    q.forEach((x, i) => { out[x.c] = { quali: i + 1 }; });
    race.forEach((x, i) => { out[x.c].finish = x.dnf ? null : i + 1; out[x.c].paceDelta = x.delta; });
    return out;
  });
  const seasonForm = drivers.map((d) => ({ code: d.code, races: perRound.map((r, i) => Object.assign({ round: i + 1 }, r[d.code])) }));
  const championship = [
    { code: 'PIA', points: 346, title: 0.47, p10: 402, p90: 468 },
    { code: 'NOR', points: 331, title: 0.30, p10: 384, p90: 452 },
    { code: 'VER', points: 304, title: 0.14, p10: 355, p90: 428 },
    { code: 'RUS', points: 288, title: 0.08, p10: 336, p90: 405 },
    { code: 'LEC', points: 201, title: 0.01, p10: 238, p90: 290 },
    { code: 'ANT', points: 175, title: 0.0, p10: 205, p90: 262 }
  ];
  const weekend = {
    year: 2026, round: 19, event: 'United States Grand Prix', venue: 'Circuit of the Americas', city: 'Austin',
    laps: LAPS, lengthKm: 5.513,
    sessions: [
      { code: 'FP1', name: 'Practice 1', day: 'Fri 23 Oct', time: '17:30', state: 'done' },
      { code: 'FP2', name: 'Practice 2', day: 'Fri 23 Oct', time: '21:00', state: 'done' },
      { code: 'FP3', name: 'Practice 3', day: 'Sat 24 Oct', time: '17:30', state: 'next' },
      { code: 'Q', name: 'Qualifying', day: 'Sat 24 Oct', time: '21:00', state: 'upcoming' },
      { code: 'R', name: 'Race', day: 'Sun 25 Oct', time: '20:00', state: 'upcoming' }
    ],
    forecast: { session: 'FP2', frozenAt: 'Fri 23 Oct 23:41', sims: 5000, model: 'Performance v1', status: 'Frozen' },
    weather: { air: 27, track: 41, rainChance: 0.08, wind: 11 }
  };
  const lab = {
    established: { label: 'Established model', sims: 5000, seed: 2026 },
    candidates: [
      { key: 'safety_cars', label: 'Safety cars and VSCs', on: true },
      { key: 'pair_overtaking', label: 'Pair overtaking', on: false },
      { key: 'survival', label: 'Survival retirements', on: true },
      { key: 'race_weather', label: 'Race-window weather', on: false },
      { key: 'shared_noise', label: 'Shared team luck', on: false },
      { key: 'grid_sampling', label: 'Sampled grids', on: true },
      { key: 'penalties', label: 'Announced grid penalties', on: false },
      { key: 'track_profile', label: 'Calibrated track profile', on: false }
    ]
  };

  window.MOCK = {
    note: 'Mock data generated in the browser for design review. Not model output.',
    drivers, teams, teamById, byCode: Object.fromEntries(drivers.map((d) => [d.code, d])),
    simulate, rng, normal, quantile, fmtLap,
    race: buildRace(), trackPoints,
    telemetry: { a: 'PIA', b: 'RUS', traceA: null, traceB: null },
    evaluation, calibration, seasonForm, championship, weekend, lab, rounds,
    RACE_PTS, QUALI_PTS
  };
  const tA = telemetry('PIA', 0), tB = telemetry('RUS', -4);
  window.MOCK.telemetry.traceA = tA;
  window.MOCK.telemetry.traceB = tB;
  window.MOCK.telemetry.delta = deltaTrace(tA, tB);
  window.MOCK.base = simulate();
  window.MOCK.candidate = simulate({ seed: 2026, safetyCar: 0.62, driverNoise: 0.36, gridWeight: 0.30 });
})();
