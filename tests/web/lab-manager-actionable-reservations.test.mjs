import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-actionable-reservations.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {}, URLSearchParams });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-actionable-reservations.js',
  });
  return context.window.LabManagerActionableReservations;
}

function element(overrides = {}) {
  return {
    value: '',
    textContent: '',
    innerHTML: '',
    className: '',
    disabled: false,
    listeners: {},
    classList: { add() {}, remove() {} },
    addEventListener(type, handler) {
      this.listeners[type] = handler;
    },
    contains: () => true,
    ...overrides,
  };
}

function response(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function dependencies(overrides = {}) {
  const events = [];
  return {
    listEl: element(),
    statusEl: element(),
    fetchImpl: async () => response({
      reservations: [{ reservationKey: 'reservation-1' }],
      pagination: { offset: 0, returned: 1, total: 1, hasMore: false },
    }),
    renderMarkup: (reservations, hasMore) => `${reservations.length}:${hasMore}`,
    escapeHtml: value => String(value),
    normalizeReservationStatus: value => Number(value),
    cancellationButtonLabel: () => 'Cancel reservation',
    showToast: (...args) => events.push(args),
    confirmImpl: () => true,
    createIdempotencyKey: () => 'idempotency-test-key',
    logger: { error() {} },
    events,
    ...overrides,
  };
}

test('loads actionable reservations and preserves offset/cursor pagination state', async () => {
  const module = loadModule();
  const requests = [];
  const pages = [
    response({
      reservations: [{ reservationKey: 'reservation-1' }],
      pagination: { offset: 0, returned: 1, total: 2, nextCursor: 'cursor-2', hasMore: true },
    }),
    response({
      reservations: [{ reservationKey: 'reservation-2' }],
      pagination: { offset: 1, returned: 1, total: 2, hasMore: false },
    }),
  ];
  const deps = dependencies({
    fetchImpl: async (url) => {
      requests.push(url);
      return pages.shift();
    },
    renderMarkup: reservations => reservations.map(item => item.reservationKey).join(','),
  });
  const controller = module.createController(deps);

  await controller.load();
  await controller.load({ append: true });

  assert.match(requests[0], /limit=100/);
  assert.match(requests[0], /offset=0/);
  assert.match(requests[1], /offset=1/);
  assert.match(requests[1], /cursor=cursor-2/);
  assert.equal(deps.listEl.innerHTML, 'reservation-1,reservation-2');
  assert.equal(controller.getState().reservations.length, 2);
  assert.equal(controller.getState().hasMore, false);
});

test('posts a cancellation with the selected reason and refreshes the list', async () => {
  const module = loadModule();
  const requests = [];
  let confirmMessage = '';
  const reasonEl = { value: '8', disabled: false };
  const button = { disabled: false, textContent: '', closest: () => row };
  const row = {
    dataset: { reservationKey: 'reservation-7', reservationStatus: '1' },
    querySelector(selector) {
      if (selector === '[data-reservation-reason]') return reasonEl;
      if (selector === '[data-action="cancel-reservation"]') return button;
      return null;
    },
  };
  const eventTarget = {
    closest(selector) {
      return selector === '[data-action="cancel-reservation"]' ? button : null;
    },
  };
  const deps = dependencies({
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      return requests.length === 1
        ? response({})
        : response({ reservations: [], pagination: { returned: 0, hasMore: false } });
    },
    confirmImpl: message => {
      confirmMessage = message;
      return true;
    },
  });
  deps.listEl.contains = () => true;
  deps.listEl.innerHTML = 'reservation';
  const originalClosest = eventTarget.closest;
  eventTarget.closest = selector => selector === '.reservation-item' ? row : originalClosest(selector);
  const controller = module.createController(deps);

  await controller.handleActions({ target: eventTarget });

  assert.match(confirmMessage, /provider service failure/i);
  assert.equal(requests[0].url, '/lab-admin/reservations/reservation-7/cancel');
  assert.equal(requests[0].options.method, 'POST');
  assert.equal(requests[0].options.headers['Idempotency-Key'], 'idempotency-test-key');
  assert.deepEqual(JSON.parse(requests[0].options.body), { reasonCode: 8 });
  assert.deepEqual(deps.events, [['Provider service-failure report submitted', 'success']]);
});

test('keeps unauthorized reservation access visible without replacing existing results', async () => {
  const module = loadModule();
  const deps = dependencies({ fetchImpl: async () => response({}, 401) });
  deps.listEl.innerHTML = 'existing';
  const controller = module.createController(deps);

  await controller.load();

  assert.equal(deps.listEl.innerHTML, '<div class="empty">Unauthorized: check LAB_MANAGER_TOKEN.</div>');
  assert.equal(deps.statusEl.textContent, 'Unauthorized');
  assert.equal(controller.getState().loading, false);
});
