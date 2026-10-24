/* Content blocks shared by the five concepts. Concepts decide layout, chrome,
   copy tone and styling; these only turn mock data into markup. */
(function () {
  'use strict';
  const esc = (s) => C.esc(s);
  const pct = (v, d) => C.pct(v, d == null ? 1 : d);
  const pp = (v) => (v >= 0 ? '+' : '−') + Math.abs(v * 100).toFixed(1) + ' pp';
  const signed = (v, d) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(d == null ? 1 : d);
  const sw = (code) => '<i class="sw" style="background:' + C.team(code).colour + '"></i>';
  const tyre = (c) => '<span class="tyre-chip tyre-' + c + '" title="' + ({ S: 'Soft', M: 'Medium', H: 'Hard' })[c] + '">' + c + '</span>';

  const BLK = {
    esc, pct, pp, signed, sw, tyre,

    schedule(ctx, cls) {
      return '<ol class="' + (cls || 'sched') + '">' + ctx.M.weekend.sessions.map((s) =>
        '<li class="s-' + s.state + '"><span class="s-code">' + s.code + '</span><span class="s-name">' + s.name + '</span><span class="s-when num">' + s.day + ' · ' + s.time + '</span><span class="s-state">' + ({ done: 'Done', next: 'Next', upcoming: '' })[s.state] + '</span></li>').join('') + '</ol>';
    },

    driverTable(ctx, opts) {
      const o = Object.assign({ rows: ctx.byAvg, n: 22, cols: ['win', 'podium', 'points', 'dnf', 'range'], rank: true }, opts);
      const head = { win: 'Win', podium: 'Podium', points: 'Points', dnf: 'DNF', range: 'Middle half', avg: 'Avg', fantasy: 'Fantasy', delta: 'Δ win vs B' };
      let t = '<table class="dt"><thead><tr>' + (o.rank ? '<th class="r">#</th>' : '') + '<th>Driver</th>' + o.cols.map((c) => '<th class="' + (c === 'range' ? '' : 'r') + '">' + head[c] + '</th>').join('') + '</tr></thead><tbody>';
      o.rows.slice(0, o.n).forEach((s, i) => {
        const d = C.team(s.code);
        t += '<tr data-driver="' + s.code + '" tabindex="0">' + (o.rank ? '<td class="num r">' + (i + 1) + '</td>' : '') + '<td>' + sw(s.code) + '<b>' + s.code + '</b> <span class="muted">' + esc(d.teamName) + '</span></td>';
        o.cols.forEach((c) => {
          if (c === 'range') t += '<td><span class="mini-range" aria-label="P' + Math.round(s.p25) + ' to P' + Math.round(s.p75) + '"><i style="left:' + ((s.p25 - 1) / 21 * 100) + '%;width:' + Math.max(3, (s.p75 - s.p25) / 21 * 100) + '%"></i><b style="left:' + ((s.p50 - 1) / 21 * 100) + '%"></b></span> <span class="num muted">P' + Math.round(s.p25) + '–' + Math.round(s.p75) + '</span></td>';
          else if (c === 'avg') t += '<td class="num r">' + s.avgFinish.toFixed(1) + '</td>';
          else if (c === 'fantasy') t += '<td class="num r">' + s.fantasyMean.toFixed(1) + '</td>';
          else if (c === 'delta') { const v = ctx.cand[s.code].win - s.win; t += '<td class="num r ' + (Math.abs(v) < 0.005 ? 'muted' : v > 0 ? 'pos' : 'neg') + '">' + pp(v) + '</td>'; }
          else t += '<td class="num r">' + pct(s[c], s[c] < 0.1 && c !== 'dnf' ? 1 : 0) + '</td>';
        });
        t += '</tr>';
      });
      return t + '</tbody></table>';
    },

    // ----- Fantasy -----
    fantasyChips(ctx) {
      const F = ctx.Fantasy, lock = F.state.lock;
      const chip = (a, kind) => { const st = lock[a.code]; return '<button type="button" class="asset' + (st ? ' asset-' + st : '') + '" data-act="asset" data-code="' + a.code + '" aria-pressed="' + (st === 'in') + '" title="' + (st === 'in' ? 'Locked in' : st === 'out' ? 'Left out' : 'Picker decides') + '">' + (kind === 'd' ? sw(a.code) : '') + '<b>' + a.code + '</b><span class="num">$' + a.price.toFixed(1) + 'm</span></button>'; };
      return '<div class="assets" role="group" aria-label="Drivers">' + F.D.slice().sort((a, b) => b.price - a.price).map((a) => chip(a, 'd')).join('') + '</div>' +
        '<div class="assets" role="group" aria-label="Constructors">' + F.T.slice().sort((a, b) => b.price - a.price).map((a) => chip(a, 't')).join('') + '</div>';
    },
    registerFantasy(ctx, opts) {
      const F = ctx.Fantasy, o = Object.assign({ alts: 5 }, opts);
      const best = () => F.pick(F.state)[0];
      ctx.live['fantasy-team'] = () => {
        const t = best();
        if (!t) return '<p class="empty">No team fits these locks and this budget. Unlock an asset or raise the budget.</p>';
        const rows = t.drivers.map((c) => ({ c, kind: 'Driver', price: C.team(c).price, pts: F.D.find((d) => d.code === c).pts * (c === t.boost ? 2 : 1) }))
          .concat(t.cons.map((c) => ({ c, kind: 'Constructor', price: ctx.M.teamById[c].price, pts: F.T.find((x) => x.code === c).pts })));
        return '<table class="dt"><thead><tr><th>Asset</th><th>Type</th><th class="r">Price</th><th class="r">Expected</th></tr></thead><tbody>' + rows.map((r) =>
          '<tr' + (r.kind === 'Driver' ? ' data-driver="' + r.c + '"' : '') + '><td>' + (r.kind === 'Driver' ? sw(r.c) : '') + '<b>' + r.c + '</b>' + (r.c === t.boost ? ' <span class="boost">2×</span>' : '') + '</td><td class="muted">' + r.kind + '</td><td class="num r">$' + r.price.toFixed(1) + 'm</td><td class="num r">' + r.pts.toFixed(1) + '</td></tr>').join('') + '</tbody></table>';
      };
      ctx.live['fantasy-metrics'] = () => {
        const t = best(); if (!t) return '';
        const dist = F.distribution(t);
        return (opts && opts.metrics || BLK.metricsHtml)([
          ['Expected points', dist.mean.toFixed(1)], ['Likely range (P10–P90)', Math.round(dist.p10) + ' to ' + Math.round(dist.p90)],
          ['Cost', '$' + t.cost.toFixed(1) + 'm'], ['Budget left', '$' + (F.state.budget - t.cost).toFixed(1) + 'm']]);
      };
      ctx.live['fantasy-dist'] = () => {
        const t = best(); if (!t) return '';
        const dist = F.distribution(t);
        return C.chart('hist', { h: o.histH || 150, values: dist.values, p10: dist.p10, p90: dist.p90, mean: dist.mean });
      };
      ctx.live['fantasy-alt'] = () => {
        const all = F.pick(F.state), top = all[0];
        return '<table class="dt"><thead><tr><th class="r">#</th><th>Drivers</th><th>Teams</th><th class="r">Cost</th><th class="r">Expected</th><th class="r">Behind</th></tr></thead><tbody>' +
          all.slice(1, 1 + o.alts).map((t, i) => '<tr><td class="num r">' + (i + 2) + '</td><td>' + t.drivers.map((c) => c === t.boost ? c + ' (2×)' : c).join(', ') + '</td><td>' + t.cons.join(', ') + '</td><td class="num r">$' + t.cost.toFixed(1) + 'm</td><td class="num r">' + t.pts.toFixed(1) + '</td><td class="num r neg">' + signed(t.pts - top.pts) + '</td></tr>').join('') + '</tbody></table>';
      };
      ctx.live['fantasy-chips'] = () => BLK.fantasyChips(ctx);
    },
    metricsHtml(items) {
      return '<div class="metrics">' + items.map(([k, v]) => '<div class="metric"><span>' + k + '</span><strong class="num">' + v + '</strong></div>').join('') + '</div>';
    },
    riskReward(ctx, h, extra) {
      const pts = ctx.M.drivers.map((d) => { const s = ctx.M.base.summary[d.idx]; return { x: s.fantasySd, y: s.fantasyMean, size: d.price, label: d.code, colour: d.colour, title: d.code + ': expected ' + s.fantasyMean.toFixed(1) + ', spread ' + s.fantasySd.toFixed(1) + ', $' + d.price + 'm' }; });
      return C.chart('scatter', Object.assign({ h, points: pts, xLabel: 'Risk: spread of outcomes (sd, pts) →', yLabel: '↑ Expected fantasy points', sizeKey: true, labelAbove: 4, aria: 'Fantasy risk against reward. Bubble size is price.' }, extra));
    },
    valueScatter(ctx, h) {
      const pts = ctx.M.drivers.map((d) => { const s = ctx.M.base.summary[d.idx]; return { x: d.price, y: s.fantasyMean, label: d.code, colour: d.colour, size: 4 }; });
      return C.chart('scatter', { h, points: pts, xLabel: 'Price ($m) →', yLabel: '↑ Expected points', frontier: true, labelAbove: 3, aria: 'Expected points against price, with the best-value frontier' });
    },

    // ----- Replay -----
    registerReplay(ctx, opts) {
      const o = Object.assign({ n: 22, compact: false }, opts);
      ctx.live.tower = (st) => {
        const rows = st.order.slice(0, o.n).concat(o.n >= 22 ? st.out : []);
        return '<ol class="tower">' + rows.map((r) => '<li data-driver="' + r.code + '" tabindex="0" class="' + (r.out ? 'is-out' : '') + '"><span class="pos num">' + (r.pos || '–') + '</span>' + sw(r.code) + '<b>' + r.code + '</b><span class="gap num">' + r.gap + '</span>' + (o.compact ? '' : '<span class="last num">' + (r.last ? ctx.M.fmtLap(r.last) : '') + '</span>') + tyre(r.compound) + (o.compact ? '' : '<span class="age num">' + Math.max(0, r.tyreAge) + '</span>') + '</li>').join('') + '</ol>';
      };
      ctx.live.lap = (st) => '<span class="num">' + st.leaderLap + '</span><span class="of">/' + ctx.M.race.laps + '</span>';
      ctx.live.flag = (st) => st.sc ? '<span class="flag flag-sc">Safety car</span>' : '<span class="flag flag-green">Green</span>';
      ctx.live.events = (st) => {
        const lap = st.leaderLap;
        return '<ol class="events">' + ctx.M.race.events.filter((e) => o.allEvents || e.kind !== 'move' || e.lap <= lap + 3).map((e) =>
          '<li class="ev ev-' + e.kind + (e.lap <= lap ? ' is-past' : '') + (e.lap === lap ? ' is-now' : '') + '"' + (e.code ? ' data-driver="' + e.code + '"' : '') + '><button type="button" data-act="jump" data-lap="' + Math.max(0, e.lap - 0.5) + '" class="ev-lap num">L' + e.lap + '</button><span>' + esc(e.text) + '</span></li>').join('') + '</ol>';
      };
    },
    replayControls(ctx, cls) {
      return '<div class="' + (cls || 'rp-controls') + '"><button type="button" data-act="step" data-by="-1" aria-label="Previous lap">◀︎</button><button type="button" data-act="play" aria-pressed="false" class="play">Play</button><button type="button" data-act="step" data-by="1" aria-label="Next lap">▶︎</button>' +
        '<label class="scrub"><span class="sr">Race position in laps</span><input type="range" min="0" max="' + ctx.M.race.laps + '" step="0.05" value="' + ctx.replayLap + '" data-scrub aria-label="Replay lap"></label></div>';
    },
    telemetry(ctx, h, opts) {
      const T = ctx.M.telemetry, o = opts || {};
      const ca = C.team(T.a).colour, cb = C.team(T.b).colour;
      return '<div class="tel">' +
        C.chart('lines', { h: h, aria: 'Speed by distance, ' + T.a + ' and ' + T.b + ' fastest laps', series: [{ values: T.traceA.map((p) => ({ x: p.d, y: p.speed })), colour: ca, code: T.a }, { values: T.traceB.map((p) => ({ x: p.d, y: p.speed })), colour: cb, code: T.b, dashed: true }], yTicks: [100, 200, 300], xTicks: [0, 1000, 2000, 3000, 4000, 5000], xFmt: (v) => (v / 1000) + ' km', yFmt: (v) => v + '' }) +
        C.chart('lines', { h: o.deltaH || Math.round(h * 0.5), aria: 'Time delta along the lap', series: [{ values: T.delta.map((p) => ({ x: p.d, y: p.delta })), colour: 'var(--c-fg)' }], symmetric: true, area: true, yTicks: [0], yFmt: () => '0', hideX: true }) +
        '<p class="cap muted">Speed (km/h) and delta (s). Above zero means ' + T.a + ' is ahead. Dashed line is ' + T.b + '.</p></div>';
    },

    // ----- Drivers -----
    h2h(ctx, a, b) {
      const fa = ctx.M.seasonForm.find((x) => x.code === a).races, fb = ctx.M.seasonForm.find((x) => x.code === b).races;
      const qa = fa.filter((r, i) => r.quali < fb[i].quali).length, ra = fa.filter((r, i) => r.finish && (!fb[i].finish || r.finish < fb[i].finish)).length;
      const avg = (arr) => arr.filter((v) => v != null).reduce((x, y) => x + y, 0) / arr.filter((v) => v != null).length;
      const rows = [
        ['Qualifying head-to-head', qa, fa.length - qa, 'n'], ['Race head-to-head', ra, fa.length - ra, 'n'],
        ['Average grid', avg(fa.map((r) => r.quali)), avg(fb.map((r) => r.quali)), 'low'], ['Average finish', avg(fa.map((r) => r.finish)), avg(fb.map((r) => r.finish)), 'low'],
        ['Retirements', fa.filter((r) => !r.finish).length, fb.filter((r) => !r.finish).length, 'low'],
        ['Win chance this race', ctx.M.base.summary[C.team(a).idx].win, ctx.M.base.summary[C.team(b).idx].win, 'pct']
      ];
      return '<table class="h2h"><thead><tr><th class="r" data-driver="' + a + '">' + sw(a) + a + '</th><th></th><th data-driver="' + b + '">' + sw(b) + b + '</th></tr></thead><tbody>' + rows.map(([k, x, y, kind]) => {
        const better = kind === 'low' ? (x < y ? 'a' : x > y ? 'b' : '') : (x > y ? 'a' : x < y ? 'b' : '');
        const f = (v) => kind === 'pct' ? pct(v) : Number.isInteger(v) ? v : v.toFixed(1);
        return '<tr><td class="num r' + (better === 'a' ? ' win' : '') + '">' + f(x) + '</td><th>' + k + '</th><td class="num' + (better === 'b' ? ' win' : '') + '">' + f(y) + '</td></tr>';
      }).join('') + '</tbody></table>';
    },
    formLines(ctx, codes, h) {
      return C.chart('lines', { h, aria: 'Finishing position by round', yMin: 22, yMax: 1, yTicks: [1, 5, 10, 15, 20], yFmt: (v) => 'P' + v, xTicks: [1, 5, 10, 15, 18], xFmt: (v) => 'R' + v, endLabels: true,
        series: codes.map((c) => ({ code: c, label: c, colour: C.team(c).colour, dashed: C.team(c).second, values: ctx.M.seasonForm.find((x) => x.code === c).races.map((r) => ({ x: r.round, y: r.finish })) })) });
    },
    formTable(ctx, n) {
      return '<table class="dt form"><thead><tr><th>Driver</th><th>Last 6 finishes</th><th class="r">Avg grid</th><th class="r">Avg finish</th><th class="r">DNF</th><th>Pace trend</th></tr></thead><tbody>' +
        ctx.byAvg.slice(0, n || 22).map((s) => {
          const f = ctx.M.seasonForm.find((x) => x.code === s.code).races;
          const last = f.slice(-6), g = f.reduce((a, r) => a + r.quali, 0) / f.length, fin = f.filter((r) => r.finish);
          return '<tr data-driver="' + s.code + '" tabindex="0"><td>' + sw(s.code) + '<b>' + s.code + '</b></td><td><span class="cells">' + last.map((r) => '<i class="' + (r.finish == null ? 'c-dnf' : r.finish <= 3 ? 'c-pod' : r.finish <= 10 ? 'c-pts' : 'c-out') + '" title="R' + r.round + ': ' + (r.finish ? 'P' + r.finish : 'DNF') + '">' + (r.finish || '×') + '</i>').join('') + '</span></td><td class="num r">' + g.toFixed(1) + '</td><td class="num r">' + (fin.reduce((a, r) => a + r.finish, 0) / fin.length).toFixed(1) + '</td><td class="num r">' + (f.length - fin.length) + '</td><td style="width:90px">' + C.chart('spark', { h: 22, values: f.map((r) => r.paceDelta), invert: false, colour: C.team(s.code).colour, aria: s.code + ' pace deficit trend' }) + '</td></tr>';
        }).join('') + '</tbody></table>';
    },

    // ----- Simulation lab -----
    labSliders(ctx) {
      const s = ctx.labState;
      const row = (key, label, min, max, step, fmt, hint) => '<label class="param"><span class="param-head"><span>' + label + '</span><output class="num" data-out="' + key + '">' + (fmt === 'pct' ? Math.round(s[key] * 100) + '%' : s[key].toFixed(2)) + '</output></span><input type="range" min="' + min + '" max="' + max + '" step="' + step + '" value="' + s[key] + '" data-param="' + key + '" data-fmt="' + fmt + '"><small class="muted">' + hint + '</small></label>';
      return row('driverNoise', 'Race-day randomness', 0.1, 0.6, 0.01, 'n', 'Toy noise per driver. Higher spreads the field.') +
        row('safetyCar', 'Safety-car chance', 0, 0.9, 0.01, 'pct', 'Only used when the safety-car candidate is on.') +
        row('gridWeight', 'Grid influence', 0, 0.8, 0.01, 'n', 'How much starting position carries into the result.') +
        row('dnfRate', 'Retirement rate', 0, 0.15, 0.005, 'pct', 'Per-driver chance of not finishing.');
    },
    labToggles(ctx) {
      return '<div class="toggles">' + ctx.M.lab.candidates.map((c) => '<button type="button" class="tog" data-act="toggle" data-key="' + c.key + '" aria-pressed="' + ctx.labState.toggles[c.key] + '"><span class="tog-dot"></span>' + c.label + '</button>').join('') + '</div>';
    },
    registerLab(ctx, opts) {
      const o = Object.assign({ n: 10 }, opts);
      ctx.live['lab-diff'] = () => {
        const r = ctx.labResult; if (!r) return '';
        const rows = ctx.M.base.summary.map((b, i) => ({ code: b.code, a: b.win, b: r.summary[i].win, pa: b.podium, pb: r.summary[i].podium })).sort((x, y) => y.b - x.b).slice(0, o.n);
        return '<table class="dt"><thead><tr><th>Driver</th><th class="r">Win A</th><th class="r">Win B</th><th class="r">Δ</th><th class="r">Podium B</th><th class="r">Δ</th></tr></thead><tbody>' + rows.map((x) =>
          '<tr data-driver="' + x.code + '"><td>' + sw(x.code) + '<b>' + x.code + '</b></td><td class="num r muted">' + pct(x.a) + '</td><td class="num r">' + pct(x.b) + '</td><td class="num r ' + (Math.abs(x.b - x.a) < 0.005 ? 'muted' : x.b > x.a ? 'pos' : 'neg') + '">' + pp(x.b - x.a) + '</td><td class="num r">' + pct(x.pb) + '</td><td class="num r ' + (Math.abs(x.pb - x.pa) < 0.005 ? 'muted' : x.pb > x.pa ? 'pos' : 'neg') + '">' + pp(x.pb - x.pa) + '</td></tr>').join('') + '</tbody></table>';
      };
      ctx.live['lab-charts'] = () => {
        const r = ctx.labResult; if (!r) return '';
        const rows = r.summary.slice().sort((a, b) => a.avgFinish - b.avgFinish).slice(0, o.n);
        return C.chart('range', { h: o.rangeH || 260, rows, teamColour: true });
      };
      ctx.live['lab-meta'] = () => { const r = ctx.labResult; return r ? '<span class="num">' + r.sims.toLocaleString() + '</span> toy races · safety car in <span class="num">' + pct(r.safetyCarShare, 0) + '</span>' : ''; };
    },

    // ----- Evaluation -----
    evalKpis(ctx) {
      const E = ctx.M.evaluation, m = E.reduce((a, r) => a + r.rpsModel, 0) / E.length, g = E.reduce((a, r) => a + r.rpsGrid, 0) / E.length;
      return [['Model RPS (mean)', m.toFixed(3)], ['Grid-order RPS', g.toFixed(3)], ['Skill vs grid', ((1 - m / g) * 100).toFixed(1) + '%'], ['Rounds scored', E.length + ' of 24']];
    },
    evalTable(ctx) {
      return '<table class="dt"><thead><tr><th class="r">R</th><th>Event</th><th class="r">Model RPS</th><th class="r">Grid RPS</th><th class="r">Better?</th><th class="r">Winner chance</th></tr></thead><tbody>' + ctx.M.evaluation.slice().reverse().map((r) =>
        '<tr><td class="num r">' + r.round + '</td><td>' + r.name + '</td><td class="num r">' + r.rpsModel.toFixed(3) + '</td><td class="num r muted">' + r.rpsGrid.toFixed(3) + '</td><td class="r ' + (r.rpsModel < r.rpsGrid ? 'pos' : 'neg') + '">' + (r.rpsModel < r.rpsGrid ? 'Yes' : 'No') + '</td><td class="num r">' + pct(r.winnerProb, 0) + '</td></tr>').join('') + '</tbody></table>';
    },

    nav(ctx, cls, labels) {
      return '<nav class="' + cls + '" aria-label="Workspaces">' + ctx.SCREENS.map(([k, label], i) => '<a href="?c=' + ctx.conceptId + '&s=' + k + '"' + (k === ctx.screen ? ' aria-current="page"' : '') + ' data-key="' + (i + 1) + '">' + (labels ? labels[k] : label) + '</a>').join('') + '</nav>';
    }
  };
  window.BLK = BLK;
  window.CONCEPTS = window.CONCEPTS || {};
})();
