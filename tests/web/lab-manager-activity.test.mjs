import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-activity.js', repoRoot);

function createElement(tagName = 'div') {
  const listeners = new Map();
  let innerHTML = '';
  const element = {
    tagName,
    children: [],
    className: '',
    disabled: false,
    scrollTop: 0,
    textContent: '',
    type: '',
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    click() {
      listeners.get('click')?.({ preventDefault() {} });
    },
  };
  Object.defineProperty(element, 'innerHTML', {
    get: () => innerHTML,
    set: (value) => {
      innerHTML = String(value ?? '');
      element.children = [];
      element.scrollTop = 0;
    },
  });
  return element;
}

function loadActivityController({ fetchImpl }) {
  const activityFeed = createElement();
  const document = {
    querySelector(selector) {
      assert.equal(selector, '#activityFeedList');
      return activityFeed;
    },
    createElement,
  };
  const window = {};
  const context = vm.createContext({ window, URLSearchParams });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-activity.js',
  });

  const toasts = [];
  const controller = window.LabManagerActivity.createController({
    document,
    fetchImpl,
    escapeHtml: (value) => String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;'),
    normalizePagination: (pagination, offset, returned, limitFallback) => ({
      limit: Number(pagination?.limit) || limitFallback,
      offset,
      returned,
      total: Number(pagination?.total) || offset + returned,
      nextOffset: Number(pagination?.nextOffset) || offset + returned,
      hasMore: pagination?.hasMore === true,
    }),
    showToast: (message, type) => toasts.push({ message, type }),
    logger: { error() {} },
  });

  return { activityFeed, controller, toasts };
}

test('loads and appends activity pages without changing request options', async () => {
  const calls = [];
  const pages = [
    {
      operations: [{ action: 'start', status: 'ok', host: 'host<&', createdAt: '2026-09-12T10:00:00Z', message: '<unsafe>' }],
      pagination: { limit: 8, total: 2, nextOffset: 1, hasMore: true },
    },
    {
      operations: [{ action: 'stop', status: 'ok', host: 'host-2', createdAt: '2026-09-12T11:00:00Z', message: 'done' }],
      pagination: { limit: 8, total: 2, nextOffset: 2, hasMore: false },
    },
  ];
  const { activityFeed, controller, toasts } = loadActivityController({
    fetchImpl: async (url, options) => {
      calls.push({ url: String(url), options });
      return { ok: true, status: 200, json: async () => pages.shift() };
    },
  });

  await controller.loadActivityFeed(false, { skipAuthPrompt: true });

  assert.equal(calls[0].url, '/ops/api/operations/recent?limit=8&offset=0');
  assert.equal(calls[0].options.credentials, 'include');
  assert.equal(calls[0].options.skipAuthPrompt, true);
  assert.equal(activityFeed.children.length, 2);
  assert.match(activityFeed.children[0].innerHTML, /&lt;unsafe&gt;/);
  assert.equal(activityFeed.children[1].children[0].textContent, 'Showing 1-1 of 2');

  const loadMoreButton = activityFeed.children[1].children[1];
  assert.equal(loadMoreButton.disabled, false);
  activityFeed.scrollTop = 120;
  loadMoreButton.click();
  await new Promise((resolve) => setImmediate(() => setImmediate(resolve)));

  assert.equal(calls[1].url, '/ops/api/operations/recent?limit=8&offset=1');
  assert.equal(activityFeed.children.length, 3);
  assert.match(activityFeed.children[0].innerHTML, /start/);
  assert.match(activityFeed.children[1].innerHTML, /stop/);
  assert.equal(activityFeed.children[2].className, 'activity-pagination');
  assert.equal(activityFeed.children[2].children.length, 1);
  assert.equal(activityFeed.children[2].children[0].textContent, 'Showing 1-2 of 2');
  assert.equal(activityFeed.scrollTop, 120);
  assert.deepEqual(toasts, [{ message: 'More activity loaded', type: 'success' }]);
});

test('preserves loaded activity pages and scroll position during background refresh', async () => {
  const calls = [];
  const firstPage = Array.from({ length: 8 }, (_, index) => ({
    action: `operation-${index + 1}`,
    status: 'ok',
    host: 'host-1',
    createdAt: '2026-09-12T10:00:00Z',
    message: 'done',
  }));
  const secondPage = Array.from({ length: 5 }, (_, index) => ({
    action: `operation-${index + 9}`,
    status: 'ok',
    host: 'host-1',
    createdAt: '2026-09-12T11:00:00Z',
    message: 'done',
  }));
  const refreshedOperations = [...firstPage, ...secondPage];
  const pages = [
    {
      operations: firstPage,
      pagination: { limit: 8, total: 13, nextOffset: 8, hasMore: true },
    },
    {
      operations: secondPage,
      pagination: { limit: 8, total: 13, nextOffset: 13, hasMore: false },
    },
    {
      operations: refreshedOperations,
      pagination: { limit: 13, total: 13, nextOffset: 13, hasMore: false },
    },
  ];
  const { activityFeed, controller } = loadActivityController({
    fetchImpl: async (url) => {
      calls.push(String(url));
      return { ok: true, status: 200, json: async () => pages.shift() };
    },
  });

  await controller.loadActivityFeed();
  await controller.loadActivityFeed(true);
  activityFeed.scrollTop = 90;
  await controller.loadActivityFeed(false, { preserveLoaded: true });

  assert.equal(calls[2], '/ops/api/operations/recent?limit=13&offset=0');
  assert.equal(activityFeed.children.length, 14);
  assert.equal(activityFeed.children[13].children[0].textContent, 'Showing 1-13 of 13');
  assert.equal(activityFeed.scrollTop, 90);
});

test('renders escaped activity errors without leaking server text', async () => {
  const { activityFeed, controller } = loadActivityController({
    fetchImpl: async () => ({ ok: false, status: 503, json: async () => ({}) }),
  });

  await controller.loadActivityFeed();

  assert.equal(
    activityFeed.innerHTML,
    '<div class="empty">Unable to load activity: HTTP 503</div>',
  );
});
