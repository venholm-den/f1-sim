const {test} = require('node:test');
const assert = require('node:assert/strict');
const {nextDriverFocus} = require('../portable_app/web/shell.js');

test('a plain click focuses one driver and a second click on them clears it', () => {
  assert.deepEqual(nextDriverFocus([], 'VER', false), ['VER']);
  assert.deepEqual(nextDriverFocus(['VER'], 'NOR', false), ['NOR']);
  assert.deepEqual(nextDriverFocus(['VER'], 'VER', false), []);
  assert.deepEqual(nextDriverFocus(['VER', 'NOR'], 'VER', false), ['VER']);
});
test('shift-click compares at most two drivers and toggles one off', () => {
  assert.deepEqual(nextDriverFocus(['VER'], 'NOR', true), ['VER', 'NOR']);
  assert.deepEqual(nextDriverFocus(['VER', 'NOR'], 'PIA', true), ['NOR', 'PIA']);
  assert.deepEqual(nextDriverFocus(['VER', 'NOR'], 'VER', true), ['NOR']);
  assert.deepEqual(nextDriverFocus([], 'PIA', true), ['PIA']);
});
