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
    logger: { error() {} },
  });

  return { activityFeed, controller };
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
  const { activityFeed, controller } = loadActivityController({
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

  const loadMoreButton = activityFeed.children[1].children[1];
  loadMoreButton.click();
  await new Promise((resolve) => setImmediate(() => setImmediate(resolve)));

  assert.equal(calls[1].url, '/ops/api/operations/recent?limit=8&offset=1');
  assert.equal(activityFeed.children.length, 3);
  assert.match(activityFeed.children[0].innerHTML, /start/);
  assert.match(activityFeed.children[1].innerHTML, /stop/);
  assert.equal(activityFeed.children[2].className, 'activity-pagination');
  assert.equal(activityFeed.children[2].children.length, 1);
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
