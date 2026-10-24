/* Concept D: Grid (Modern Consumer Sports App).
   Light, card-based and mobile-first. Each card leads with one plain-language
   answer; the statistics sit behind "Show the maths". */
(function () {
  'use strict';
  const card = (body, cls) => '<section class="d-card ' + (cls || '') + '">' + body + '</section>';
  const maths = (body, label) => '<details class="d-maths"><summary>' + (label || 'Show the maths') + '</summary><div class="d-maths-in">' + body + '</div></details>';
  const icons = { hub: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z', predict: 'M4 19V9m6 10V5m6 14v-7m4 7H2', fantasy: 'M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.5 6.7 19.4l1.2-6L3.4 9.3l6-.7z', replay: 'M8 5v14l11-7z', intel: 'M8 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm8 2a3 3 0 1 0 0-6M2 21c0-3.3 2.7-6 6-6s6 2.7 6 6m2-6c2.8 0 5 2.2 5 5', lab: 'M9 3h6M10 3v6L4 19a1.5 1.5 0 0 0 1.3 2h13.4a1.5 1.5 0 0 0 1.3-2L14 9V3', eval: 'M20 6L9 17l-5-5' };
  const icon = (k) => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + icons[k] + '"/></svg>';

  function shell(ctx, title, sub, inner) {
    const labels = { hub: 'Home', predict: 'Predict', fantasy: 'Fantasy', replay: 'Replay', intel: 'Drivers', lab: 'What-if', eval: 'Accuracy' };
    return '<div class="d-shell"><nav class="d-rail" aria-label="Main"><div class="d-logo"><span>RW</span></div>' + ctx.SCREENS.map(([k]) => '<a href="?c=d&s=' + k + '"' + (k === ctx.screen ? ' aria-current="page"' : '') + ' class="d-tab d-tab-' + k + '">' + icon(k) + '<span>' + labels[k] + '</span></a>').join('') + '</nav>' +
      '<main class="d-main"><header class="d-head"><div><p class="d-eyebrow">' + ctx.M.weekend.event + ' · Round ' + ctx.M.weekend.round + '</p><h1>' + title + '</h1>' + (sub ? '<p class="d-sub">' + sub + '</p>' : '') + '</div>' + ctx.mockTag + '</header>' + inner + '</main></div>';
  }
  function pick(ctx, s, big) {
    const d = C.team(s.code), oneIn = Math.max(1, Math.round(1 / Math.max(s.win, 0.001)));
    return '<article class="d-pick' + (big ? ' big' : '') + '" data-driver="' + s.code + '" tabindex="0" style="--team:' + d.colour + '"><div class="d-avatar"><span class="num">' + d.number + '</span></div><div class="d-pick-txt"><h3>' + d.name + '</h3><p class="muted">' + d.teamName + '</p>' +
      (big ? '<p class="d-lede">Wins about <b>1 in ' + oneIn + '</b> simulated races, and usually finishes <b>P' + Math.round(s.p25) + ' to P' + Math.round(s.p75) + '</b>.</p>' : '<p class="d-range">Usually P' + Math.round(s.p25) + '–' + Math.round(s.p75) + '</p>') + '</div><div class="d-pct"><b class="num">' + C.pct(s.win, 0) + '</b><span>win</span></div></article>';
  }
  function segmented(name, tabs) {
    return '<div class="d-seg" role="tablist">' + tabs.map(([k, label], i) => '<input type="radio" name="' + name + '" id="' + name + k + '"' + (i ? '' : ' checked') + '><label for="' + name + k + '">' + label + '</label>').join('') + '</div><div class="d-seg-panels">' + tabs.map(([k, , body]) => '<div class="d-seg-panel d-seg-' + k + '">' + body + '</div>').join('') + '</div>';
  }
  function twoSided(a, b, rows) {
    return '<div class="d-vs-rows">' + rows.map(([label, x, y, low, fmt]) => {
      const tot = (x + y) || 1, ax = low ? y / tot : x / tot, bx = low ? x / tot : y / tot;
      return '<div class="d-vs-row"><span class="num' + (ax > bx ? ' win' : '') + '">' + fmt(x) + '</span><div class="d-vs-bar"><i style="width:' + (ax * 100) + '%;background:' + C.team(a).colour + '"></i><i style="width:' + (bx * 100) + '%;background:' + C.team(b).colour + '"></i></div><span class="num' + (bx > ax ? ' win' : '') + '">' + fmt(y) + '</span><small>' + label + '</small></div>';
    }).join('') + '</div>';
  }

  const screens = {
    hub(ctx) {
      const W = ctx.M.weekend, s = ctx.sum;
      return shell(ctx, 'Race weekend', 'Austin · ' + W.laps + ' laps · Qualifying today at 21:00',
        '<div class="d-grid">' + card('<p class="d-kicker">Our pick</p>' + pick(ctx, s[0], true) + '<div class="d-mini">' + s.slice(1, 4).map((x) => pick(ctx, x)).join('') + '</div>' + maths(C.chart('range', { h: 300, rows: ctx.byAvg.slice(0, 10), teamColour: true }) + '<p class="cap muted">Line: 80% of simulated finishes. Bar: middle half. Dot: median. From ' + W.forecast.sims.toLocaleString() + ' simulated races after ' + W.forecast.session + '.</p>'), 'd-span2') +
        card('<p class="d-kicker">Next up</p><div class="d-count"><b class="num">6h 35m</b><span>until qualifying</span></div>' + BLK.schedule(ctx, 'd-sched')) +
        card('<p class="d-kicker">Quick actions</p><div class="d-actions"><a href="?c=d&s=fantasy">' + icon('fantasy') + '<b>Build my team</b><span>Best line-up under $100m</span></a><a href="?c=d&s=intel">' + icon('intel') + '<b>Compare drivers</b><span>Head-to-head this season</span></a><a href="?c=d&s=replay">' + icon('replay') + '<b>Watch a replay</b><span>Lap by lap, with tyres</span></a></div>') +
        card('<p class="d-kicker">Conditions</p><div class="d-chips"><span>☀︎ ' + W.weather.air + '°C air</span><span>' + W.weather.track + '°C track</span><span>' + Math.round(W.weather.rainChance * 100) + '% rain</span><span>' + W.weather.wind + ' km/h wind</span></div><p class="cap muted">Weather is shown for context. It does not change these predictions yet.</p>') +
        card('<p class="d-kicker">Title race</p>' + C.chart('interval', { h: 200, rows: ctx.M.championship.slice(0, 4) }), 'd-span2') + '</div>');
    },
    predict(ctx) {
      const tabs = [['win', 'Win', C.bars(ctx.sum, { key: 'win', n: 8 })], ['podium', 'Podium', C.bars(ctx.sum.slice().sort((a, b) => b.podium - a.podium), { key: 'podium', n: 8, max: 1 })], ['points', 'Points', C.bars(ctx.sum.slice().sort((a, b) => b.points - a.points), { key: 'points', n: 10, max: 1, fmt: (v) => C.pct(v, 0) })]];
      return shell(ctx, 'Who wins on Sunday?', 'Based on ' + ctx.M.base.sims.toLocaleString() + ' simulated races. Tap a driver to follow them on every chart.',
        '<div class="d-grid">' + card(segmented('p', tabs), 'd-span2') +
        card('<p class="d-kicker">How sure are we? · ' + ctx.sum[0].code + '</p>' + C.chart('dots', { h: 140, code: ctx.sum[0].code }) + '<p class="cap muted">Each dot is 2 in 100 simulated races. Spread-out dots mean more uncertainty.</p>') +
        card('<p class="d-kicker">Driver by driver</p><div class="d-list">' + ctx.byAvg.slice(0, 8).map((s) => pick(ctx, s)).join('') + '</div>' + maths('<div class="scroll-x">' + C.chart('heat', { rows: ctx.byAvg.slice(0, 10), upto: 10 }) + '</div>', 'Every position, in detail'), 'd-span2') +
        card('<p class="d-kicker">Qualifying vs race</p>' + BLK.metricsHtml(ctx.byAvg.slice(0, 4).map((s) => [s.code + ' grid → finish', 'P' + Math.round(s.gridMedian) + ' → P' + s.avgFinish.toFixed(1)])) + '<p class="cap muted">Typical starting slot from simulated qualifying, then average finish.</p>') + '</div>');
    },
    fantasy(ctx) {
      BLK.registerFantasy(ctx, { alts: 3, metrics: (items) => '<div class="d-teamsum"><div><b class="num">' + items[0][1] + '</b><span>expected points</span></div><div><span>Usually between</span><b class="num">' + items[1][1] + '</b></div><div class="d-cap"><span>Cost cap</span><div class="d-capbar"><i style="width:' + (parseFloat(items[2][1].slice(1)) / ctx.Fantasy.state.budget * 100) + '%"></i></div><span class="num">' + items[2][1] + ' of $' + ctx.Fantasy.state.budget + 'm</span></div></div>' });
      return shell(ctx, 'Build your team', 'Five drivers and two constructors. We pick the highest expected score; you can lock or leave out anyone.',
        '<div class="d-grid">' + card('<div data-live="fantasy-metrics">' + ctx.live['fantasy-metrics']() + '</div><div data-live="fantasy-team">' + ctx.live['fantasy-team']() + '</div>' + maths('<div data-live="fantasy-dist">' + ctx.live['fantasy-dist']() + '</div><p class="cap muted">Team score across simulated races. The darker bars are the usual range (P10–P90).</p>', 'How risky is this team?'), 'd-span2 d-sticky') +
        card('<div class="d-row"><p class="d-kicker">Choose players</p><button type="button" class="d-link" data-act="reset-picks">Reset</button></div><p class="cap muted">Tap once to lock in, again to leave out, again to let us choose.</p><div data-live="fantasy-chips">' + BLK.fantasyChips(ctx) + '</div>') +
        card('<p class="d-kicker">Good value</p>' + BLK.valueScatter(ctx, 260) + '<p class="cap muted">Drivers above the dashed line give the most points for their price.</p>', 'd-span2') +
        card('<p class="d-kicker">Close alternatives</p><div class="scroll-x" data-live="fantasy-alt">' + ctx.live['fantasy-alt']() + '</div>') + '</div>');
    },
    replay(ctx) {
      BLK.registerReplay(ctx, { n: 5, compact: true });
      ctx.live.caption = (st) => {
        const ev = ctx.M.race.events.filter((e) => e.lap <= st.leaderLap).slice(-1)[0];
        return '<p class="d-lap">Lap <b class="num">' + st.leaderLap + '</b> of ' + ctx.M.race.laps + (st.sc ? ' · <span class="d-sc">Safety car</span>' : '') + '</p><p class="d-what">' + (ev ? BLK.esc(ev.text) : '') + '</p>';
      };
      return shell(ctx, 'Race replay', 'Mock race at a schematic circuit. Drag the slider, or press Space to play.',
        '<div class="d-grid">' + card('<div class="d-replay"><div class="d-replay-map">' + C.chart('track', { h: ctx.mobile() ? 230 : 380, lap: ctx.replayLap, labelTop: 3, noLabel: true }) + '</div><div class="d-replay-side"><div data-live="caption"></div><div data-live="tower"></div></div></div>' + BLK.replayControls(ctx, 'rp-controls d-ctrl'), 'd-span3') +
        card('<p class="d-kicker">The race in one chart</p>' + C.chart('bump', { h: 280, lap: ctx.replayLap, cursor: true, showN: 10, focus: ctx.M.race.startOrder.slice(0, 4) }) + '<p class="cap muted">Top four starters highlighted. Tap any line to follow a driver.</p>', 'd-span2') +
        card('<p class="d-kicker">Key moments</p><div data-live="events" class="d-scroll"></div>') +
        card(maths(C.chart('tyres', { h: 330, lap: ctx.replayLap }), 'Tyre strategy for every driver') + maths(BLK.telemetry(ctx, 160), 'Fastest-lap telemetry'), 'd-span3') + '</div>');
    },
    intel(ctx) {
      const a = 'PIA', b = 'NOR', fa = ctx.M.seasonForm.find((x) => x.code === a).races, fb = ctx.M.seasonForm.find((x) => x.code === b).races;
      const avg = (arr) => arr.reduce((x, y) => x + y, 0) / arr.length;
      const qa = fa.filter((r, i) => r.quali < fb[i].quali).length, ra = fa.filter((r, i) => r.finish && (!fb[i].finish || r.finish < fb[i].finish)).length;
      return shell(ctx, 'Piastri vs Norris', 'McLaren team-mates, 18 races into 2026.',
        '<div class="d-grid">' + card('<div class="d-vs-head">' + [a, b].map((c) => { const d = C.team(c); return '<div class="d-vs-who" data-driver="' + c + '" style="--team:' + d.colour + '"><div class="d-avatar"><span class="num">' + d.number + '</span></div><b>' + d.name + '</b></div>'; }).join('<span class="d-vs">VS</span>') + '</div>' +
          twoSided(a, b, [['Out-qualified team-mate', qa, fa.length - qa, false, (v) => v], ['Finished ahead', ra, fa.length - ra, false, (v) => v], ['Average grid slot', avg(fa.map((r) => r.quali)), avg(fb.map((r) => r.quali)), true, (v) => v.toFixed(1)], ['Retirements', fa.filter((r) => !r.finish).length, fb.filter((r) => !r.finish).length, true, (v) => v], ['Win chance this weekend', ctx.M.base.summary[C.team(a).idx].win * 100, ctx.M.base.summary[C.team(b).idx].win * 100, false, (v) => v.toFixed(0) + '%']]), 'd-span2') +
        card('<p class="d-kicker">Recent form</p>' + BLK.formLines(ctx, [a, b], 220)) +
        card('<p class="d-kicker">Whole grid</p><div class="scroll-x">' + BLK.formTable(ctx, 10) + '</div>', 'd-span3') + '</div>');
    },
    lab(ctx) {
      BLK.registerLab(ctx, { n: 8, rangeH: 260 });
      ctx.live['lab-diff'] = ((orig) => () => {
        const r = ctx.labResult; if (!r) return '';
        const rows = ctx.M.base.summary.map((b, i) => ({ code: b.code, a: b.win, b: r.summary[i].win })).sort((x, y) => Math.abs(y.b - y.a) - Math.abs(x.b - x.a)).slice(0, 6);
        return '<ul class="d-movers">' + rows.map((x) => '<li data-driver="' + x.code + '">' + BLK.sw(x.code) + '<b>' + C.team(x.code).name + '</b><span class="num muted">' + C.pct(x.a, 0) + ' → ' + C.pct(x.b, 0) + '</span><span class="d-delta ' + (x.b >= x.a ? 'up' : 'down') + '">' + (x.b >= x.a ? '▲' : '▼') + ' ' + Math.abs((x.b - x.a) * 100).toFixed(1) + '</span></li>').join('') + '</ul>';
      })(ctx.live['lab-diff']);
      return shell(ctx, 'What if…?', 'Move a slider to change the race. We re-run the simulation and show who gains.',
        '<div class="d-grid">' + card(BLK.labSliders(ctx) + maths(BLK.labToggles(ctx), 'Experimental engines')) +
        card('<p class="d-kicker">Biggest movers · win chance</p><p class="cap muted" data-live="lab-meta"></p><div data-live="lab-diff"></div>', 'd-span2') +
        card('<p class="d-kicker">Likely finish in your scenario</p><div data-live="lab-charts"></div>', 'd-span3') + '</div>');
    },
    eval(ctx) {
      const better = ctx.M.evaluation.filter((r) => r.rpsModel < r.rpsGrid).length;
      return shell(ctx, 'How accurate are we?', 'Every 2026 forecast, checked against the real result (mock).',
        '<div class="d-grid">' + card('<div class="d-hero-stat"><b class="num">' + better + '<small>/' + ctx.M.evaluation.length + '</small></b><p>races where our forecast beat simply guessing the grid order.</p></div>' + BLK.metricsHtml(BLK.evalKpis(ctx).slice(0, 3)), 'd-span3') +
        card('<p class="d-kicker">Race by race · lower is better</p>' + C.chart('paired', { h: 240 }) + '<p class="cap muted">Coloured: our model. Grey: grid order.</p>', 'd-span2') +
        card('<p class="d-kicker">Do our percentages mean what they say?</p>' + C.chart('calib', { h: 240 }) + maths('<p class="cap">Each dot groups forecasts with a similar top-3 chance. If dots sit on the dashed line, a 30% forecast happened about 30% of the time.</p>', 'How to read this')) + '</div>');
    }
  };

  window.CONCEPTS.d = { name: 'D · Grid', render(screen, ctx) { return screens[screen](ctx); } };
})();
