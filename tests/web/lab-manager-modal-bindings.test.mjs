import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-modal-bindings.js', repoRoot);

function loadModule() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-modal-bindings.js',
  });
  return context.window.LabManagerModalBindings;
}

function field(events, name) {
  return {
    addEventListener(type, callback) {
      events.push({ callback, name, type });
    },
  };
}

test('binds host and WinRM modal controls without embedding modal behavior', () => {
  const events = [];
  const callbacks = {
    closeProvision: () => {},
    saveProvision: () => {},
    closeCredentials: () => {},
    saveCredentials: () => {},
    closeTrust: () => {},
    previewTrust: () => {},
    saveTrust: () => {},
    verifyTrust: () => {},
    deleteTrust: () => {},
    trustCertificateSelected: () => {},
    trustFingerprintChanged: () => {},
    closeEdit: () => {},
    saveEdit: () => {},
  };
  const fields = Object.fromEntries([
    ['closeProvision', 'click'],
    ['cancelProvision', 'click'],
    ['saveProvision', 'click'],
    ['closeCredentials', 'click'],
    ['cancelCredentials', 'click'],
    ['saveCredentials', 'click'],
    ['closeTrust', 'click'],
    ['cancelTrust', 'click'],
    ['previewTrust', 'click'],
    ['saveTrust', 'click'],
    ['verifyTrust', 'click'],
    ['deleteTrust', 'click'],
    ['trustCertificate', 'change'],
    ['trustFingerprint', 'change'],
    ['closeEdit', 'click'],
    ['cancelEdit', 'click'],
    ['saveEdit', 'click'],
  ].map(([name]) => [name, field(events, name)]));

  loadModule().createController({ fields, callbacks }).bind();

  assert.deepEqual(
    events.map(({ name, type }) => [name, type]),
    [
      ['closeProvision', 'click'],
      ['cancelProvision', 'click'],
      ['saveProvision', 'click'],
      ['closeCredentials', 'click'],
      ['cancelCredentials', 'click'],
      ['saveCredentials', 'click'],
      ['closeTrust', 'click'],
      ['cancelTrust', 'click'],
      ['previewTrust', 'click'],
      ['saveTrust', 'click'],
      ['verifyTrust', 'click'],
      ['deleteTrust', 'click'],
      ['trustCertificate', 'change'],
      ['trustFingerprint', 'change'],
      ['closeEdit', 'click'],
      ['cancelEdit', 'click'],
      ['saveEdit', 'click'],
    ],
  );
  assert.equal(events[0].callback, callbacks.closeProvision);
  assert.equal(events[2].callback, callbacks.saveProvision);
  assert.equal(events[12].callback, callbacks.trustCertificateSelected);
  assert.equal(events[16].callback, callbacks.saveEdit);
});
