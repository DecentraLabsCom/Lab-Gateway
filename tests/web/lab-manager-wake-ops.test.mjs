import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-wake-ops.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-wake-ops.js',
  });
  return context.window.LabManagerWakeOps;
}

function field(overrides = {}) {
  return {
    value: '',
    checked: false,
    textContent: '',
    hidden: false,
    classList: { add() {}, remove() {} },
    ...overrides,
  };
}

function documentImpl() {
  return {
    createElement: () => ({}),
  };
}

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function fields() {
  return {
    modal: field(),
    host: field(),
    enabled: field(),
    day: field(),
    hour: field(),
    minute: field(),
    timezone: field({
      options: [],
      appendChild(option) { this.options.push(option); },
    }),
    status: field(),
    saveButton: field({ disabled: false }),
    wakeButton: field({ disabled: false, innerHTML: '<i class="fas fa-bolt"></i> Wake' }),
  };
}

test('loads and saves a Wake Ops schedule through the dialog API', async () => {
  const module = loadModule();
  const form = fields();
  const requests = [];
  const events = [];
  const controller = module.createController({
    fields: form,
    documentImpl: documentImpl(),
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      if (options?.method === 'PUT') {
        return response({
          schedule: {
            enabled: false,
            dayOfWeek: 2,
            hour: 9,
            minute: 30,
            timezone: 'UTC',
          },
        });
      }
      return response({
        schedule: {
          enabled: true,
          dayOfWeek: 6,
          hour: 8,
          minute: 0,
          timezone: 'Europe/Madrid',
        },
        evidence: { state: 'verified', ageSeconds: 60, validForSeconds: 604800 },
      });
    },
    callbacks: { showToast: (...args) => events.push(args) },
  });

  await controller.open('station/7');

  assert.equal(form.modal.hidden, false);
  assert.equal(form.host.textContent, 'station/7');
  assert.equal(form.enabled.checked, true);
  assert.equal(form.day.value, '6');
  assert.equal(form.timezone.value, 'Europe/Madrid');
  assert.equal(form.timezone.options[0].value, '');
  assert.equal(form.timezone.options[0].textContent, 'Use Lab Gateway timezone');
  assert.ok(form.timezone.options.length > 400);
  assert.ok(form.timezone.options.some(option => option.value === 'Pacific/Wallis'));

  form.enabled.checked = false;
  form.day.value = '2';
  form.hour.value = '09';
  form.minute.value = '30';
  form.timezone.value = 'UTC';
  await controller.save();

  assert.equal(requests[0].url, '/ops/api/wake-ops/station%2F7');
  assert.equal(requests[1].options.method, 'PUT');
  assert.deepEqual(JSON.parse(requests[1].options.body), {
    enabled: false,
    dayOfWeek: 2,
    hour: 9,
    minute: 30,
    timezone: 'UTC',
  });
  assert.deepEqual(events, [['Wake Ops schedule saved for station/7', 'success']]);
});

test('keeps manual Wake separate from weekly schedule changes and reports evidence', async () => {
  const module = loadModule();
  const form = fields();
  const requests = [];
  const controller = module.createController({
    fields: form,
    documentImpl: documentImpl(),
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      if (url.endsWith('/wake')) return response({ success: true, status: 'completed' });
      return response({
        schedule: { enabled: true, dayOfWeek: 6, hour: 8, minute: 0, timezone: 'UTC' },
        evidence: { state: 'unknown', validForSeconds: 604800 },
      });
    },
    callbacks: { showToast: () => {} },
  });

  await controller.open('station-7');
  await controller.manualWake();

  assert.equal(requests[1].url, '/ops/api/wake-ops/station-7/wake');
  assert.equal(requests[1].options.method, 'POST');
  assert.match(form.status.textContent, /manual Wake|evidence/i);
});

