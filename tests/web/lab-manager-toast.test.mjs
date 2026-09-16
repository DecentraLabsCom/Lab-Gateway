import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/core/toast.js', repoRoot);

function loadToastController() {
  const toast = { textContent: '', className: '' };
  const document = {
    querySelector(selector) {
      assert.equal(selector, '#toast');
      return toast;
    },
  };
  const window = {};
  const context = vm.createContext({ window });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'toast.js',
  });

  const timeoutCallbacks = [];
  const controller = window.LabManagerToast.createController({
    document,
    setTimeoutImpl: (callback, delay) => {
      timeoutCallbacks.push({ callback, delay });
    },
  });
  return { controller, toast, timeoutCallbacks, window };
}

test('renders toast text and success styling, then clears it after the existing delay', () => {
  const { controller, toast, timeoutCallbacks } = loadToastController();

  controller.showToast('Configuration saved', 'success');

  assert.equal(toast.textContent, 'Configuration saved');
  assert.equal(toast.className, 'toast show success');
  assert.equal(timeoutCallbacks.length, 1);
  assert.equal(timeoutCallbacks[0].delay, 2500);

  timeoutCallbacks[0].callback();
  assert.equal(toast.className, 'toast');
});

test('keeps error styling and treats other types as informational', () => {
  const { controller, toast } = loadToastController();

  controller.showToast('Request failed', 'error');
  assert.equal(toast.className, 'toast show error');

  controller.showToast('Working');
  assert.equal(toast.className, 'toast show ');
});

test('exposes one shared controller for all Lab Manager composition roots', () => {
  const { toast, timeoutCallbacks, window } = loadToastController();
  const first = window.LabManagerToast.getDefaultController({
    document: {
      querySelector: () => toast,
    },
    setTimeoutImpl: (callback, delay) => timeoutCallbacks.push({ callback, delay }),
  });
  const second = window.LabManagerToast.getDefaultController({
    document: {
      querySelector: () => toast,
    },
    setTimeoutImpl: () => {},
  });

  assert.strictEqual(first, second);
});
