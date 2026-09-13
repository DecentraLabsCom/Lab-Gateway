import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const accessScriptPath = new URL('web/assets/js/lab-manager-notifications-access.js', repoRoot);
const configScriptPath = new URL('web/assets/js/lab-manager-notifications-config.js', repoRoot);
const scriptPath = new URL('web/assets/js/lab-manager-notifications.js', repoRoot);

const fieldIds = [
  'driver', 'enabled', 'from', 'fromName', 'defaultTo', 'timezone',
  'smtpHost', 'smtpPort', 'smtpUser', 'smtpPass', 'smtpStartTls', 'smtpSection',
  'graphTenant', 'graphClientId', 'graphClientSecret', 'graphFrom', 'graphSection',
  'driverSummary', 'configStatus', 'configModal', 'configureBtn', 'closeModal',
  'cancelModal', 'btnTestLoad', 'saveConfigBtn', 'btnTestEmail',
  'notificationsAccessGate', 'notificationsConfigContent', 'unlockNotificationsBtn',
  'smtpPasswordHint', 'graphClientSecretHint',
];

function createElement(id) {
  const listeners = new Map();
  const classes = new Set();
  const element = {
    id,
    value: '',
    checked: false,
    disabled: false,
    hidden: false,
    textContent: '',
    title: '',
    tabIndex: -1,
    innerHTML: '',
    style: {},
    options: [],
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      toggle: (name, force) => {
        const enabled = force === undefined ? !classes.has(name) : Boolean(force);
        if (enabled) classes.add(name);
        else classes.delete(name);
        return enabled;
      },
      contains: (name) => classes.has(name),
    },
    addEventListener: (type, handler) => listeners.set(type, handler),
    appendChild: (child) => {
      element.options.push(child);
      return child;
    },
    setAttribute: () => {},
    dispatchEvent: (event) => listeners.get(event.type)?.(event),
    click: () => listeners.get('click')?.({ preventDefault() {} }),
  };
  return element;
}

function loadNotifications({ billingResponse, testResponse } = {}) {
  const elements = new Map(fieldIds.map((id) => [id, createElement(id)]));
  const document = {
    querySelector: (selector) => selector.startsWith('#')
      ? elements.get(selector.slice(1))
      : null,
    createElement: (tagName) => createElement(tagName),
  };
  const fetchCalls = [];
  const toasts = [];
  const promptCalls = [];
  const window = {
    AuthTokenHandler: {
      showTokenModal: (...args) => promptCalls.push(args),
      getTokenConfigForPath: () => ({ key: 'billing', login: '/admin/login' }),
    },
  };
  const context = vm.createContext({
    document,
    window,
    console,
    Intl,
    Promise,
    setTimeout,
    clearTimeout,
    fetch: () => Promise.reject(new Error('unexpected fetch')),
    Option: function Option(text, value) {
      this.textContent = text;
      this.value = value;
    },
  });

  const defaultResponse = {
    ok: true,
    status: 200,
    json: async () => ({ config: {} }),
  };
  const fetchImpl = (url, options = {}) => {
    fetchCalls.push({ url: String(url), options });
    if (String(url) === '/billing/admin/notifications/test') {
      return Promise.resolve(testResponse || defaultResponse);
    }
    return Promise.resolve(billingResponse || defaultResponse);
  };

  vm.runInContext(fs.readFileSync(accessScriptPath, 'utf8'), context, {
    filename: 'lab-manager-notifications-access.js',
  });
  vm.runInContext(fs.readFileSync(configScriptPath, 'utf8'), context, {
    filename: 'lab-manager-notifications-config.js',
  });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-notifications.js',
  });

  const controller = context.window.LabManagerNotifications.createController({
    fetchImpl,
    showToast: (message, type) => toasts.push({ message, type }),
    getAuthTokenHandler: () => context.window.AuthTokenHandler,
  });
  controller.initialize();
  return { controller, elements, fetchCalls, toasts, promptCalls };
}

test('preserves notification access loading, lock state and status lifecycle', async () => {
  const { controller, elements, fetchCalls, toasts } = loadNotifications({
    billingResponse: {
      ok: true,
      status: 200,
      json: async () => ({ config: { driver: 'SMTP', enabled: true } }),
    },
  });

  assert.equal(elements.get('notificationsConfigContent').hidden, true);
  assert.equal(elements.get('saveConfigBtn').disabled, true);
  assert.equal(await controller.requestAccess(), true);
  assert.equal(fetchCalls[0].url, '/billing/admin/notifications');
  assert.equal(fetchCalls[0].options.credentials, 'include');
  assert.equal(elements.get('notificationsConfigContent').hidden, false);
  assert.equal(elements.get('driver').value, 'SMTP');
  assert.equal(elements.get('configStatus').textContent, 'Loaded');
  assert.deepEqual(toasts.at(-1), { message: 'Configuration loaded', type: 'success' });
});

test('preserves notification save payloads and omits blank secrets', async () => {
  const { controller, elements, fetchCalls } = loadNotifications({
    billingResponse: {
      ok: true,
      status: 200,
      json: async () => ({ config: { smtp: { passwordConfigured: true }, graph: { clientSecretConfigured: true } } }),
    },
  });

  await controller.requestAccess();
  elements.get('smtpPass').value = '   ';
  elements.get('graphClientSecret').value = '';
  await controller.saveConfig();

  const saveCall = fetchCalls.find(({ options }) => options.method === 'POST');
  assert.ok(saveCall);
  assert.equal(saveCall.url, '/billing/admin/notifications');
  const payload = JSON.parse(saveCall.options.body);
  assert.equal(Object.hasOwn(payload.smtp, 'password'), false);
  assert.equal(Object.hasOwn(payload.graph, 'clientSecret'), false);
});

test('preserves the protected test-email request and modal access guard', async () => {
  const { controller, elements, fetchCalls, promptCalls } = loadNotifications({
    billingResponse: {
      ok: false,
      status: 401,
      json: async () => ({}),
    },
    testResponse: {
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    },
  });

  elements.get('configureBtn').click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(promptCalls.length, 1);
  assert.equal(elements.get('configModal').classList.contains('show'), false);

  const access = loadNotifications({
    billingResponse: {
      ok: true,
      status: 200,
      json: async () => ({ config: {} }),
    },
    testResponse: {
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    },
  });
  await access.controller.requestAccess();
  await access.controller.sendTestEmail();
  const testCall = access.fetchCalls.find(({ url }) => url === '/billing/admin/notifications/test');
  assert.ok(testCall);
  assert.equal(testCall.options.method, 'POST');
});
