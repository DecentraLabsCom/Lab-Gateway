import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-reservation-renderers.js', repoRoot);

function loadRenderers() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-reservation-renderers.js',
  });
  return context.window.LabManagerReservationRenderers;
}

function dependencies() {
  const escape = value => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
  return {
    escapeHtml: escape,
    htmlEscape: escape,
    formatDate: value => `date:${value}`,
    formatBool: value => value === true ? 'yes' : value === false ? 'no' : 'n/a',
    formatReservationDate: value => `reservation:${value}`,
    formatRange: (start, end) => `range:${start}-${end}`,
    isReservationWindowEnded: reservation => reservation.end === 100,
    normalizeReservationStatus: status => Number.isInteger(Number(status)) ? Number(status) : null,
    cancellationButtonLabel: (status, reasonCode) => status === 2 || reasonCode === 8
      ? 'Report service failure'
      : 'Cancel reservation',
    shortAddress: value => String(value || '').slice(0, 4),
    resolveReservationLabDisplayName: reservation => reservation.labName || `Lab #${reservation.labId}`,
  };
}

test('renders actionable reservations with safe status and cancellation markup', () => {
  const renderer = loadRenderers().createController(dependencies());
  const html = renderer.renderUpcomingReservationsMarkup([{
    reservationKey: '0x<unsafe>',
    status: 1,
    statusLabel: 'CONFIRMED',
    end: 100,
    start: 10,
    cancellable: true,
    cancellationOptions: [{
      reasonCode: 8,
      label: '<provider failure>',
      deadline: 20,
      reputationPenalty: 0,
    }],
    renter: '0xabcdef',
    labId: 'lab-1',
    priceCredits: '12.5',
  }], true);

  assert.match(html, /data-reservation-key="0x&lt;unsafe&gt;"/);
  assert.match(html, /CONFIRMED · ACCESS WINDOW ENDED/);
  assert.match(html, /Report service failure/);
  assert.match(html, /&lt;provider failure&gt;/);
  assert.match(html, /reservation:20/);
  assert.match(html, /data-action="load-more-actionable"/);
  assert.doesNotMatch(html, /<unsafe>/);
});

test('keeps unavailable cancellation and empty reservation markup stable', () => {
  const renderer = loadRenderers().createController(dependencies());
  const html = renderer.renderUpcomingReservationsMarkup([{
    reservationKey: 'reservation-2',
    status: 0,
    statusLabel: 'PENDING',
    start: 10,
    end: 20,
    cancellable: false,
    labName: 'Lab 2',
  }]);

  assert.match(html, /Cancellation unavailable for this status/);
  assert.doesNotMatch(html, /cancel-reservation/);
  assert.equal(renderer.renderUpcomingReservationsMarkup([]), '');
});

test('renders timeline summary, phases, operations and heartbeat safely', () => {
  const renderer = loadRenderers().createController(dependencies());
  const html = renderer.renderTimelineMarkup({
    reservation: {
      reservationId: '0x<reservation>',
      labId: 'lab-1',
      status: 'confirmed',
      start: 10,
      end: 20,
    },
    host: { name: 'host<&', labName: 'Lab 1' },
    phases: { wake: { success: true, createdAt: 'now', message: 'ready<&' } },
    operations: [{
      action: 'prepare<&',
      success: false,
      createdAt: 'later',
      durationMs: 12,
      responseCode: 500,
      message: 'failed<&',
    }],
    pagination: { offset: 0, returned: 1, total: 2, hasMore: true },
    heartbeat: {
      timestamp: 'heartbeat',
      ready: true,
      localMode: false,
      localSession: null,
      lastPower: { mode: 'wake', timestamp: 'power' },
      lastForcedLogoff: { user: 'operator', timestamp: 'logoff' },
    },
  });

  assert.match(html, /0x&lt;reservation&gt;/);
  assert.match(html, /host&lt;&amp;/);
  assert.match(html, /Wake: ok/);
  assert.match(html, /prepare&lt;&amp;/);
  assert.match(html, /failed&lt;&amp;/);
  assert.match(html, /Showing 1-1 of 2/);
  assert.match(html, /timelineLoadMoreBtn/);
  assert.match(html, /Heartbeat \(date:heartbeat\)/);
  assert.doesNotMatch(html, /<reservation>/);
});

test('renders the timeline heartbeat empty state without data', () => {
  const renderer = loadRenderers().createController(dependencies());
  const html = renderer.renderTimelineMarkup({ host: { name: 'station-1' } });

  assert.match(html, /No heartbeat data for station-1 yet\./);
  assert.match(html, /No orchestration events captured yet\./);
});
