import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-power-renderers.js', repoRoot);

function loadRenderers() {
  const context = vm.createContext({ console, window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-power-renderers.js',
  });
  return context.window.LabManagerPowerRenderers;
}

function renderer() {
  return loadRenderers().createController({
    escapeHtml: value => String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;'),
  });
}

test('renders power controller rows with discovery, outlet actions and escaping', () => {
  const rows = renderer().renderPowerControllerRowsMarkup([{
    id: 'pdu-<&',
    name: 'Bench <PDU>',
    driver: 'mock',
    host: '',
    discovery: { reachable: true },
    outlets: [{
      outlet: '1<&',
      displayName: 'PLC <main>',
      state: 'on',
      protected: true,
      critical: true,
    }],
  }], false, false);

  assert.equal(rows.length, 1);
  assert.match(rows[0], /Bench &lt;PDU&gt;/);
  assert.match(rows[0], /pdu-&lt;&amp;/);
  assert.match(rows[0], /reachable/);
  assert.match(rows[0], /PLC &lt;main&gt;/);
  assert.match(rows[0], /data-power-action="cycle"/);
  assert.match(rows[0], /data-protected="true"/);
  assert.doesNotMatch(rows[0], /<PDU>/);
});

test('keeps power controller status and empty outlet markup stable', () => {
  const renderers = renderer();
  const rows = renderers.renderPowerControllerRowsMarkup([{
    id: 'pdu-1',
    driver: 'mock',
    discovery: { errorCode: 'timeout' },
    outlets: [],
  }], false, true);

  assert.match(rows[0], /status unavailable/);
  assert.match(rows[0], /No outlets configured/);
  assert.equal(renderers.renderPowerControllerRowsMarkup([], false, false).length, 0);
});

test('renders compatible power credential options and preserves unavailable selection', () => {
  const html = renderer().renderPowerControllerCredentialOptionsMarkup('netio-json', 'snmp-old', [
    { credentialRef: 'netio-main', type: 'netio-http-basic' },
    { credentialRef: 'snmp-old', type: 'snmpv3' },
    { credentialRef: 'empty', type: '' },
  ]);

  assert.match(html, /No credential \(optional\)/);
  assert.match(html, /snmp-old — unavailable for this driver/);
  assert.match(html, /netio-main · netio-http-basic/);
  assert.doesNotMatch(html, /value="empty"/);
});

test('renders policy steps with controller and outlet choices', () => {
  const renderers = renderer();
  const html = renderers.renderPowerPolicyStepsMarkup([{
    phase: 'start',
    controllerId: 'pdu-1',
    outlet: '1',
    action: 'on',
    desiredState: 'on',
    logicalName: '<PLC>',
    offSeconds: 10,
    delayBeforeSeconds: 1,
    delayAfterSeconds: 2,
    timeoutSeconds: 20,
    retryCount: 1,
    required: true,
    readBackRequired: false,
    allowProtected: true,
    conditionsText: '{"ready":true}',
  }], [{
    id: 'pdu-1',
    name: 'Bench PDU',
    outlets: [{ outlet: '1', logicalName: 'PLC' }],
  }]);

  assert.match(html, /data-step-field="phase"/);
  assert.match(html, /data-step-drag-handle/);
  assert.match(html, /draggable="true"/);
  assert.match(html, /Step 1/);
  assert.doesNotMatch(html, /data-step-field="sequence"/);
  assert.match(html, /value="pdu-1" selected/);
  assert.match(html, /value="1" selected/);
  assert.match(html, /&lt;PLC&gt;/);
  assert.match(html, /data-step-field="allowProtected" checked/);
  assert.doesNotMatch(html, /data-step-field="readBackRequired" checked/);
  assert.match(renderers.renderPowerPolicyStepsMarkup([], []), /No steps configured/);
});

test('renders controller outlet drafts with escaped editable values', () => {
  const html = renderer().renderPowerControllerOutletsMarkup([{
    outlet: '1',
    displayName: '<PLC>',
    logicalName: 'plc&main',
    defaultState: 'on',
    protected: true,
    critical: false,
  }]);

  assert.match(html, /value="&lt;PLC&gt;"/);
  assert.match(html, /value="plc&amp;main"/);
  assert.match(html, /value="on" selected/);
  assert.match(html, /data-controller-outlet-field="protected" checked/);
});

test('renders physical outputs from the device and hides local inventory controls', () => {
  const html = renderer().renderPowerControllerOutletsMarkup([{
    outlet: '1',
    deviceName: '<PLC>',
    deviceConfig: {
      powerOnDelaySeconds: 5,
      powerOffDelaySeconds: 30,
      rebootDurationSeconds: 10,
    },
    deviceConfigFields: ['name', 'powerOnDelaySeconds', 'powerOffDelaySeconds', 'rebootDurationSeconds'],
    deviceConfigWritable: true,
    deviceManaged: true,
    logicalName: 'plc',
    defaultState: 'off',
    protected: false,
    critical: false,
  }], { deviceManaged: true });

  assert.match(html, /Device output name/);
  assert.match(html, /value="&lt;PLC&gt;"/);
  assert.match(html, /data-controller-device-config-field="powerOnDelaySeconds"/);
  assert.match(html, /value="30"/);
  assert.doesNotMatch(html, /data-controller-outlet-action="remove"/);
  assert.match(html, /data-controller-outlet-field="outlet"[^>]+readonly/);
});

test('renders NETIO physical output names as read-only', () => {
  const html = renderer().renderPowerControllerOutletsMarkup([{
    outlet: '2',
    deviceName: 'HMI',
    deviceConfigFields: ['name'],
    deviceConfigWritable: false,
    deviceManaged: true,
  }], { deviceManaged: true });

  assert.match(html, /Device output name \(read-only\)/);
  assert.match(html, /data-controller-outlet-field="deviceName"[^>]+readonly/);
  assert.doesNotMatch(html, /data-controller-outlet-action="remove"/);
});
