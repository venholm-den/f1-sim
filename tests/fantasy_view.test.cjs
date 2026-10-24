const test = require('node:test');
const assert = require('node:assert/strict');
const { fantasyAnswers, riskRewardPoints, signedPoints } = require('../portable_app/web/fantasy.js');

const team = (points, extra = {}) => ({
  expected_points: points, cost: 99.8, budget_left: 0.2, transfers_in: [], transfers_out: [],
  drivers: [{ code: 'NOR', points: 20.2, boosted: true }, { code: 'GAS', points: 6.5 }], constructors: [], ...extra,
});

test('Fantasy answers describe the best team only', () => {
  const answers = fantasyAnswers({ budget: 100, current: null, teams: [team(118.56, { range: { p10: 53.3, p90: 189.7 } })] });
  assert.deepEqual(answers.map(a => a.value), ['118.6 pts', '53–190', 'NOR 2×', '$99.8m']);
  assert.equal(answers[3].note, '$0.2m left');
  assert.deepEqual(fantasyAnswers({ teams: [] }), []);
});

test('Fantasy answers compare against the held team when one is entered', () => {
  const best = team(110, { transfers_in: ['VER'], transfers_out: ['GAS'] });
  const answers = fantasyAnswers({ budget: 100, current: { expected_points: 104.5 }, teams: [best] });
  assert.deepEqual(answers.map(a => a.label), ['Best team', 'Boost', 'Versus your team']);
  assert.equal(answers[2].value, '+5.5 pts');
  assert.equal(answers[2].note, '1 transfer');
});

test('risk and reward uses the spread when every driver has one, else price', () => {
  const drivers = [
    { code: 'NOR', points: 20, floor: 0, ceiling: 40, price: 29 },
    { code: 'GAS', points: 5, floor: 0, ceiling: 10, price: 11 },
    { code: 'ALO', points: 10, floor: 2, ceiling: 27, price: 12 },
  ];
  const chart = riskRewardPoints(drivers, ['GAS']);
  assert.equal(chart.mode, 'spread');
  assert.deepEqual(chart.points.map(p => [p.code, p.x, p.y, p.picked]), [['NOR', 1, 1, false], ['GAS', 0, 0, true], ['ALO', 0.5, 1 / 3, false]]);
  assert.equal(riskRewardPoints(drivers.map(({ floor, ...d }) => d), []).mode, 'price');
  assert.equal(riskRewardPoints(drivers.slice(0, 1), []).mode, 'none');
});

test('signed points use a real minus sign', () => {
  assert.equal(signedPoints(-0.25), '−0.3 pts');
  assert.equal(signedPoints(0), '0.0 pts');
});
