const {test} = require('node:test');
const assert = require('node:assert/strict');
const {plans, parseSequence} = require('../portable_app/web/tyre-strategy.js');

test('compound and usage remain distinct, including missing set usage', () => {
  assert.deepEqual(parseSequence('Medium(used) → Hard(new) → Soft'), [
    {compound:'medium', usage:'used', label:'Medium(used)'},
    {compound:'hard', usage:'new', label:'Hard(new)'},
    {compound:'soft', usage:'unknown', label:'Soft'},
  ]);
  assert.equal(parseSequence('Intermediate(new) -> Wet(used)')[1].compound, 'wet');
});
test('missing recommendations do not become zero-stop plans', () => {
  for (const value of [null, '', 'Unknown', 'NaN', '—']) assert.deepEqual(parseSequence(value), []);
  assert.equal(plans({rows:[{Driver:'VER', PredictedStrategy:'Unknown'}]})[0].stops, null);
});
test('chart follows final displayed prediction ahead of legacy primary fields', () => {
  const row = {Driver:'VER', PredictedStrategy:'Medium(new) → Hard(new)', primary_strategy:'Soft(new) → Hard(new) → Soft(used)', expected_stops:2};
  assert.equal(plans({rows:[row]})[0].stops, 1);
  assert.equal(plans({rows:[{...row, history_adjusted_strategy:'Hard(new)'}]})[0].stops, 0);
});
test('alternative plans never borrow a missing recommendation', () => {
  const rows = [{Driver:'VER', PredictedStrategy:'Soft(new) → Hard(new)', AlternativeStrategy:'Hard(used) → Medium(new) → Soft(new)'}, {Driver:'NOR', PredictedStrategy:'Medium(new) → Hard(new)'}];
  const result = plans({rows}, 'alternative');
  assert.equal(result.find(row => row.driver === 'VER').stops, 2);
  assert.equal(result.find(row => row.driver === 'NOR').stops, null);
});
test('numeric model grid sorts before unknown and pit-lane placeholders', () => {
  const rows = [{Driver:'Z',GridPosition:0}, {Driver:'Y'}, {Driver:'B',Grid:'P10'}, {Driver:'A',GridPosition:2}];
  assert.deepEqual(plans({rows}).map(row => row.driver), ['A','B','Y','Z']);
  assert.equal(plans({rows})[3].grid, null);
});
test('unknown compounds are retained without a known-tyre label', () => {
  assert.deepEqual(parseSequence('Experimental(new)'), [{compound:'unknown', usage:'new', label:'Experimental(new)'}]);
  assert.deepEqual(plans(null), []);
});
