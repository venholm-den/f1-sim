/* Concept A: Pit Wall (Motorsport Command Centre).
   A tiled, keyboard-first engineering workspace. Timing colours carry meaning:
   purple = best overall, green = improved, amber = caution/safety car. */
(function () {
  'use strict';
  const panel = (area, title, meta, body, cls) => '<section class="a-panel ' + (cls || '') + '" style="grid-area:' + area + '"><header><h2>' + title + '</h2>' + (meta ? '<span class="a-meta">' + meta + '</span>' : '') + '</header><div class="a-body">' + body + '</div></section>';

  function shell(ctx, inner) {
    const W = ctx.M.weekend;
    return '<div class="a-shell">' +
      '<header class="a-top"><div class="a-brand"><span class="a-mark" aria-hidden="true">RW</span><span>Race Workbench</span></div>' +
      '<div class="a-event"><span class="num">R' + W.round + '</span> ' + W.event + ' <span class="muted">· ' + W.venue + '</span></div>' +
      BLK.nav(ctx, 'a-tabs', { hub: 'Weekend', predict: 'Predict', fantasy: 'Fantasy', replay: 'Replay', intel: 'Drivers', lab: 'Lab', eval: 'Eval' }) +
      '<div class="a-clock"><span class="a-led"></span><span>FP3 in</span> <b class="num">03:06:12</b>' + ctx.mockTag + '</div></header>' +
      '<div class="a-grid a-' + ctx.screen + '">' + inner + '</div>' +
      '<footer class="a-keys"><span><kbd>1</kbd>–<kbd>7</kbd> workspaces</span><span><kbd>Space</kbd> play</span><span><kbd>←</kbd><kbd>→</kbd> lap</span><span><kbd>Shift</kbd>+click compare two</span><span><kbd>Esc</kbd> clear focus</span><span class="a-focus">Focus: <b data-focus-label>All drivers</b></span></footer></div>';
  }

  const screens = {
    hub(ctx) {
      const W = ctx.M.weekend, F = W.forecast, top = ctx.sum.slice(0, 8);
      return panel('sched', 'Session timeline', W.sessions.filter((s) => s.state === 'done').length + '/5 complete', BLK.schedule(ctx, 'a-sched')) +
        panel('fc', 'Latest forecast', F.status, BLK.metricsHtml([['Input session', F.session], ['Frozen', F.frozenAt], ['Simulations', F.sims.toLocaleString()], ['Model', F.model]]) + '<div class="a-actions"><a href="?c=a&s=predict" class="a-btn primary">Open prediction</a><a href="?c=a&s=lab" class="a-btn">Run scenario</a><a href="?c=a&s=fantasy" class="a-btn">Pick team</a></div>') +
        panel('win', 'Win probability', 'top 8', C.bars(top, { key: 'win', n: 8 })) +
        panel('range', 'Finish range', 'P10–P90 · middle half · median', C.chart('range', { h: 300, rows: ctx.byAvg.slice(0, 10), teamColour: true })) +
        panel('wx', 'Conditions', 'forecast', BLK.metricsHtml([['Air', W.weather.air + '°C'], ['Track', W.weather.track + '°C'], ['Rain (race window)', Math.round(W.weather.rainChance * 100) + '%'], ['Wind', W.weather.wind + ' km/h']]) + '<p class="cap muted">Race-window weather is informational and does not change driver probabilities.</p>') +
        panel('champ', 'Championship', '5 rounds left', C.chart('interval', { h: 210, rows: ctx.M.championship }));
    },
    predict(ctx) {
      const lead = ctx.sum[0].code;
      return panel('tower', 'Predicted classification', 'sorted by average finish', '<div class="scroll-x">' + BLK.driverTable(ctx, { cols: ['avg', 'win', 'podium', 'points', 'dnf', 'range'] }) + '</div>', 'a-dense') +
        panel('heat', 'Finish distribution', 'P1–P10, % of sims', C.chart('heat', { rows: ctx.byAvg.slice(0, 12), upto: 10 })) +
        panel('dots', 'Outcome dots · ' + lead, '1 dot = 2% of races', C.chart('dots', { h: 150, code: lead }) + '<p class="cap muted">Click any driver to focus them across every panel. Shift-click a second driver to compare.</p>') +
        panel('qr', 'Qualifying vs race', 'median grid → average finish', C.chart('scatter', { h: 240, points: ctx.byAvg.slice(0, 14).map((s) => ({ x: s.gridMedian, y: 23 - s.avgFinish, label: s.code, colour: C.team(s.code).colour })), xLabel: 'Median grid →', yLabel: '↑ Better finish', labelAbove: 0, aria: 'Median grid position against average finish' }));
    },
    fantasy(ctx) {
      BLK.registerFantasy(ctx);
      return panel('chips', 'Market', 'click: lock in → leave out → auto', '<div data-live="fantasy-chips">' + BLK.fantasyChips(ctx) + '</div><label class="a-budget">Budget <input type="number" min="80" max="120" step="0.5" value="' + ctx.Fantasy.state.budget + '" data-budget class="num"> $m</label>') +
        panel('team', 'Best team', 'max expected points', '<div data-live="fantasy-team">' + ctx.live['fantasy-team']() + '</div>') +
        panel('kpi', 'Team outlook', 'from 4,000 toy sims', '<div data-live="fantasy-metrics">' + ctx.live['fantasy-metrics']() + '</div><div data-live="fantasy-dist">' + ctx.live['fantasy-dist']() + '</div>') +
        panel('rr', 'Risk / reward', 'bubble = price', BLK.riskReward(ctx, 280)) +
        panel('alt', 'Alternatives', 'next best constructor pairs', '<div class="scroll-x" data-live="fantasy-alt">' + ctx.live['fantasy-alt']() + '</div>');
    },
    replay(ctx) {
      BLK.registerReplay(ctx);
      return panel('tower', 'Timing', '<span data-live="flag"></span>', '<div data-live="tower"></div>', 'a-dense') +
        panel('map', 'Track', '<span class="a-lap">Lap <span data-live="lap"></span></span>', C.chart('track', { h: ctx.mobile() ? 240 : 360, lap: ctx.replayLap }) + BLK.replayControls(ctx, 'rp-controls a-ctrl')) +
        panel('events', 'Race control', 'click to jump', '<div data-live="events" class="a-scroll"></div>') +
        panel('bump', 'Positions', 'lap by lap', C.chart('bump', { h: 260, lap: ctx.replayLap, cursor: true })) +
        panel('tyres', 'Tyre stints', 'S · M · H', C.chart('tyres', { h: 300, lap: ctx.replayLap })) +
        panel('tel', 'Telemetry · fastest laps', ctx.M.telemetry.a + ' vs ' + ctx.M.telemetry.b, BLK.telemetry(ctx, 150));
    },
    intel(ctx) {
      return panel('h2h', 'Head to head', 'PIA vs NOR · 18 rounds', BLK.h2h(ctx, 'PIA', 'NOR')) +
        panel('form', 'Season form', 'finishing position by round', BLK.formLines(ctx, ['PIA', 'NOR', 'VER', 'RUS'], 260)) +
        panel('table', 'Driver form', 'last six races', '<div class="scroll-x">' + BLK.formTable(ctx, 22) + '</div>', 'a-dense');
    },
    lab(ctx) {
      BLK.registerLab(ctx);
      return panel('params', 'Scenario B parameters', 'A = established run', BLK.labSliders(ctx) + '<p class="cap muted">The playground re-runs a toy engine in your browser. In the app, scenarios would run as a cancellable job with the same seed as A.</p>') +
        panel('cands', 'Model candidates', 'unpromoted · local only', BLK.labToggles(ctx)) +
        panel('diff', 'A vs B', '<span data-live="lab-meta"></span>', '<div data-live="lab-diff"></div>', 'a-dense') +
        panel('range', 'Scenario B finish range', '', '<div data-live="lab-charts"></div>');
    },
    eval(ctx) {
      return panel('kpi', 'Season scorecard', '2026 · rounds 1–18', BLK.metricsHtml(BLK.evalKpis(ctx))) +
        panel('rps', 'Ranked probability score', 'lower is better · grey = grid order', C.chart('paired', { h: 220 })) +
        panel('cal', 'Calibration · top 3', 'dot size = forecasts', C.chart('calib', { h: 260 })) +
        panel('table', 'Round by round', '', '<div class="scroll-x a-scroll">' + BLK.evalTable(ctx) + '</div>', 'a-dense');
    }
  };

  window.CONCEPTS.a = {
    name: 'A · Pit Wall',
    render(screen, ctx) { return shell(ctx, screens[screen](ctx)); }
  };
})();
