/* Concept L: Broadcast hybrid. Kyle's preferred look (B, Lights Out) applied to
   the hybrid's structure: the same screens, answer rows and uncertainty charts
   as H, dressed as a broadcast graphics package. The full-height hero becomes a
   slim strip, and charts keep H's focus-only team colour so they stay legible. */
(function () {
  'use strict';
  const titles = {
    hub: ['Race weekend', 'Who can win in Austin'],
    predict: ['Prediction', 'How Sunday could go'],
    fantasy: ['Fantasy', 'Build the team'],
    replay: ['Race replay', 'Lap by lap'],
    intel: ['Driver intelligence', 'Teammates compared'],
    lab: ['What if', 'Change the race'],
    eval: ['Scorecard', 'Were we right?']
  };

  function shell(ctx, inner) {
    const W = ctx.M.weekend, [kicker, title] = titles[ctx.screen];
    return '<div class="b-shell l-shell"><header class="b-top"><div class="b-logo"><span class="b-slash"></span>RACE<b>WORKBENCH</b></div>' +
      BLK.nav(ctx, 'b-nav', { hub: 'Weekend', predict: 'Prediction', fantasy: 'Fantasy', replay: 'Replay', intel: 'Drivers', lab: 'What if', eval: 'Scorecard' }) + ctx.mockTag + '</header>' +
      '<section class="l-strip"><div class="b-stripes" aria-hidden="true">' + ctx.M.teams.slice(0, 6).map((t) => '<i style="background:' + t.colour + '"></i>').join('') + '</div>' +
      '<div class="l-strip-in"><span class="b-kicker">' + kicker + '</span><h1>' + title + '</h1></div>' +
      '<div class="l-round"><span>R' + W.round + '</span> ' + W.event.toUpperCase() + '<small>Forecast after ' + W.forecast.session + '</small></div></section>' +
      '<div class="a-grid h-grid l-grid h-' + ctx.screen + '">' + inner + '</div>' +
      '<footer class="l-keys"><span><kbd>1</kbd>–<kbd>7</kbd> screens</span><span><kbd>Space</kbd> play</span><span><kbd>←</kbd><kbd>→</kbd> lap</span><span><kbd>Shift</kbd>+click compare</span><span><kbd>Esc</kbd> clear</span><span class="l-focus">Focus: <b data-focus-label>All drivers</b></span></footer></div>';
  }

  window.CONCEPTS.l = {
    name: 'L · Broadcast hybrid',
    render(screen, ctx) { return shell(ctx, window.CONCEPTS.h.screens[screen](ctx)); }
  };
})();
