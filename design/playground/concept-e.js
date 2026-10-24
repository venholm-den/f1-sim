/* Concept E: Raceline (Experimental Data Experience).
   Editorial and paper-toned. The weekend reads as a story in chapters, and
   uncertainty is shown as many possible races rather than one number. */
(function () {
  'use strict';
  const chapters = { hub: 'The weekend', predict: 'Fifty futures', fantasy: 'The portfolio', replay: 'The river', intel: 'Two drivers', lab: 'Bend the race', eval: 'Were we right?' };
  const note = (text) => '<aside class="e-note">' + text + '</aside>';
  const fig = (body, caption, notes) => '<figure class="e-fig"><div class="e-fig-main">' + body + (caption ? '<figcaption>' + caption + '</figcaption>' : '') + '</div><div class="e-notes">' + (notes || '') + '</div></figure>';

  function shell(ctx, num, title, lede, inner) {
    return '<div class="e-shell"><nav class="e-chapters" aria-label="Chapters"><p class="e-mast">Race<em>line</em></p><ol>' + ctx.SCREENS.map(([k], i) => '<li><a href="?c=e&s=' + k + '"' + (k === ctx.screen ? ' aria-current="page"' : '') + '><span class="num">' + String(i + 1).padStart(2, '0') + '</span>' + chapters[k] + '</a></li>').join('') + '</ol><p class="e-colophon">' + ctx.M.weekend.event + '<br>Round ' + ctx.M.weekend.round + ' · ' + ctx.M.weekend.year + '</p>' + ctx.mockTag + '</nav>' +
      '<article class="e-main"><header class="e-head"><p class="e-num num">Chapter ' + num + '</p><h1>' + title + '</h1><p class="e-lede">' + lede + '</p></header>' + inner + '</article></div>';
  }
  function dotRows(ctx, codes) {
    return '<div class="e-dotrows">' + codes.map((c) => '<div class="e-dotrow" data-driver="' + c + '"><span class="e-dname">' + C.team(c).name + '</span>' + C.chart('dots', { h: 110, code: c }) + '</div>').join('') + '</div>';
  }

  const screens = {
    hub(ctx) {
      const s = ctx.sum, W = ctx.M.weekend;
      return shell(ctx, '01', 'Four drivers, one Sunday', 'After Friday practice in Austin, the simulation can\'t separate the front of the grid. <b>' + C.team(s[0].code).name + '</b> wins ' + C.pct(s[0].win, 0) + ' of simulated races, and three others are within six points.',
        '<ol class="e-timeline">' + W.sessions.map((x) => '<li class="s-' + x.state + '"><span class="e-tdot"></span><b>' + x.name + '</b><span class="num">' + x.day + ' ' + x.time + '</span></li>').join('') + '</ol>' +
        fig(dotRows(ctx, s.slice(0, 5).map((x) => x.code)), 'Each dot is one in fifty simulated races, placed at that driver\'s finishing position. Red dots are retirements. Mock data.',
          note('<b>Read across, not down.</b> A tight cluster means the model is confident. A long smear means anything can happen.') + note('Simulation frozen after ' + W.forecast.session + ', ' + W.forecast.frozenAt + '.')) +
        fig(C.chart('interval', { h: 220, rows: ctx.M.championship }), 'The title: points today (dot) and where each contender is likely to end the season (bar).', note('Five rounds remain. ' + C.team('PIA').name + ' leads, but ' + C.pct(1 - ctx.M.championship[0].title, 0) + ' of simulated seasons end with someone else as champion.')));
    },
    predict(ctx) {
      return shell(ctx, '02', 'Fifty ways Sunday could go', 'A single favourite hides how often the favourite loses. Here are fifty simulated races, each shown by its podium. Tap a driver to find them in every future.',
        fig(C.chart('futures', { n: 50, cols: ctx.mobile() ? 5 : 10 }), 'Each tile is one simulated race. Bars from top: winner, second, third. Mock data.',
          note('Count the orange bars on top: that\'s how often a McLaren wins.') + note('No two rows look the same. That variety <i>is</i> the forecast.')) +
        fig(C.chart('ridge', { h: 420, rows: ctx.byAvg.slice(0, 10), amp: 2.4 }), 'The same races as shapes: where each driver finishes, across all ' + ctx.M.base.sims.toLocaleString() + ' simulations.', note('Narrow peaks are drivers the model is sure about. Wide hills are drivers who could be anywhere.')));
    },
    fantasy(ctx) {
      BLK.registerFantasy(ctx, { alts: 3, histH: 170, metrics: (items) => '<p class="e-big">A <b>' + items[0][1] + '</b>-point team, usually <b>' + items[1][1] + '</b>, for <b>' + items[2][1] + '</b>.</p>' });
      ctx.live['fantasy-stack'] = () => {
        const t = ctx.Fantasy.pick(ctx.Fantasy.state)[0]; if (!t) return '';
        const parts = t.drivers.map((c) => ({ c, v: ctx.Fantasy.D.find((d) => d.code === c).pts * (c === t.boost ? 2 : 1), col: C.team(c).colour })).concat(t.cons.map((c) => ({ c, v: ctx.Fantasy.T.find((x) => x.code === c).pts, col: ctx.M.teamById[c].colour }))).filter((p) => p.v > 0).sort((a, b) => b.v - a.v);
        const tot = parts.reduce((a, p) => a + p.v, 0);
        return '<div class="e-stack" role="img" aria-label="Where the team\'s points come from">' + parts.map((p) => '<span style="flex:' + p.v + ';background:' + p.col + '"' + (C.team(p.c) ? ' data-driver="' + p.c + '"' : '') + '><b>' + p.c + '</b><i class="num">' + Math.round(p.v / tot * 100) + '%</i></span>').join('') + '</div>';
      };
      return shell(ctx, '03', 'Building a portfolio, not a wish list', 'Fantasy is a budget problem with uncertain returns. The best team balances a few expensive, reliable scorers against cheap picks that rarely hurt.',
        '<div data-live="fantasy-metrics">' + ctx.live['fantasy-metrics']() + '</div>' +
        fig('<div data-live="fantasy-stack">' + ctx.live['fantasy-stack']() + '</div>', 'Where the expected points come from. The 2× boost doubles one driver.', note('Constructors score for both of their cars, so they carry a large share of the total.')) +
        fig(BLK.riskReward(ctx, 380), 'Every driver by expected points (up) and how widely their result swings (right). Bubble size is price.', note('Top-left is the dream: high reward, low risk. Nobody lives there.') + note('Bottom-left is cheap and safe, but scores little.')) +
        fig('<div data-live="fantasy-dist">' + ctx.live['fantasy-dist']() + '</div>', 'The team\'s score across all simulated races.', '') +
        '<section class="e-picks"><h2>Change the brief</h2><p class="muted">Lock someone in or rule them out, and the portfolio rebalances.</p><div data-live="fantasy-chips">' + BLK.fantasyChips(ctx) + '</div></section>');
    },
    replay(ctx) {
      BLK.registerReplay(ctx, { n: 6, compact: true, allEvents: true });
      ctx.live.story = (st) => {
        const ev = ctx.M.race.events.filter((e) => e.lap <= st.leaderLap && e.kind !== 'move').slice(-1)[0];
        return '<p class="e-now"><span class="num">Lap ' + st.leaderLap + '</span> ' + (ev ? BLK.esc(ev.text) : '') + '</p>';
      };
      return shell(ctx, '04', 'The race as a river', 'Every line is a driver; height is position. Lines cross at overtakes and pit stops, and bunch together under the safety car. Scrub to replay.',
        '<div class="e-river">' + C.chart('bump', { h: ctx.mobile() ? 380 : 560, lap: ctx.replayLap, cursor: true, pins: true }) + '<div class="e-inset">' + C.chart('track', { h: 170, lap: ctx.replayLap, carR: 4, labelTop: 1, noLabel: true, pad: 14 }) + '</div></div>' +
        BLK.replayControls(ctx, 'rp-controls e-ctrl') + '<div data-live="story"></div>' +
        fig('<div data-live="events" class="e-events"></div>', 'Numbered pins on the river mark the safety car, retirements and the fastest lap. Mock race.', note('Shift-click two lines to follow a battle.')) +
        fig(C.chart('tyres', { h: 420, lap: ctx.replayLap }), 'Tyre stints. The shaded band is the safety car, a cheap moment to stop.', note('In this mock race a stop under the safety car costs about half the usual time.')));
    },
    intel(ctx) {
      return shell(ctx, '05', 'Same car, different seasons', 'Oscar Piastri and Lando Norris drive identical McLarens. Over eighteen rounds their results drifted apart in small, telling ways (mock).',
        fig(BLK.formLines(ctx, ['PIA', 'NOR'], 300), 'Finishing position by round. Gaps in a line are retirements.', note('Look for runs of rounds where one line stays above the other.')) +
        fig(BLK.h2h(ctx, 'PIA', 'NOR'), 'The ledger.', note('Head-to-head counts ignore how big each gap was. The line chart above shows that.')) +
        fig('<div class="scroll-x">' + BLK.formTable(ctx, 12) + '</div>', 'The rest of the field, briefly.', ''));
    },
    lab(ctx) {
      BLK.registerLab(ctx, { n: 8, rangeH: 280 });
      ctx.live['lab-futures'] = () => ctx.labResult ? C.chart('futures', { n: 30, cols: ctx.mobile() ? 5 : 10, sim: ctx.labResult }) : '';
      ctx.live['lab-charts'] = () => ctx.live['lab-futures']();
      return shell(ctx, '06', 'Bend the race', 'What if Sunday is messier than usual? Turn up the chaos and watch the futures rearrange.',
        '<div class="e-lab"><div class="e-sliders">' + BLK.labSliders(ctx) + '<details class="e-more"><summary>Experimental engines</summary>' + BLK.labToggles(ctx) + '</details></div>' +
        '<div>' + fig('<div data-live="lab-charts"></div>', 'Thirty futures under your scenario. <span data-live="lab-meta"></span>', '') + '<div data-live="lab-diff"></div></div></div>');
    },
    eval(ctx) {
      const better = ctx.M.evaluation.filter((r) => r.rpsModel < r.rpsGrid).length;
      return shell(ctx, '07', 'Keeping score', 'A forecast is only useful if its numbers mean something. When the model says 30%, it should happen about three times in ten.',
        fig(C.chart('calib', { h: 420 }), 'Calibration for top-three finishes, 2026. Dot size is how many forecasts fell in each group (mock).', note('Points below the dashed line mean the model was over-confident at that level.')) +
        fig(C.chart('paired', { h: 260 }), 'Ranked probability score per round: the model in colour, simply copying the grid in grey. Lower is better.', note('The model beat the grid in <b>' + better + ' of ' + ctx.M.evaluation.length + '</b> rounds.')));
    }
  };

  window.CONCEPTS.e = { name: 'E · Raceline', render(screen, ctx) { return screens[screen](ctx); } };
})();
