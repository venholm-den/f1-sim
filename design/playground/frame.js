/* Renders one concept + screen inside a frame, and wires the shared interactions:
   driver focus, replay scrubbing, the Fantasy picker and the Simulation Lab. */
(function () {
  'use strict';
  const M = window.MOCK;
  const params = new URLSearchParams(location.search);
  const conceptId = (params.get('c') || 'a').toLowerCase();
  const screen = params.get('s') || 'hub';
  const SCREENS = [
    ['hub', 'Weekend hub'], ['predict', 'Race prediction'], ['fantasy', 'Fantasy'], ['replay', 'Replay'],
    ['intel', 'Drivers & teams'], ['lab', 'Simulation lab'], ['eval', 'Model evaluation']
  ];

  // ---------- shared derived data ----------
  const sum = M.base.summary.slice().sort((a, b) => b.win - a.win || a.avgFinish - b.avgFinish);
  const byAvg = M.base.summary.slice().sort((a, b) => a.avgFinish - b.avgFinish);
  const cand = Object.fromEntries(M.candidate.summary.map((s) => [s.code, s]));

  // ---------- Fantasy picker (same rule as the app: 5 drivers + 2 constructors) ----------
  const Fantasy = (function () {
    const D = M.drivers.map((d) => ({ code: d.code, price: d.price, pts: M.base.summary[d.idx].fantasyMean, idx: d.idx }));
    const T = M.teams.map((t) => {
      const ds = M.drivers.filter((d) => d.team === t.id);
      return { code: t.id, price: t.price, pts: ds.reduce((a, d) => a + M.base.summary[d.idx].fantasyMean, 0), members: ds.map((d) => d.idx) };
    });
    const combos = [];
    (function rec(start, pick) {
      if (pick.length === 5) {
        const cost = pick.reduce((a, i) => a + D[i].price, 0);
        const pts = pick.reduce((a, i) => a + D[i].pts, 0);
        const boost = pick.reduce((b, i) => (D[i].pts > D[b].pts ? i : b), pick[0]);
        combos.push({ ids: pick.slice(), cost, pts: pts + D[boost].pts, boost });
        return;
      }
      for (let i = start; i < D.length; i++) { pick.push(i); rec(i + 1, pick); pick.pop(); }
    })(0, []);
    combos.sort((a, b) => b.pts - a.pts);
    function pick(state) {
      const budget = state.budget || 100, lock = state.lock || {}, out = [];
      const lockedD = D.filter((d) => lock[d.code] === 'in').map((d) => d.idx);
      const banD = new Set(D.filter((d) => lock[d.code] === 'out').map((d) => d.idx));
      for (let a = 0; a < T.length; a++) for (let b = a + 1; b < T.length; b++) {
        const pair = [T[a], T[b]];
        if (pair.some((t) => lock[t.code] === 'out')) continue;
        const needT = T.filter((t) => lock[t.code] === 'in');
        if (!needT.every((t) => pair.includes(t))) continue;
        const left = budget - pair[0].price - pair[1].price;
        const c = combos.find((x) => x.cost <= left + 1e-9 && lockedD.every((i) => x.ids.includes(i)) && !x.ids.some((i) => banD.has(i)));
        if (c) out.push({ drivers: c.ids.map((i) => D[i].code), boost: D[c.boost].code, cons: pair.map((t) => t.code), cost: c.cost + pair[0].price + pair[1].price, pts: c.pts + pair[0].pts + pair[1].pts });
      }
      out.sort((x, y) => y.pts - x.pts);
      return out;
    }
    function distribution(team) {
      const sims = M.base.sims, f = M.base.fantasy, vals = new Array(sims).fill(0);
      team.drivers.forEach((code) => { const i = M.byCode[code].idx, k = code === team.boost ? 2 : 1; for (let s = 0; s < sims; s++) vals[s] += f[i][s] * k; });
      team.cons.forEach((tc) => T.find((t) => t.code === tc).members.forEach((i) => { for (let s = 0; s < sims; s++) vals[s] += f[i][s]; }));
      const sorted = vals.slice().sort((a, b) => a - b);
      return { values: vals, p10: M.quantile(sorted, 0.1), p50: M.quantile(sorted, 0.5), p90: M.quantile(sorted, 0.9), mean: vals.reduce((a, b) => a + b, 0) / sims };
    }
    return { D, T, pick, distribution, state: { budget: 100, lock: {} } };
  })();

  // ---------- context passed to each concept ----------
  const ctx = {
    M, C: window.C, sum, byAvg, cand, Fantasy, screen, SCREENS, conceptId,
    pct: C.pct, esc: C.esc, team: C.team,
    mobile: () => window.innerWidth < 720,
    mockTag: '<span class="mock-tag" title="Generated for design review. Not model output.">Mock data</span>',
    replayLap: 24.4,
    live: {},
    labState: { driverNoise: 0.24, safetyCar: 0.45, gridWeight: 0.35, dnfRate: 0.045, sims: 1500, toggles: Object.fromEntries(M.lab.candidates.map((c) => [c.key, c.on])) },
    labResult: null
  };
  window.CTX = ctx;

  function render() {
    const concept = window.CONCEPTS[conceptId];
    document.documentElement.dataset.concept = conceptId;
    document.title = concept.name + ' · ' + (SCREENS.find((s) => s[0] === screen) || ['', ''])[1];
    ctx.live = {};
    document.getElementById('app').innerHTML = concept.render(screen, ctx);
    C.mount(document);
    applyFocus();
    wire();
    if (screen === 'replay') setLap(ctx.replayLap);
    if (window.parent !== window) window.parent.postMessage({ type: 'frame', c: conceptId, s: screen }, '*');
  }

  // ---------- driver focus (synchronised highlighting) ----------
  let focus = params.get('focus') ? [params.get('focus')] : [];
  function applyFocus() {
    document.documentElement.classList.toggle('has-focus', focus.length > 0);
    document.querySelectorAll('[data-driver]').forEach((el) => el.classList.toggle('is-focus', focus.includes(el.dataset.driver)));
    document.querySelectorAll('[data-focus-label]').forEach((el) => { el.textContent = focus.length ? focus.join(' vs ') : 'All drivers'; });
  }
  function toggleFocus(code, additive) {
    if (focus.includes(code)) focus = focus.filter((c) => c !== code);
    else focus = additive ? focus.concat(code).slice(-2) : [code];
    applyFocus();
  }

  // ---------- replay ----------
  let playTimer = null;
  function setLap(lap) {
    ctx.replayLap = Math.max(0, Math.min(M.race.laps, lap));
    const st = C.Replay.state(ctx.replayLap);
    document.querySelectorAll('.chart-track[data-cid]').forEach((el) => C.Replay.placeCars(el, ctx.replayLap, { focus, labelTop: el.dataset.labels ? Number(el.dataset.labels) : 6 }));
    document.querySelectorAll('.chart-bump[data-cid], .chart-tyres[data-cid]').forEach((el) => C.update(el, { lap: Math.max(1, ctx.replayLap), focus }));
    document.querySelectorAll('[data-live]').forEach((el) => { const fn = ctx.live[el.dataset.live]; if (fn) el.innerHTML = fn(st); });
    document.querySelectorAll('input[data-scrub]').forEach((el) => { el.value = ctx.replayLap; el.setAttribute('aria-valuetext', 'Lap ' + st.leaderLap + ' of ' + M.race.laps); });
    applyFocus();
  }
  function play() {
    if (playTimer) { clearInterval(playTimer); playTimer = null; markPlay(false); return; }
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    markPlay(true);
    playTimer = setInterval(() => {
      if (ctx.replayLap >= M.race.laps) { play(); return; }
      setLap(ctx.replayLap + (reduce ? 1 : 0.08));
    }, reduce ? 900 : 60);
  }
  function markPlay(on) { document.querySelectorAll('[data-act="play"]').forEach((b) => { b.setAttribute('aria-pressed', on); b.textContent = on ? (b.dataset.pause || 'Pause') : (b.dataset.playLabel || 'Play'); }); }

  // ---------- simulation lab ----------
  function runLab() {
    const s = ctx.labState;
    ctx.labResult = M.simulate({ sims: s.sims, seed: 2026, driverNoise: s.driverNoise, safetyCar: s.toggles.safety_cars ? s.safetyCar : 0, gridWeight: s.gridWeight, dnfRate: s.toggles.survival ? s.dnfRate : s.dnfRate * 0.8 });
    document.querySelectorAll('[data-live^="lab"]').forEach((el) => { const fn = ctx.live[el.dataset.live]; if (fn) el.innerHTML = fn(); });
    C.mount(document.querySelector('[data-live="lab-charts"]') || document.createElement('div'));
    applyFocus();
  }

  // ---------- fantasy ----------
  function refreshFantasy() {
    document.querySelectorAll('[data-live^="fantasy"]').forEach((el) => { const fn = ctx.live[el.dataset.live]; if (fn) el.innerHTML = fn(); });
    document.querySelectorAll('[data-live^="fantasy"]').forEach((el) => C.mount(el));
    applyFocus();
  }

  function wire() {
    const app = document.getElementById('app');
    app.onclick = (e) => {
      const act = e.target.closest('[data-act]');
      if (act) {
        const a = act.dataset.act;
        if (a === 'play') play();
        if (a === 'step') setLap(Math.round(ctx.replayLap) + Number(act.dataset.by));
        if (a === 'jump') setLap(Number(act.dataset.lap));
        if (a === 'asset') {
          const code = act.dataset.code, cur = Fantasy.state.lock[code];
          Fantasy.state.lock[code] = cur === undefined ? 'in' : cur === 'in' ? 'out' : undefined;
          if (Fantasy.state.lock[code] === undefined) delete Fantasy.state.lock[code];
          refreshFantasy();
        }
        if (a === 'reset-picks') { Fantasy.state.lock = {}; refreshFantasy(); }
        if (a === 'toggle') { ctx.labState.toggles[act.dataset.key] = !ctx.labState.toggles[act.dataset.key]; act.setAttribute('aria-pressed', ctx.labState.toggles[act.dataset.key]); runLab(); }
        if (a === 'clear-focus') { focus = []; applyFocus(); }
        return;
      }
      const d = e.target.closest('[data-driver]');
      if (d && !e.target.closest('input,select,a')) toggleFocus(d.dataset.driver, e.shiftKey);
    };
    app.oninput = (e) => {
      const t = e.target;
      if (t.dataset.scrub !== undefined) { if (playTimer) play(); setLap(Number(t.value)); }
      if (t.dataset.param) { ctx.labState[t.dataset.param] = Number(t.value); const out = document.querySelector('[data-out="' + t.dataset.param + '"]'); if (out) out.textContent = t.dataset.fmt === 'pct' ? Math.round(t.value * 100) + '%' : Number(t.value).toFixed(2); clearTimeout(runLab.t); runLab.t = setTimeout(runLab, 120); }
      if (t.dataset.budget !== undefined) { Fantasy.state.budget = Number(t.value); refreshFantasy(); }
    };
    if (screen === 'lab') runLab();
  }

  document.addEventListener('keydown', (e) => {
    if (e.target.matches('[data-cmd]') && e.key === 'Enter') { command(e.target.value); e.target.value = ''; return; }
    if (e.target.matches('input[type=text],input[type=search],input[type=number],textarea')) return;
    if (screen === 'replay') {
      if (e.key === ' ') { e.preventDefault(); play(); }
      if (e.key === 'ArrowRight' && !e.target.matches('input[type=range]')) setLap(Math.round(ctx.replayLap) + 1);
      if (e.key === 'ArrowLeft' && !e.target.matches('input[type=range]')) setLap(Math.round(ctx.replayLap) - 1);
      if (e.key === 'Home') setLap(0);
      if (e.key === 'End') setLap(M.race.laps);
    }
    if (e.key === 'Escape') { focus = []; applyFocus(); }
    if (/^[1-7]$/.test(e.key) && !e.metaKey && !e.ctrlKey && !e.altKey) location.search = '?c=' + conceptId + '&s=' + SCREENS[Number(e.key) - 1][0];
    if (e.key === 'Enter' && e.target.closest('[data-driver]') && !e.target.matches('button')) toggleFocus(e.target.closest('[data-driver]').dataset.driver, e.shiftKey);
  });
  // Command line (concept C): a driver code focuses, a screen name navigates.
  function command(raw) {
    const words = raw.trim().toUpperCase().split(/\s+/).filter(Boolean);
    const alias = { HUB: 'hub', WKND: 'hub', PRED: 'predict', FANT: 'fantasy', RPLY: 'replay', REPLAY: 'replay', INTL: 'intel', LAB: 'lab', EVAL: 'eval' };
    const codes = words.filter((w) => M.byCode[w]);
    const target = words.map((w) => alias[w]).find(Boolean);
    if (target && target !== screen) { location.search = '?c=' + conceptId + '&s=' + target + (codes[0] ? '&focus=' + codes[0] : ''); return; }
    if (codes.length) { focus = codes.slice(0, 2); applyFocus(); }
    const out = document.querySelector('[data-cmd-out]');
    if (out) out.textContent = codes.length ? 'FOCUS ' + codes.slice(0, 2).join(' vs ') : target ? 'ALREADY ON ' + target.toUpperCase() : 'UNKNOWN: ' + raw;
  }
  let resizeT;
  window.addEventListener('resize', () => { clearTimeout(resizeT); resizeT = setTimeout(render, 150); });
  window.addEventListener('DOMContentLoaded', render);
  window.FRAME = { render, setLap, toggleFocus };
})();
