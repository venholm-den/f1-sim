/* Recommended hybrid: Pit Wall's synchronised, keyboard-first workspace (A),
   with Grid's plain-language answers on top of every screen (D) and Raceline's
   uncertainty pictures (E) as the signature charts. */
(function () {
  'use strict';
  const panel = (area, title, meta, body, cls) => '<section class="a-panel ' + (cls || '') + '" style="grid-area:' + area + '"><header><h2>' + title + '</h2>' + (meta ? '<span class="a-meta">' + meta + '</span>' : '') + '</header><div class="a-body">' + body + '</div></section>';
  const answers = (items) => '<div class="h-answers" style="grid-area:ans">' + items.map(([k, v, s]) => '<div class="h-answer"><span>' + k + '</span><b>' + v + '</b><small>' + s + '</small></div>').join('') + '</div>';
  const more = (body, label) => '<details class="h-more"><summary>' + (label || 'Show the maths') + '</summary>' + body + '</details>';

  function shell(ctx, inner) {
    const W = ctx.M.weekend;
    return '<div class="a-shell h-shell">' +
      '<header class="a-top"><div class="a-brand"><span class="a-mark" aria-hidden="true">RW</span><span>Race Workbench</span></div>' +
      '<div class="a-event"><span class="num">R' + W.round + '</span> ' + W.event + '</div>' +
      BLK.nav(ctx, 'a-tabs', { hub: 'Weekend', predict: 'Predict', fantasy: 'Fantasy', replay: 'Replay', intel: 'Drivers', lab: 'Lab', eval: 'Accuracy' }) +
      '<div class="a-clock"><span class="a-led"></span><span>Forecast after ' + W.forecast.session + '</span>' + ctx.mockTag + '</div></header>' +
      '<div class="a-grid h-grid h-' + ctx.screen + '">' + inner + '</div>' +
      '<footer class="a-keys"><span><kbd>1</kbd>–<kbd>7</kbd> workspaces</span><span><kbd>Space</kbd> play</span><span><kbd>←</kbd><kbd>→</kbd> lap</span><span><kbd>Shift</kbd>+click compare</span><span><kbd>Esc</kbd> clear</span><span class="a-focus">Focus: <b data-focus-label>All drivers</b></span></footer></div>';
  }

  const screens = {
    hub(ctx) {
      const s = ctx.sum, W = ctx.M.weekend;
      return answers([['Favourite', C.team(s[0].code).name, 'wins ' + C.pct(s[0].win, 0) + ' of simulated races'], ['Contenders', String(s.filter((x) => x.win >= 0.15).length), 'drivers with at least 15% win chance'], ['Next session', 'Practice 3', W.sessions[2].day + ' · ' + W.sessions[2].time], ['Forecast', W.forecast.status, W.forecast.sims.toLocaleString() + ' races after ' + W.forecast.session]]) +
        panel('sched', 'Weekend', '', BLK.schedule(ctx, 'a-sched')) +
        panel('dots', 'Where the favourites finish', '1 dot = 2% of races', '<div class="h-dotrows">' + s.slice(0, 4).map((x) => '<div data-driver="' + x.code + '"><b>' + x.code + '</b>' + C.chart('dots', { h: 118, code: x.code }) + '</div>').join('') + '</div>') +
        panel('win', 'Win chance', 'top 8', C.bars(s, { key: 'win', n: 8 }) + more(C.chart('range', { h: 280, rows: ctx.byAvg.slice(0, 10), teamColour: true }), 'Finish ranges')) +
        panel('champ', 'Championship', '5 rounds left', C.chart('interval', { h: 200, rows: ctx.M.championship }));
    },
    predict(ctx) {
      const s = ctx.sum[0];
      return answers([['Most likely winner', s.code + ' · ' + C.pct(s.win, 0), 'but someone else wins ' + C.pct(1 - s.win, 0) + ' of the time'], ['Likely podium', ctx.byAvg.slice(0, 3).map((x) => x.code).join(' · '), 'by average finish'], ['Widest range (top 8)', (() => { const w = ctx.byAvg.slice(0, 8).sort((x, y) => (y.p75 - y.p25) - (x.p75 - x.p25))[0]; return w.code + ' · P' + Math.round(w.p25) + '–' + Math.round(w.p75); })(), 'middle half of finishes'], ['Retirement risk', C.pct(ctx.sum[0].dnf, 0), 'favourite\'s chance of not finishing']]) +
        panel('fut', 'Fifty futures', 'each tile = one simulated podium', C.chart('futures', { n: 40, cols: ctx.mobile() ? 5 : 10 })) +
        panel('tower', 'Classification', 'average finish', '<div class="scroll-x">' + BLK.driverTable(ctx, { n: 12, cols: ['win', 'podium', 'points', 'range'] }) + '</div>' + more('<div class="scroll-x">' + C.chart('heat', { rows: ctx.byAvg.slice(0, 12), upto: 10 }) + '</div>', 'Every position'), 'a-dense') +
        panel('ridge', 'Distribution shape', 'top 8', C.chart('ridge', { h: 300, rows: ctx.byAvg.slice(0, 8) }));
    },
    fantasy(ctx) {
      BLK.registerFantasy(ctx, { alts: 4 });
      ctx.live['fantasy-answers'] = () => {
        const t = ctx.Fantasy.pick(ctx.Fantasy.state)[0];
        if (!t) return answers([['Best team', '—', 'no team fits these locks and the budget'], ['Usual range', '—', ''], ['Boost', '—', ''], ['Spend', '—', '']]);
        const d = ctx.Fantasy.distribution(t);
        return answers([['Best team', d.mean.toFixed(0) + ' pts', 'expected, under $' + ctx.Fantasy.state.budget + 'm'], ['Usual range', Math.round(d.p10) + '–' + Math.round(d.p90), 'P10 to P90 of simulated races'], ['Boost', t.boost + ' 2×', 'highest expected driver'], ['Spend', '$' + t.cost.toFixed(1) + 'm', 'of $' + ctx.Fantasy.state.budget + 'm']]);
      };
      return '<div data-live="fantasy-answers" style="grid-area:ans;display:contents">' + ctx.live['fantasy-answers']() + '</div>' +
        panel('team', 'Team', 'click a market chip to lock or exclude', '<div data-live="fantasy-team">' + ctx.live['fantasy-team']() + '</div><div data-live="fantasy-dist">' + ctx.live['fantasy-dist']() + '</div>') +
        panel('chips', 'Market', 'lock in → leave out → auto', '<div data-live="fantasy-chips">' + BLK.fantasyChips(ctx) + '</div>') +
        panel('rr', 'Risk and reward', 'bubble = price', BLK.riskReward(ctx, 300)) +
        panel('alt', 'Alternatives', '', '<div class="scroll-x" data-live="fantasy-alt">' + ctx.live['fantasy-alt']() + '</div>');
    },
    replay(ctx) {
      BLK.registerReplay(ctx);
      ctx.live.story = (st) => { const ev = ctx.M.race.events.filter((e) => e.lap <= st.leaderLap && e.kind !== 'move').slice(-1)[0]; return '<b class="num">Lap ' + st.leaderLap + '/' + ctx.M.race.laps + '</b> ' + (ev ? BLK.esc(ev.text) : ''); };
      return '<div class="h-story" style="grid-area:ans" data-live="story"></div>' +
        panel('tower', 'Timing', '<span data-live="flag"></span>', '<div data-live="tower"></div>', 'a-dense') +
        panel('map', 'Track', '', C.chart('track', { h: ctx.mobile() ? 230 : 300, lap: ctx.replayLap }) + BLK.replayControls(ctx, 'rp-controls a-ctrl')) +
        panel('bump', 'The race as a river', 'numbered pins: SC, retirements, fastest lap', C.chart('bump', { h: 340, lap: ctx.replayLap, cursor: true, pins: true })) +
        panel('tyres', 'Tyres', 'S · M · H', C.chart('tyres', { h: 300, lap: ctx.replayLap })) +
        panel('tel', 'Fastest laps', ctx.M.telemetry.a + ' vs ' + ctx.M.telemetry.b, BLK.telemetry(ctx, 140));
    },
    intel(ctx) {
      const F = (c) => ctx.M.seasonForm.find((x) => x.code === c).races, a = F('PIA'), b = F('NOR');
      const ra = a.filter((r, i) => r.finish && (!b[i].finish || r.finish < b[i].finish)).length, qa = a.filter((r, i) => r.quali < b[i].quali).length;
      const pod = (c) => F(c).slice(-6).filter((r) => r.finish && r.finish <= 3).length;
      const best = ctx.M.drivers.map((d) => ({ c: d.code, f: F(d.code).filter((r) => r.finish) })).map((x) => ({ c: x.c, avg: x.f.reduce((p, r) => p + r.finish, 0) / x.f.length, dnf: 18 - x.f.length })).sort((x, y) => x.avg - y.avg)[0];
      return answers([['Races: PIA vs NOR', ra + '–' + (a.length - ra), 'finished ahead (mock)'], ['Qualifying', qa + '–' + (a.length - qa), 'PIA vs NOR'], ['Best average finish', best.c, best.avg.toFixed(1) + ' · ' + best.dnf + ' retirements'], ['Recent podiums', 'PIA ' + pod('PIA') + ' · NOR ' + pod('NOR'), 'last six rounds']]) +
        panel('h2h', 'Head to head', 'PIA vs NOR', BLK.h2h(ctx, 'PIA', 'NOR')) +
        panel('form', 'Season form', 'finishing position by round', BLK.formLines(ctx, ['PIA', 'NOR'], 240)) +
        panel('table', 'Field', 'last six races', '<div class="scroll-x">' + BLK.formTable(ctx, 22) + '</div>', 'a-dense');
    },
    lab(ctx) {
      BLK.registerLab(ctx, { n: 10 });
      ctx.live['lab-charts'] = () => ctx.labResult ? C.chart('futures', { n: 30, cols: ctx.mobile() ? 5 : 10, sim: ctx.labResult }) : '';
      return answers([['Scenario', 'B vs A', 'A is the established, frozen run'], ['Engine', 'Toy (playground)', 'the app runs real jobs with the same seed'], ['Candidates', 'Unpromoted', 'labelled on every output'], ['Re-runs', 'Live', 'on every slider change']]) +
        panel('params', 'Change the race', '', BLK.labSliders(ctx) + more(BLK.labToggles(ctx), 'Candidate engines')) +
        panel('diff', 'Who gains, who loses', '<span data-live="lab-meta"></span>', '<div data-live="lab-diff"></div>', 'a-dense') +
        panel('range', 'Thirty futures under B', '', '<div data-live="lab-charts"></div>');
    },
    eval(ctx) {
      const better = ctx.M.evaluation.filter((r) => r.rpsModel < r.rpsGrid).length, k = BLK.evalKpis(ctx);
      return answers([['Beat the grid', better + ' of ' + ctx.M.evaluation.length, 'rounds with lower RPS'], ['Skill vs grid', k[2][1], 'lower error than copying the grid'], ['Calibration', 'Slightly over-confident', 'above 60% (mock)'], ['Scored', k[3][1], 'rounds this season']]) +
        panel('rps', 'Accuracy by round', 'lower is better · grey = grid order', C.chart('paired', { h: 240 })) +
        panel('cal', 'Calibration · top 3', 'dot size = forecasts', C.chart('calib', { h: 240 })) +
        panel('table', 'Round by round', '', '<div class="scroll-x a-scroll">' + BLK.evalTable(ctx) + '</div>', 'a-dense');
    }
  };

  window.CONCEPTS.h = { name: 'H · Recommended hybrid', render(screen, ctx) { return shell(ctx, screens[screen](ctx)); } };
})();
