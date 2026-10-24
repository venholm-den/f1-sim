/* Concept B: Lights Out (Premium F1 Broadcast).
   Cinematic, team-colour led. Broadcast graphics: timing towers, lower thirds,
   big numbers and a full-bleed replay stage. */
(function () {
  'use strict';
  const card = (title, body, cls) => '<section class="b-card ' + (cls || '') + '">' + (title ? '<h2 class="b-h">' + title + '</h2>' : '') + body + '</section>';
  const lower = (kicker, text) => '<div class="b-lower"><span class="b-kicker">' + kicker + '</span><p>' + text + '</p></div>';

  function shell(ctx, hero, inner) {
    return '<div class="b-shell"><header class="b-top"><div class="b-logo"><span class="b-slash"></span>RACE<b>WORKBENCH</b></div>' +
      BLK.nav(ctx, 'b-nav', { hub: 'Weekend', predict: 'Prediction', fantasy: 'Fantasy', replay: 'Replay', intel: 'Drivers', lab: 'What if', eval: 'Scorecard' }) + ctx.mockTag + '</header>' +
      (hero || '') + '<div class="b-main b-' + ctx.screen + '">' + inner + '</div></div>';
  }
  function hero(ctx, kicker, title, sub) {
    const W = ctx.M.weekend;
    return '<section class="b-hero"><div class="b-stripes" aria-hidden="true">' + ctx.M.teams.slice(0, 6).map((t) => '<i style="background:' + t.colour + '"></i>').join('') + '</div>' +
      '<div class="b-hero-in"><span class="b-kicker">' + kicker + '</span><h1>' + title + '</h1><p>' + sub + '</p></div>' +
      '<div class="b-round"><span>ROUND</span><b class="num">' + W.round + '</b></div></section>';
  }
  function tower(rows, key, fmt) {
    return '<ol class="b-tower">' + rows.map((s, i) => { const d = C.team(s.code); return '<li data-driver="' + s.code + '" tabindex="0"><span class="b-pos num">' + (i + 1) + '</span><i style="background:' + d.colour + '"></i><b>' + s.code + '</b><span class="b-val num">' + fmt(s[key]) + '</span></li>'; }).join('') + '</ol>';
  }
  function driverCard(ctx, s, rank) {
    const d = C.team(s.code);
    return '<article class="b-driver" data-driver="' + s.code + '" tabindex="0" style="--team:' + d.colour + '"><span class="b-num num">' + d.number + '</span><span class="b-rank">P' + rank + ' favourite</span><h3>' + d.name.split(' ')[0] + ' <b>' + d.name.split(' ').slice(1).join(' ').toUpperCase() + '</b></h3><span class="b-team">' + d.teamName + '</span><div class="b-big num">' + C.pct(s.win, 0) + '<small>to win</small></div><div class="b-sub num">' + C.pct(s.podium, 0) + ' podium · P' + Math.round(s.p25) + '–' + Math.round(s.p75) + ' likely</div></article>';
  }

  const screens = {
    hub(ctx) {
      const W = ctx.M.weekend, top = ctx.sum.slice(0, 3);
      return [hero(ctx, W.city + ' · ' + W.venue, W.event.replace(' Grand Prix', '') + '<br><span>Grand Prix</span>', 'Qualifying Saturday 21:00 · Race Sunday 20:00 · ' + W.laps + ' laps'),
        '<div class="b-strip">' + BLK.schedule(ctx, 'b-sched') + '</div>' +
        '<h2 class="b-section">Who wins on Sunday?</h2><div class="b-podium">' + top.map((s, i) => driverCard(ctx, s, i + 1)).join('') + '</div>' +
        '<div class="b-cols">' + card('Win chance', tower(ctx.sum.slice(0, 10), 'win', (v) => C.pct(v, 1))) +
        '<div class="b-stack">' + lower('The story', ctx.sum[0].code + ' starts as a narrow favourite. The top four are separated by under six points of win chance.') +
        lower('Watch for', 'Tyre wear. A one-stop on mediums and hards is the most common plan in the forecast.') +
        lower('Forecast', 'Frozen after ' + W.forecast.session + ' · ' + W.forecast.sims.toLocaleString() + ' simulated races') +
        card('Title fight', C.chart('interval', { h: 220, rows: ctx.M.championship })) + '</div></div>'];
    },
    predict(ctx) {
      const lead = ctx.sum[0];
      return [hero(ctx, 'Race prediction', 'The <span>order</span>', 'Each driver\'s likely finishing range from ' + ctx.M.base.sims.toLocaleString() + ' simulated races (mock).'),
        '<div class="b-cols">' + card('Average finish', tower(ctx.byAvg.slice(0, 12), 'avgFinish', (v) => 'P' + v.toFixed(1))) +
        '<div class="b-stack">' + card('', driverCard(ctx, lead, 1) + '<div class="b-dots">' + C.chart('dots', { h: 150, code: lead.code }) + '<p class="b-cap">Every dot is 2% of simulated races. Red dots are retirements.</p></div>', 'b-feature') +
        card('Likely finishing range', C.chart('range', { h: 330, rows: ctx.byAvg.slice(0, 12), teamColour: true })) + '</div></div>' +
        card('Position by position', C.chart('heat', { rows: ctx.byAvg.slice(0, 10), upto: 10 }), 'b-wide')];
    },
    fantasy(ctx) {
      BLK.registerFantasy(ctx, { metrics: (items) => '<div class="b-bignums">' + items.map(([k, v]) => '<div><b class="num">' + v + '</b><span>' + k + '</span></div>').join('') + '</div>' });
      ctx.live['fantasy-sheet'] = () => {
        const t = ctx.Fantasy.pick(ctx.Fantasy.state)[0]; if (!t) return '<p class="empty">No team fits. Unlock an asset.</p>';
        return '<div class="b-sheet">' + t.drivers.map((c) => { const d = C.team(c), s = ctx.M.base.summary[d.idx]; return '<article class="b-slot" data-driver="' + c + '" style="--team:' + d.colour + '"><span class="b-num num">' + d.number + '</span>' + (c === t.boost ? '<span class="b-boost">2×</span>' : '') + '<b>' + c + '</b><span class="num">$' + d.price + 'm</span><strong class="num">' + (s.fantasyMean * (c === t.boost ? 2 : 1)).toFixed(1) + '</strong></article>'; }).join('') +
          t.cons.map((c) => { const tm = ctx.M.teamById[c]; return '<article class="b-slot b-con" style="--team:' + tm.colour + '"><b>' + c + '</b><span>' + tm.name + '</span><span class="num">$' + tm.price + 'm</span><strong class="num">' + ctx.Fantasy.T.find((x) => x.code === c).pts.toFixed(1) + '</strong></article>'; }).join('') + '</div>';
      };
      return [hero(ctx, 'Fantasy', 'Your <span>line-up</span>', 'The best five drivers and two constructors under $' + ctx.Fantasy.state.budget + 'm for this race.'),
        '<div data-live="fantasy-sheet">' + ctx.live['fantasy-sheet']() + '</div><div data-live="fantasy-metrics">' + ctx.live['fantasy-metrics']() + '</div>' +
        card('Build around', '<p class="b-cap">Tap once to lock an asset in, twice to leave it out.</p><div data-live="fantasy-chips">' + BLK.fantasyChips(ctx) + '</div>') +
        '<div class="b-cols">' + card('Risk and reward', BLK.riskReward(ctx, 300)) + card('Other line-ups', '<div class="scroll-x" data-live="fantasy-alt">' + ctx.live['fantasy-alt']() + '</div>') + '</div>'];
    },
    replay(ctx) {
      BLK.registerReplay(ctx, { n: ctx.mobile() ? 6 : 10, compact: true });
      return ['', '<section class="b-stage"><div class="b-stage-map">' + C.chart('track', { h: ctx.mobile() ? 300 : 520, lap: ctx.replayLap, pad: 40, carR: 7, labelTop: 3 }) + '</div>' +
        '<div class="b-overlay-tower"><div class="b-ot-head">Mock race · 56 laps</div><div data-live="tower"></div></div>' +
        '<div class="b-lapcount"><span>LAP</span><b data-live="lap"></b><span data-live="flag"></span></div></section>' +
        BLK.replayControls(ctx, 'rp-controls b-ctrl') +
        '<div class="b-ticker" data-live="events"></div>' +
        '<div class="b-cols">' + card('How the race unfolded', C.chart('bump', { h: 300, lap: ctx.replayLap, cursor: true, showN: 10 })) + card('Strategy', C.chart('tyres', { h: 300, lap: ctx.replayLap })) + '</div>' +
        card('Fastest laps · ' + ctx.M.telemetry.a + ' vs ' + ctx.M.telemetry.b, BLK.telemetry(ctx, 170), 'b-wide')];
    },
    intel(ctx) {
      const a = C.team('PIA'), b = C.team('NOR');
      return [hero(ctx, 'Tale of the tape', 'Piastri <span>v</span> Norris', 'Team-mates at McLaren across 18 rounds of 2026 (mock).'),
        '<section class="b-tape" style="--ta:' + a.colour + ';--tb:' + b.colour + '"><div class="b-tape-side"><span class="b-num num">' + a.number + '</span><b>PIA</b></div>' + BLK.h2h(ctx, 'PIA', 'NOR') + '<div class="b-tape-side r"><span class="b-num num">' + b.number + '</span><b>NOR</b></div></section>' +
        '<div class="b-cols">' + card('Season form', BLK.formLines(ctx, ['PIA', 'NOR'], 260)) + card('The field', '<div class="scroll-x">' + BLK.formTable(ctx, 10) + '</div>') + '</div>'];
    },
    lab(ctx) {
      BLK.registerLab(ctx, { n: 8 });
      return [hero(ctx, 'Simulation lab', 'What <span>if</span>…', 'Change the race and see who gains. Scenario B against the established run.'),
        '<div class="b-cols">' + card('Change the race', BLK.labSliders(ctx) + '<h3 class="b-h3">Experimental engines</h3>' + BLK.labToggles(ctx)) +
        '<div class="b-stack">' + card('Who gains, who loses', '<p class="b-cap" data-live="lab-meta"></p><div data-live="lab-diff"></div>') + card('Likely finish under B', '<div data-live="lab-charts"></div>') + '</div></div>'];
    },
    eval(ctx) {
      const k = BLK.evalKpis(ctx);
      return [hero(ctx, 'Scorecard', 'How did we <span>do?</span>', 'Every 2026 forecast scored against what happened (mock).'),
        '<div class="b-bignums">' + k.map(([l, v]) => '<div><b class="num">' + v + '</b><span>' + l + '</span></div>').join('') + '</div>' +
        '<div class="b-cols">' + card('Accuracy by round · red = model, grey = grid order', C.chart('paired', { h: 260 })) + card('When we said X%, did it happen X% of the time?', C.chart('calib', { h: 260 })) + '</div>'];
    }
  };

  window.CONCEPTS.b = {
    name: 'B · Lights Out',
    render(screen, ctx) { const [h, inner] = screens[screen](ctx); return shell(ctx, h, inner); }
  };
})();
