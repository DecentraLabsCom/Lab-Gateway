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
    timezone: field(),
    status: field(),
    saveButton: field({ disabled: false }),
    wakeButton: field({ disabled: false }),
  };
}

test('loads and saves a Wake Ops schedule through the dialog API', async () => {
  const module = loadModule();
  const form = fields();
  const requests = [];
  const events = [];
  const controller = module.createController({
    fields: form,
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
  assert.match(form.status.textContent, /Wake manual completado|evidencia/i);
});
