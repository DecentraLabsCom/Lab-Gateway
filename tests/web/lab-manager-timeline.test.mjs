import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-timeline.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {}, URLSearchParams });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-timeline.js',
  });
  return context.window.LabManagerTimeline;
}

function element(overrides = {}) {
  return {
    value: '',
    textContent: '',
    innerHTML: '',
    disabled: false,
    classList: { add() {}, remove() {} },
    listeners: {},
    addEventListener(type, handler) {
      this.listeners[type] = handler;
    },
    focus() {},
    querySelector() { return null; },
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
    timelineInput: element({ value: 'reservation-7' }),
    timelineBtn: element(),
    timelineResult: element(),
    fetchImpl: async () => response({
      reservation: { reservationId: 'reservation-7' },
      operations: [{ action: 'wake', success: true }],
      pagination: { offset: 0, returned: 1, total: 1, hasMore: false },
    }),
    normalizePagination: (pagination, offset, returned, limit) => ({
      ...pagination,
      offset,
      returned,
      limit,
      nextOffset: offset + returned,
      hasMore: Boolean(pagination?.hasMore),
    }),
    renderTimelineMarkup: data => `timeline:${data.operations.length}`,
    showToast: (...args) => events.push(args),
    logger: { error() {} },
    events,
    ...overrides,
  };
}

test('loads and renders a timeline page while preserving pagination state', async () => {
  const module = loadModule();
  const deps = dependencies();
  const controller = module.createController(deps);

  controller.bind();
  await controller.fetchTimeline();

  assert.equal(deps.timelineBtn.listeners.click !== undefined, true);
  assert.equal(deps.timelineInput.listeners.keydown !== undefined, true);
  assert.equal(deps.timelineResult.innerHTML, 'timeline:1');
  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState())), {
    reservationId: 'reservation-7',
    limit: 100,
    operations: [{ action: 'wake', success: true }],
    base: {
      reservation: { reservationId: 'reservation-7' },
      operations: [{ action: 'wake', success: true }],
      pagination: { offset: 0, returned: 1, total: 1, hasMore: false },
    },
    pagination: {
      offset: 0,
      returned: 1,
      total: 1,
      hasMore: false,
      limit: 100,
      nextOffset: 1,
    },
    nextOffset: 1,
    loading: false,
  });
  assert.deepEqual(deps.events, [['Timeline loaded', 'success']]);
});

test('keeps access failures visible and avoids rendering an unauthorized timeline', async () => {
  const module = loadModule();
  const deps = dependencies({
    fetchImpl: async () => response({}, 403),
  });
  const controller = module.createController(deps);

  await controller.fetchTimeline();

  assert.equal(deps.timelineResult.textContent, 'Access denied: /ops blocked by Lab Manager access policy');
  assert.equal(deps.timelineResult.innerHTML, '');
  assert.deepEqual(deps.events, [[
    'Access denied: /ops blocked by Lab Manager access policy',
    'error',
  ]]);
});

test('loads more timeline operations through the next pagination offset', async () => {
  const module = loadModule();
  const requests = [];
  const pages = [
    response({
      operations: [{ action: 'wake' }],
      pagination: { offset: 0, returned: 1, total: 2, hasMore: true },
    }),
    response({
      operations: [{ action: 'prepare' }],
      pagination: { offset: 1, returned: 1, total: 2, hasMore: false },
    }),
  ];
  const deps = dependencies({
    fetchImpl: async (url) => {
      requests.push(url);
      return pages.shift();
    },
    renderTimelineMarkup: data => data.operations.map(operation => operation.action).join(','),
  });
  deps.timelineResult.querySelector = selector => selector === '#timelineLoadMoreBtn'
    ? element()
    : null;
  const controller = module.createController(deps);

  await controller.fetchTimeline();
  await controller.loadMoreTimeline();

  assert.match(requests[0], /offset=0/);
  assert.match(requests[1], /offset=1/);
  assert.equal(deps.timelineResult.innerHTML, 'wake,prepare');
  assert.deepEqual(
    JSON.parse(JSON.stringify(controller.getState().operations)),
    [{ action: 'wake' }, { action: 'prepare' }],
  );
});
