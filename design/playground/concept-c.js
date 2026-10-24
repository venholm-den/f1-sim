/* Concept C: Quant Terminal (Quantitative Prediction Terminal).
   Information-dense and keyboard-led, like a market terminal. Every number has
   a distribution next to it; every change shows its delta. */
(function () {
  'use strict';
  const pane = (code, title, body, cls) => '<section class="c-pane ' + (cls || '') + '"><header><span class="c-code">' + code + '</span><h2>' + title + '</h2></header><div class="c-body">' + body + '</div></section>';

  function shell(ctx, inner) {
    const keys = { hub: 'HUB', predict: 'PRED', fantasy: 'FANT', replay: 'RPLY', intel: 'INTL', lab: 'LAB', eval: 'EVAL' };
    const F = ctx.M.weekend.forecast;
    return '<div class="c-shell"><header class="c-cmd"><span class="c-prompt">RWB&gt;</span><label class="sr" for="cmd">Command</label><input id="cmd" type="text" data-cmd autocomplete="off" spellcheck="false" placeholder="PIA NOR  ·  PRED  ·  FANT  ·  type a driver code or screen and press Enter"><span class="c-out" data-cmd-out aria-live="polite"></span>' + ctx.mockTag + '</header>' +
      '<nav class="c-fkeys" aria-label="Workspaces">' + ctx.SCREENS.map(([k], i) => '<a href="?c=c&s=' + k + '"' + (k === ctx.screen ? ' aria-current="page"' : '') + '><b>F' + (i + 1) + '</b>' + keys[k] + '</a>').join('') + '</nav>' +
      '<div class="c-status"><span>USGP R19</span><span>INPUT ' + F.session + '</span><span>RUN 2026-19-FP2-a41c</span><span>SEED 2026</span><span>N ' + ctx.M.base.sims.toLocaleString() + '</span><span>MODEL ' + F.model.toUpperCase() + '</span><span class="c-ok">FROZEN ✓</span><span class="c-focus">FOCUS <b data-focus-label>All drivers</b></span></div>' +
      '<div class="c-grid c-' + ctx.screen + '">' + inner + '</div></div>';
  }
  const history = (code) => {
    const r = window.MOCK.rng(code.charCodeAt(0) * 7 + code.charCodeAt(2)), w = window.MOCK.base.summary[window.MOCK.byCode[code].idx].win;
    return [w * (0.7 + r() * 0.6), w * (0.75 + r() * 0.5), w * (0.85 + r() * 0.3), w];
  };
  function monitor(ctx, n) {
    return '<table class="dt c-mon"><thead><tr><th>TKR</th><th class="r">WIN</th><th>PRE→FP2</th><th class="r">Δ FP1</th><th class="r">POD</th><th class="r">PTS</th><th class="r">DNF</th><th class="r">E[POS]</th><th class="r">P10</th><th class="r">P90</th><th class="r">E[FAN]</th></tr></thead><tbody>' +
      ctx.sum.slice(0, n).map((s) => { const h = history(s.code), dlt = h[3] - h[2]; return '<tr data-driver="' + s.code + '" tabindex="0"><td>' + BLK.sw(s.code) + '<b>' + s.code + '</b></td><td class="num r">' + C.pct(s.win, 1) + '</td><td style="width:70px">' + C.chart('spark', { h: 16, values: h, colour: dlt >= 0 ? 'var(--c-pos)' : 'var(--c-neg)', aria: s.code + ' win chance across forecasts' }) + '</td><td class="num r ' + (dlt >= 0 ? 'pos' : 'neg') + '">' + BLK.pp(dlt) + '</td><td class="num r">' + C.pct(s.podium, 1) + '</td><td class="num r">' + C.pct(s.points, 0) + '</td><td class="num r">' + C.pct(s.dnf, 1) + '</td><td class="num r">' + s.avgFinish.toFixed(2) + '</td><td class="num r">' + Math.round(s.p10) + '</td><td class="num r">' + Math.round(s.p90) + '</td><td class="num r">' + s.fantasyMean.toFixed(1) + '</td></tr>'; }).join('') + '</tbody></table>';
  }
  function cumulative(ctx) {
    const ks = [1, 3, 5, 10];
    return '<table class="dt"><thead><tr><th>TKR</th>' + ks.map((k) => '<th class="r">P(≤' + k + ')</th>').join('') + '<th class="r">P(POLE)</th><th class="r">GRID→FIN</th></tr></thead><tbody>' + ctx.byAvg.slice(0, 14).map((s) => {
      const cum = (k) => s.matrix.slice(0, k).reduce((a, b) => a + b, 0), g = s.gridMedian - s.avgFinish;
      return '<tr data-driver="' + s.code + '"><td><b>' + s.code + '</b></td>' + ks.map((k) => '<td class="num r" style="--a:' + cum(k).toFixed(2) + '"><span class="c-cell">' + C.pct(cum(k), 0) + '</span></td>').join('') + '<td class="num r">' + C.pct(s.poleChance, 0) + '</td><td class="num r ' + (g >= 0 ? 'pos' : 'neg') + '">' + BLK.signed(g) + '</td></tr>';
    }).join('') + '</tbody></table>';
  }
  function lapMatrix(ctx) {
    ctx.live.matrix = (st) => {
      const L = st.leaderLap, from = Math.max(1, L - 7), to = Math.min(ctx.M.race.laps, from + 9), laps = [];
      for (let l = from; l <= to; l++) laps.push(l);
      return '<table class="dt c-lapm"><thead><tr><th>TKR</th>' + laps.map((l) => '<th class="r' + (l === L ? ' c-now' : '') + '">L' + l + '</th>').join('') + '</tr></thead><tbody>' + st.order.slice(0, 12).map((r) =>
        '<tr data-driver="' + r.code + '"><td><b>' + r.code + '</b></td>' + laps.map((l) => {
          const p = ctx.M.race.positions[l - 1][r.code], prev = l > 1 ? ctx.M.race.positions[l - 2][r.code] : p;
          const cls = l > L ? 'muted' : p < prev ? 'pos' : p > prev ? 'neg' : '';
          return '<td class="num r ' + cls + (l === L ? ' c-now' : '') + '">' + (l > L ? '·' : p == null ? 'OUT' : p) + '</td>';
        }).join('') + '</tr>').join('') + '</tbody></table>';
    };
    return '<div class="scroll-x" data-live="matrix"></div>';
  }

  const screens = {
    hub(ctx) {
      return pane('MON', 'Forecast monitor · sorted by win', '<div class="scroll-x">' + monitor(ctx, 22) + '</div>', 'c-span2 c-tall3') +
        pane('SCHED', 'Weekend', BLK.schedule(ctx, 'c-sched')) +
        pane('DIST', 'Finish distribution · ridgeline', C.chart('ridge', { h: 300, rows: ctx.byAvg.slice(0, 10) })) +
        pane('WDC', 'Title odds · final points P10–P90', C.chart('interval', { h: 190, rows: ctx.M.championship }));
    },
    predict(ctx) {
      const lead = ctx.sum[0].code;
      return pane('PROB', 'Cumulative position probabilities', '<div class="scroll-x">' + cumulative(ctx) + '</div>') +
        pane('HEAT', 'P(position) · full field', '<div class="scroll-x">' + C.chart('heat', { rows: ctx.byAvg, upto: 22 }) + '</div>', 'c-span2') +
        pane('RIDGE', 'Distribution shape', C.chart('ridge', { h: 340, rows: ctx.byAvg.slice(0, 12), amp: 2.6 })) +
        pane('QDOT', 'Quantile dots · ' + lead + ' · 1 dot = 2%', C.chart('dots', { h: 130, code: lead })) +
        pane('IQR', 'Finish intervals', C.chart('range', { h: 330, rows: ctx.byAvg.slice(0, 12) }));
    },
    fantasy(ctx) {
      BLK.registerFantasy(ctx, { alts: 8, histH: 130 });
      return pane('MKT', 'Asset universe · click lock/exclude', '<div data-live="fantasy-chips">' + BLK.fantasyChips(ctx) + '</div><label class="c-inline">BUDGET $<input type="number" class="num" min="80" max="120" step="0.5" value="' + ctx.Fantasy.state.budget + '" data-budget>m</label>', 'c-span3') +
        pane('OPT', 'Optimal portfolio', '<div data-live="fantasy-team">' + ctx.live['fantasy-team']() + '</div><div data-live="fantasy-metrics">' + ctx.live['fantasy-metrics']() + '</div>') +
        pane('PNL', 'Team points distribution', '<div data-live="fantasy-dist">' + ctx.live['fantasy-dist']() + '</div><p class="cap muted">Highlighted bars: P10–P90. Line: mean.</p>') +
        pane('FRONT', 'Value frontier · price vs E[pts]', BLK.valueScatter(ctx, 260)) +
        pane('RISK', 'Risk vs return · bubble = price', BLK.riskReward(ctx, 260)) +
        pane('ALT', 'Next-best portfolios', '<div class="scroll-x" data-live="fantasy-alt">' + ctx.live['fantasy-alt']() + '</div>', 'c-span2');
    },
    replay(ctx) {
      BLK.registerReplay(ctx, { compact: false });
      const top = ctx.M.race.startOrder.slice(0, 5);
      return pane('TWR', 'Timing · <span data-live="flag"></span> · lap <span data-live="lap"></span>', '<div data-live="tower"></div>', 'c-tall') +
        pane('MAP', 'Track', C.chart('track', { h: 250, lap: ctx.replayLap, labelTop: 4 }) + BLK.replayControls(ctx)) +
        pane('LAPM', 'Position matrix · ±7 laps', lapMatrix(ctx)) +
        pane('LAPT', 'Lap times · top 5 · pit and SC laps removed', C.chart('lines', { h: 220, aria: 'Lap times for the top five starters', yMin: 96.5, yMax: 101, yTicks: [97, 99, 101], yFmt: (v) => v.toFixed(0) + 's', xTicks: [1, 14, 28, 42, 56], xFmt: (v) => 'L' + v, bands: [[24, 26]], endLabels: true,
          series: top.map((code) => { const row = ctx.M.race.rows.find((r) => r.code === code); return { code, label: code, colour: C.team(code).colour, dashed: C.team(code).second, values: row.lapTime.map((t, i) => ({ x: i + 1, y: (t > 101.5 || i === 0) ? null : t })) }; }) })) +
        pane('BUMP', 'Running order', C.chart('bump', { h: 220, lap: ctx.replayLap, cursor: true })) +
        pane('TEL', 'Telemetry · ' + ctx.M.telemetry.a + ' vs ' + ctx.M.telemetry.b, BLK.telemetry(ctx, 130)) +
        pane('EVT', 'Event log', '<div data-live="events" class="c-scroll"></div>', 'c-span2');
    },
    intel(ctx) {
      const rows = ctx.byAvg.map((s) => { const f = ctx.M.seasonForm.find((x) => x.code === s.code).races, fin = f.filter((r) => r.finish).map((r) => r.finish), g = f.reduce((a, r) => a + r.quali, 0) / f.length, mf = fin.reduce((a, b) => a + b, 0) / fin.length, sd = Math.sqrt(fin.reduce((a, b) => a + (b - mf) * (b - mf), 0) / fin.length); return { code: s.code, g, mf, gain: g - mf, sd, dnf: f.length - fin.length, pace: f.reduce((a, r) => a + r.paceDelta, 0) / f.length }; });
      return pane('STATS', 'Season factor table · 18 rounds', '<div class="scroll-x"><table class="dt"><thead><tr><th>TKR</th><th class="r">AVG GRID</th><th class="r">AVG FIN</th><th class="r">GAIN</th><th class="r">SD FIN</th><th class="r">DNF</th><th class="r">PACE Δ s/lap</th></tr></thead><tbody>' + rows.map((r) => '<tr data-driver="' + r.code + '"><td>' + BLK.sw(r.code) + '<b>' + r.code + '</b></td><td class="num r">' + r.g.toFixed(1) + '</td><td class="num r">' + r.mf.toFixed(1) + '</td><td class="num r ' + (r.gain >= 0 ? 'pos' : 'neg') + '">' + BLK.signed(r.gain) + '</td><td class="num r">' + r.sd.toFixed(1) + '</td><td class="num r">' + r.dnf + '</td><td class="num r">' + r.pace.toFixed(2) + '</td></tr>').join('') + '</tbody></table></div>', 'c-tall') +
        pane('H2H', 'Pair · PIA / NOR', BLK.h2h(ctx, 'PIA', 'NOR'), 'c-span2') +
        pane('FORM', 'Finishing position by round', BLK.formLines(ctx, ['PIA', 'NOR', 'VER', 'RUS', 'LEC'], 260));
    },
    lab(ctx) {
      BLK.registerLab(ctx, { n: 14, rangeH: 340 });
      return pane('PARAM', 'Scenario B · parameters', BLK.labSliders(ctx)) +
        pane('ENG', 'Candidate engines', BLK.labToggles(ctx) + '<p class="cap muted">Unpromoted candidates stay local and are labelled on every output. Promotion needs chronological backtests.</p>') +
        pane('DIFF', 'A (established) vs B · <span data-live="lab-meta"></span>', '<div data-live="lab-diff"></div>', 'c-tall') +
        pane('B.IQR', 'Scenario B intervals', '<div data-live="lab-charts"></div>', 'c-span2');
    },
    eval(ctx) {
      return pane('KPI', 'Scorecard', BLK.metricsHtml(BLK.evalKpis(ctx)), 'c-span3') +
        pane('RPS', 'RPS by round · model (orange) vs grid (grey)', C.chart('paired', { h: 240 }), 'c-span2') +
        pane('CAL', 'Reliability · P(top 3)', C.chart('calib', { h: 240 })) +
        pane('LOG', 'Round log', '<div class="scroll-x c-scroll">' + BLK.evalTable(ctx) + '</div>', 'c-span3');
    }
  };

  window.CONCEPTS.c = {
    name: 'C · Quant Terminal',
    render(screen, ctx) { return shell(ctx, screens[screen](ctx)); }
  };
})();
