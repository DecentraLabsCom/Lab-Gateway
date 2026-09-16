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
      logicalName: 'PLC <main>',
      state: 'on',
      protected: true,
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
    stepLabel: '<PLC>',
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
  assert.ok(
    html.indexOf('data-step-field="stepLabel"') < html.indexOf('data-step-field="phase"'),
    'Step label should be the first step field',
  );
  assert.match(html, /value="pdu-1" selected/);
  assert.match(html, /value="1" selected/);
  assert.match(html, /&lt;PLC&gt;/);
  assert.match(html, /Step label/);
  assert.doesNotMatch(html, /Desired state/);
  assert.doesNotMatch(html, /data-step-field="offSeconds"/);
  assert.match(html, /data-step-field="allowProtected" checked/);
  assert.doesNotMatch(html, /data-step-field="readBackRequired" checked/);
  assert.match(html, /Confirm state/);
  assert.doesNotMatch(html, /Read back state/);
  assert.doesNotMatch(html, /power-policy-step-options/);
  for (const [label, field, tooltip] of [
    ['Delay before', 'delayBeforeSeconds', 'Delay before in seconds'],
    ['Delay after', 'delayAfterSeconds', 'Delay after in seconds'],
    ['Timeout', 'timeoutSeconds', 'Timeout in seconds'],
  ]) {
    assert.match(
      html,
      new RegExp(`<label class="field" title="${tooltip}">[\\s\\S]*<span>${label}<\\/span>[\\s\\S]*data-step-field="${field}"[^>]+title="${tooltip}"`),
    );
  }
  for (const [label, field, id] of [
    ['Required', 'required', 'powerPolicyStep0Required'],
    ['Confirm state', 'readBackRequired', 'powerPolicyStep0ConfirmState'],
    ['Allow protected outlet', 'allowProtected', 'powerPolicyStep0AllowProtected'],
  ]) {
    assert.match(
      html,
      new RegExp(`<div class="field toggle-field power-checkbox-field">[\\s\\S]*<span>${label}<\\/span>[\\s\\S]*<label class="switch" for="${id}">[\\s\\S]*<input type="checkbox" id="${id}" data-step-field="${field}"[\\s\\S]*<span class="slider"><\\/span>`),
    );
  }
  assert.doesNotMatch(html, /Delay before \(seconds\)|Delay after \(seconds\)|Timeout \(seconds\)/);
  const policyFieldsStart = html.indexOf('<div class="form-grid power-policy-step-fields">');
  const policyConditionsStart = html.indexOf('power-policy-conditions');
  for (const [label, field] of [
    ['Required', 'required'],
    ['Confirm state', 'readBackRequired'],
    ['Allow protected outlet', 'allowProtected'],
  ]) {
    const labelIndex = html.indexOf(`<span>${label}</span>`);
    const checkboxIndex = html.indexOf(`data-step-field="${field}"`, labelIndex);
    assert.ok(
      labelIndex > policyFieldsStart && checkboxIndex > labelIndex && checkboxIndex < policyConditionsStart,
      `${label} should be a vertical checkbox field in the step grid`,
    );
  }
  assert.match(renderers.renderPowerPolicyStepsMarkup([], []), /No steps configured/);
});

test('renders cycle timing only for cycle actions', () => {
  const renderers = renderer();
  const html = renderers.renderPowerPolicyStepsMarkup([{
    phase: 'start',
    controllerId: 'pdu-1',
    outlet: '1',
    action: 'cycle',
    stepLabel: 'Restart PLC',
    offSeconds: 15,
  }], [{ id: 'pdu-1', outlets: [{ outlet: '1' }] }]);

  assert.match(html, /<label class="field" title="Cycle off time in seconds">[\s\S]*<span>Cycle off time<\/span>[\s\S]*data-step-field="offSeconds"[^>]+title="Cycle off time in seconds"/);
  assert.doesNotMatch(html, /Cycle off time \(seconds\)/);
  assert.match(html, /value="15"/);
});

test('renders controller outlet drafts with escaped editable values', () => {
  const html = renderer().renderPowerControllerOutletsMarkup([{
    outlet: '1',
    logicalName: '<PLC>',
    defaultState: 'on',
    protected: true,
  }]);

  assert.match(html, /value="&lt;PLC&gt;"/);
  assert.match(html, /Name/);
  assert.match(html, /value="on" selected/);
  assert.match(html, /<div class="field toggle-field power-checkbox-field power-controller-outlet-protected-field">[\s\S]*<span>Protected<\/span>[\s\S]*<label class="switch" for="powerControllerOutlet0Protected">[\s\S]*<input type="checkbox" id="powerControllerOutlet0Protected" data-controller-outlet-field="protected" checked[\s\S]*<span class="slider"><\/span>/);
  assert.doesNotMatch(html, /check-field/);
  const fieldsStart = html.indexOf('<div class="form-grid power-controller-outlet-fields">');
  const protectedLabelIndex = html.indexOf('<span>Protected</span>');
  const protectedIndex = html.indexOf('data-controller-outlet-field="protected" checked');
  const fieldsEnd = html.indexOf('<div class="power-controller-outlet-options">');
  assert.ok(
    fieldsStart >= 0
      && protectedLabelIndex > fieldsStart
      && protectedIndex > protectedLabelIndex
      && (fieldsEnd < 0 || protectedIndex < fieldsEnd),
  );
  assert.doesNotMatch(html, /Logical name/);
  assert.doesNotMatch(html, /Critical/);
  assert.doesNotMatch(html, /power-controller-outlet-options/);
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
  }], { deviceManaged: true });

  assert.match(html, /<span>Name<\/span>/);
  assert.match(html, /value="&lt;PLC&gt;"/);
  assert.match(html, /<label class="field" title="Power-on delay in seconds">[\s\S]*<span>Power-on delay<\/span>[\s\S]*data-controller-device-config-field="powerOnDelaySeconds"[^>]+title="Power-on delay in seconds"/);
  assert.match(html, /<label class="field" title="Power-off delay in seconds">[\s\S]*<span>Power-off delay<\/span>[\s\S]*data-controller-device-config-field="powerOffDelaySeconds"[^>]+title="Power-off delay in seconds"/);
  assert.match(html, /<label class="field" title="Reboot duration in seconds">[\s\S]*<span>Reboot duration<\/span>[\s\S]*data-controller-device-config-field="rebootDurationSeconds"[^>]+title="Reboot duration in seconds"/);
  assert.doesNotMatch(html, /Power-on delay \(sec\)|Power-off delay \(sec\)|Reboot duration \(sec\)/);
  assert.match(html, /data-controller-device-config-field="powerOnDelaySeconds"/);
  assert.match(html, /value="30"/);
  assert.doesNotMatch(html, /data-controller-outlet-action="remove"/);
  assert.match(html, /data-controller-outlet-field="outlet"[^>]+readonly/);
});

test('disables NETIO physical output names when the device configuration is read-only', () => {
  const html = renderer().renderPowerControllerOutletsMarkup([{
    outlet: '2',
    deviceName: 'HMI',
    deviceConfigFields: ['name'],
    deviceConfigWritable: false,
    deviceManaged: true,
  }], { deviceManaged: true });

  assert.match(html, /Name \(read-only\)/);
  assert.match(html, /data-controller-outlet-field="deviceName"[^>]+disabled/);
  assert.doesNotMatch(html, /data-controller-outlet-field="deviceName"[^>]+readonly/);
  assert.doesNotMatch(html, /data-controller-outlet-action="remove"/);
});
