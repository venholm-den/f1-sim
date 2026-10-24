const test = require('node:test');
const assert = require('node:assert/strict');
const { replayEvents } = require('../portable_app/web/replay.js');

const lap = (n, start, time, extra = {}) => ({ lap: n, start, end: start + time, time, compound: 'MEDIUM', deleted: false, ...extra });
const session = (race = true) => ({
  race, start: 0, end: 450,
  drivers: [{ number: '1', code: 'NOR' }, { number: '2', code: 'STR' }],
  trackStatus: [{ t: 0, status: '1' }, { t: 150, status: '4' }, { t: 160, status: '4' }, { t: 250, status: '1' }, { t: 300, status: '2' }],
  laps: {
    '1': [lap(1, 0, 100), lap(2, 100, 98, { pitIn: true }), lap(3, 198, 101, { compound: 'HARD' }), lap(4, 299, 96)],
    '2': [lap(1, 1, 102), lap(2, 103, 99)],
  },
});

test('race events come from track status, pit entries, early stops and new fastest laps', () => {
  const events = replayEvents(session());
  assert.deepEqual(events.map(e => [e.t, e.kind, e.label]), [
    [198, 'pit', 'NOR pits'], [198, 'fastest', 'NOR fastest lap'], [150, 'status', 'Safety car'],
    [202, 'retired', 'STR stops'], [250, 'green', 'Track clear'], [395, 'fastest', 'NOR fastest lap'],
  ].sort((a, b) => a[0] - b[0]));
  assert.equal(events.find(e => e.kind === 'pit').detail, 'end of lap 2 · onto hard');
});

test('practice sessions list neutralisations and pits but not retirements or fastest laps', () => {
  const kinds = replayEvents(session(false)).map(e => e.kind);
  assert.deepEqual(kinds, ['status', 'pit', 'green']);
});
