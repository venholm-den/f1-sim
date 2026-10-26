const test = require('node:test');
const assert = require('node:assert/strict');

global.plural = (count, noun) => `${count} ${noun}${count === 1 ? '' : 's'}`;
const { driversAnswers, accuracyAnswers, retirementTally, scenarioChanges, signedPercent, excludedNote } = require('../portable_app/web/insights.js');

test('Drivers answers come from the season summary', () => {
  const data = {
    rounds: 4,
    drivers: [
      { driver: 'NOR', team: 'McLaren', races: 4, wins: 1, podiums: 3, points: 80, retirements: 1 },
      { driver: 'VER', team: 'Red Bull', races: 4, wins: 2, podiums: 2, points: 70, retirements: 0 },
      { driver: 'PIA', team: 'McLaren', races: 1, wins: 0, podiums: 0, points: 4, retirements: 0 },
    ],
    pairs: [
      { team: 'McLaren', a: 'NOR', b: 'PIA', a_ahead: 1, b_ahead: 0, races: 1 },
      { team: 'Red Bull', a: 'TSU', b: 'VER', a_ahead: 1, b_ahead: 2, races: 4 },
    ],
  };
  const answers = driversAnswers(data);
  assert.deepEqual(answers.map(a => a.value), ['NOR · 80', 'VER · 2', 'TSU 1–2 VER', 'VER · 0']);
  assert.equal(answers[0].note, 'McLaren, after 4 rounds');
  assert.deepEqual(driversAnswers({ drivers: [] }), []);
});

test('Accuracy answers average the scored races', () => {
  const scored = [
    { year: 2026, event: 'Mexico City Grand Prix', finish_mae: 3, win_chance_skill: 0.2, podium_chance_skill: -0.1 },
    { year: 2026, event: 'United States Grand Prix', finish_mae: 4, win_chance_skill: 0.4, podium_chance_skill: null },
  ];
  const answers = accuracyAnswers({ scored });
  assert.deepEqual(answers.map(a => a.value), ['2', '3.5 places', '+30%', '−10%']);
  assert.equal(answers[0].note, 'latest 2026 Mexico City Grand Prix');
  assert.deepEqual(accuracyAnswers({ scored: [] }), []);
  assert.equal(signedPercent(null), '—');
});

test('Accuracy can score finishers only and tallies retirements', () => {
  const scored = [
    { year: 2026, event: 'Singapore Grand Prix', finish_mae: 4, finishers_finish_mae: 2, retirements: 3, expected_retirements: 0.8 },
    { year: 2026, event: 'Bahrain Grand Prix', finish_mae: 3, finishers_finish_mae: 3, retirements: 1, expected_retirements: 0.7 },
  ];
  assert.equal(accuracyAnswers({ scored })[1].value, '3.5 places');
  const finishers = accuracyAnswers({ scored }, 'finishers');
  assert.equal(finishers[1].value, '2.5 places');
  assert.equal(finishers[4].value, '4 vs 1.5');
  assert.deepEqual(retirementTally([{ retirements: 2, expected_retirements: null }]), { races: 1, actual: 2, expected: null });
  assert.equal(retirementTally([{ retirements: null }]), null);
});

test('Scenario changes list only what differs from Race setup', () => {
  const options = [{ key: 'race_engine', label: 'Race engine', options: [{ value: 'pit', label: 'Pit-stop scenarios' }] }];
  const base = { default_overtaking_difficulty: 0.55 };
  assert.deepEqual(scenarioChanges(base, { default_overtaking_difficulty: 0.55 }, {}, options), []);
  assert.deepEqual(scenarioChanges(base, { default_overtaking_difficulty: 0.8 }, { race_engine: 'pit' }, options),
    ['Overtaking difficulty 55 → 80', 'Race engine: Pit-stop scenarios']);
});

test('Accuracy says how many personal runs were left out and why', () => {
  assert.equal(excludedNote([]), '');
  const note = excludedNote([
    { id: 'a', reasons: ['Changed from the official protocol: Overtaking difficulty 0.55 → 0.7'] },
    { id: 'b', reasons: ['Changed from the official protocol: Overtaking difficulty 0.55 → 0.7'] },
  ]);
  assert.equal(note, '2 personal runs are left out of this record: Changed from the official protocol: Overtaking difficulty 0.55 → 0.7.');
});
