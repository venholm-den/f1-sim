const test = require('node:test');
const assert = require('node:assert/strict');
const { forecastAnswers, hubAnswers, quantileDots, nextSession } = require('../portable_app/web/forecast.js');

const rows = [
  { Driver: 'NOR', avg_finish: 4.0, win_chance: 0.259, dnf_chance: 0.061 },
  { Driver: 'VER', avg_finish: 4.5, win_chance: 0.198, dnf_chance: 0.06 },
  { Driver: 'PIA', avg_finish: 4.6, win_chance: 0.165 },
  { Driver: 'RUS', avg_finish: 5.9, win_chance: 0.102 },
];
const ranges = [
  { driver: 'NOR', p25: 1, p75: 4 }, { driver: 'VER', p25: 2, p75: 5 },
  { driver: 'PIA', p25: 2, p75: 6 }, { driver: 'RUS', p25: 3, p75: 7.4 },
];

test('prediction answers come from the saved rows and ranges', () => {
  const answers = forecastAnswers(rows, ranges);
  assert.deepEqual(answers.map(a => a.value), ['NOR · 26%', 'NOR · VER · PIA', 'RUS · P3–P7', '6%']);
  assert.equal(answers[0].note, 'someone else wins 74% of simulated races');
  assert.deepEqual(forecastAnswers([], []), []);
});

test('prediction answers leave out what the run did not save', () => {
  const answers = forecastAnswers(rows.slice(0, 2).map(({ dnf_chance, ...r }) => r), []);
  assert.deepEqual(answers.map(a => a.label), ['Most likely winner']);
});

test('hub answers count contenders and say when title odds are missing', () => {
  const loading = hubAnswers(rows, undefined, { sims: 5000, label: '2026 United States Grand Prix · Q' });
  assert.deepEqual(loading.map(a => a.value), ['NOR', '3', '—', '5,000 races']);
  assert.equal(loading[2].note, 'loading title odds…');
  assert.equal(hubAnswers(rows, null, {}).at(2).note, 'title odds unavailable');
  const champ = { drivers: [{ name: 'PIA', current_points: 300 }, { name: 'NOR', current_points: 310 }] };
  assert.equal(hubAnswers([], champ, {}).at(1).value, 'NOR · 310 pts');
  assert.equal(hubAnswers([], champ, {})[0].value, 'No forecast');
});

test('quantile dots follow the finish probabilities', () => {
  assert.deepEqual(quantileDots([0.5, 0.3, 0.2], 10), [1, 1, 1, 1, 1, 2, 2, 2, 3, 3]);
  const dots = quantileDots([0.26, 0.2, 0.18, 0.36]);
  assert.equal(dots.length, 50);
  assert.equal(dots.filter(d => d === 1).length, 13);
  assert.deepEqual(quantileDots([0, 0]), []);
});

test('next session is the first that has not started', () => {
  const sessions = [{ name: 'FP1', start_utc: '2026-10-23T17:30:00Z' }, { name: 'Q', start_utc: '2026-10-24T21:00:00Z' }];
  assert.equal(nextSession(sessions, Date.parse('2026-10-24T12:00:00Z')).name, 'Q');
  assert.equal(nextSession(sessions, Date.parse('2026-10-25T12:00:00Z')), null);
});
