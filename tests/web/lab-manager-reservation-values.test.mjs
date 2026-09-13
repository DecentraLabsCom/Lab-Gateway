import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-reservation-values.js', repoRoot);

function loadValues() {
  const context = vm.createContext({ console, window: { Date, Intl } });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-reservation-values.js',
  });
  return context.window.LabManagerReservationValues;
}

test('formats reservation timestamps and ranges through injected dependencies', () => {
  const module = loadValues();
  const values = module.createController({
    dateTimeFormatCtor: class {
      format(date) { return `formatted:${date.getTime()}`; }
    },
    formatDate: value => `date:${value}`,
  });

  assert.equal(values.formatReservationDate(12.5), 'formatted:12500');
  assert.equal(values.formatReservationDate('invalid'), 'Unknown time');
  assert.equal(values.formatRange(10, 20), 'date:10 → date:20');
  assert.equal(values.formatRange(0, 0), 'n/a');
});

test('keeps reservation status and cancellation labels stable', () => {
  const module = loadValues();
  const values = module.createController({ formatDate: value => String(value) });

  assert.equal(values.normalizeReservationStatus('0'), 0);
  assert.equal(values.normalizeReservationStatus(2), 2);
  assert.equal(values.normalizeReservationStatus('unknown'), null);
  assert.equal(values.cancellationButtonLabel(0, 1), 'Decline request');
  assert.equal(values.cancellationButtonLabel(1, 8), 'Report service failure');
  assert.equal(values.cancellationButtonLabel(2, 1), 'Report service failure');
  assert.equal(values.cancellationButtonLabel(1, 1), 'Cancel reservation');
});

test('uses the injected clock for access-window expiry', () => {
  const module = loadValues();
  const values = module.createController({
    now: () => 100000,
    formatDate: value => String(value),
  });

  assert.equal(values.isReservationWindowEnded({ end: 99 }), true);
  assert.equal(values.isReservationWindowEnded({ end: 100 }), true);
  assert.equal(values.isReservationWindowEnded({ end: 101 }), false);
  assert.equal(values.isReservationWindowEnded({ end: 'invalid' }), false);
});

test('shortens long addresses with the existing prefix and suffix lengths', () => {
  const module = loadValues();
  const values = module.createController({ formatDate: value => String(value) });

  assert.equal(values.shortAddress('0x1234567890abcdef'), '0x1234…cdef');
  assert.equal(values.shortAddress('short'), 'short');
  assert.equal(values.shortAddress(null), '');
  assert.equal(values.shortAddress('abcdefghijkl', 3, 2), 'abc…kl');
});