test('shows a spinner and loading toast until a manual Wake succeeds', async () => {
  const module = loadModule();
  const form = fields();
  const events = [];
  let resolveWake;
  const wakeResponse = new Promise(resolve => { resolveWake = resolve; });
  const controller = module.createController({
    fields: form,
    documentImpl: documentImpl(),
    fetchImpl: async (url) => {
      if (url.endsWith('/wake')) return wakeResponse;
      return response({
        schedule: { enabled: true, dayOfWeek: 6, hour: 8, minute: 0, timezone: 'UTC' },
        evidence: { state: 'verified', ageSeconds: 0, validForSeconds: 604800 },
      });
    },
    callbacks: { showToast: (...args) => events.push(args) },
  });

  await controller.open('station-7');
  const wakePromise = controller.manualWake();

  assert.equal(form.wakeButton.disabled, true);
  assert.match(form.wakeButton.innerHTML, /wake-ops-spinner/);
  assert.equal(form.status.textContent, 'Sending Wake to station-7...');
  assert.deepEqual(events.at(-1), ['Sending Wake to station-7...', 'loading']);

  resolveWake(response({ success: true }));
  assert.equal(await wakePromise, true);
  assert.equal(form.wakeButton.disabled, false);
  assert.equal(form.wakeButton.innerHTML, '<i class="fas fa-bolt"></i> Wake');
  assert.equal(form.status.textContent, 'Manual Wake completed for station-7');
  assert.deepEqual(events.at(-1), ['Manual Wake completed for station-7', 'success']);
});

test('replaces the loading message with an error when manual Wake fails', async () => {
  const module = loadModule();
  const form = fields();
  const events = [];
  const controller = module.createController({
    fields: form,
    documentImpl: documentImpl(),
    fetchImpl: async (url) => {
      if (url.endsWith('/wake')) return response({ success: false, message: 'Station did not respond' });
      return response({
        schedule: { enabled: true, dayOfWeek: 6, hour: 8, minute: 0, timezone: 'UTC' },
        evidence: { state: 'unknown', validForSeconds: 604800 },
      });
    },
    callbacks: { showToast: (...args) => events.push(args) },
    logger: { error: () => {} },
  });

  await controller.open('station-7');
  assert.equal(await controller.manualWake(), false);

  assert.equal(form.wakeButton.disabled, false);
  assert.equal(form.wakeButton.innerHTML, '<i class="fas fa-bolt"></i> Wake');
  assert.equal(form.status.textContent, 'Manual Wake not completed: Station did not respond');
  assert.deepEqual(events.slice(-2), [
    ['Sending Wake to station-7...', 'loading'],
    ['Manual Wake failed for station-7: Station did not respond', 'error'],
  ]);
});

test('reports Wake Ops loading errors in English', async () => {
  const module = loadModule();
  const form = fields();
  const controller = module.createController({
    fields: form,
    documentImpl: documentImpl(),
    fetchImpl: async () => response({ error: 'Internal server error' }, 500),
    callbacks: { showToast: () => {} },
    logger: { error: () => {} },
  });

  await controller.open('station-7');

  assert.equal(form.status.textContent, 'Unable to load Wake Ops: Internal server error');
});

test('keeps the Wake Ops dialog in English and uses the standard toggle layout', () => {
  const html = fs.readFileSync(new URL('web/lab-manager/index.html', repoRoot), 'utf8');
  const css = fs.readFileSync(new URL('web/assets/css/lab-manager.css', repoRoot), 'utf8');

  assert.match(html, /class="wake-ops-summary"/);
  assert.match(html, /class="wake-ops-status"/);
  assert.match(html, /class="switch" for="wakeOpsEnabled"/);
  assert.match(html, /class="wake-ops-settings-grid"/);
  assert.match(html, /<select id="wakeOpsTimezone"><\/select>/);
  assert.doesNotMatch(html, /Activar verificaci|La evidencia de WoL es|Hora local|Zona horaria del Lab Gateway/);
  assert.match(css, /\.wake-ops-enabled-field\s*\{[\s\S]*?flex-direction:\s*column;/);
  assert.match(css, /\.wake-ops-spinner\s*\{[\s\S]*?animation:\s*wake-ops-spin/);
});
