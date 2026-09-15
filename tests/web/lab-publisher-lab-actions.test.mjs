import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const valuesScriptPath = new URL('web/assets/js/lab-publisher-values.js', repoRoot);
const renderersScriptPath = new URL('web/assets/js/lab-publisher-renderers.js', repoRoot);
const actionsScriptPath = new URL('web/assets/js/lab-publisher-lab-actions.js', repoRoot);
const resourcesScriptPath = new URL('web/assets/js/lab-publisher-resources.js', repoRoot);
const assetsScriptPath = new URL('web/assets/js/lab-publisher-assets.js', repoRoot);
const metadataScriptPath = new URL('web/assets/js/lab-publisher-metadata.js', repoRoot);
const stylesheetPath = new URL('web/assets/css/lab-manager.css', repoRoot);
const indexPath = new URL('web/lab-manager/index.html', repoRoot);

function loadPublisherHooks() {
  const valuesSource = fs.readFileSync(valuesScriptPath, 'utf8');
  const renderersSource = fs.readFileSync(renderersScriptPath, 'utf8');
  const actionsSource = fs.readFileSync(actionsScriptPath, 'utf8');
  const resourcesSource = fs.readFileSync(resourcesScriptPath, 'utf8');
  const assetsSource = fs.readFileSync(assetsScriptPath, 'utf8');
  const metadataSource = fs.readFileSync(metadataScriptPath, 'utf8');
  const labList = {
    classList: {
      add() {},
      remove() {},
    },
    innerHTML: '',
    textContent: '',
  };
  const document = {
    addEventListener() {},
    getElementById(id) {
      return id === 'labPublisherList' ? labList : null;
    },
  };
  const window = {};
  const context = vm.createContext({ document, window, console });
  vm.runInContext(valuesSource, context, { filename: 'lab-publisher-values.js' });
  vm.runInContext(renderersSource, context, { filename: 'lab-publisher-renderers.js' });
  vm.runInContext(resourcesSource, context, { filename: 'lab-publisher-resources.js' });
  vm.runInContext(assetsSource, context, { filename: 'lab-publisher-assets.js' });
  vm.runInContext(metadataSource, context, { filename: 'lab-publisher-metadata.js' });
  vm.runInContext(actionsSource, context, { filename: 'lab-publisher-lab-actions.js' });
  const values = context.window.LabPublisherValues;
  const renderers = context.window.LabPublisherRenderers;
  const controller = context.window.LabPublisherLabActions.createController({
    listElement: labList,
    renderLabActionIcon: renderers.renderLabActionIcon,
    escapeHtml: values.escapeHtml,
    escapeAttr: values.escapeAttr,
    formatRawPriceForUnit: values.formatRawPriceForUnit,
    resolveLabPriceUnit: values.resolveLabPriceUnit,
    resolveLabDisplayName: values.resolveLabDisplayName,
  });
  return { labList, hooks: { renderLabs: labs => controller.render(labs) } };
}

test('renders self-contained lab action icons for edit, list/unlist and delete', () => {
  const { labList, hooks } = loadPublisherHooks();

  hooks.renderLabs([
    { labId: '42', listed: true, accessKey: 'guac:id:42', uri: 'https://gateway.example/guacamole', price: '1' },
    { labId: '43', listed: false, accessKey: 'guac:id:43', uri: 'https://gateway.example/guacamole', price: '1' },
  ]);

  assert.match(labList.innerHTML, /data-lab-action="edit"[\s\S]*class="lab-action-icon"/);
  assert.match(labList.innerHTML, /data-lab-action="unlist"[\s\S]*class="lab-action-icon"/);
  assert.match(labList.innerHTML, /data-lab-action="list"[\s\S]*class="lab-action-icon"/);
  assert.match(labList.innerHTML, /data-lab-action="delete"[\s\S]*class="lab-action-icon"/);
  assert.equal((labList.innerHTML.match(/stroke="currentColor"/g) || []).length, 6);
  assert.doesNotMatch(labList.innerHTML, /class="fas\s/);
});

test('gives lab action icons a light, high-contrast color in every button variant', () => {
  const stylesheet = fs.readFileSync(stylesheetPath, 'utf8');

  assert.match(stylesheet, /\.lab-actions \.mini-btn\s*\{[\s\S]*color:\s*#f8fafc;/);
  assert.match(stylesheet, /\.lab-actions \.mini-btn\.primary\s*\{[\s\S]*color:\s*#fff;/);
  assert.match(stylesheet, /\.lab-actions \.mini-btn\.danger\s*\{[\s\S]*color:\s*#fff;/);
  assert.match(stylesheet, /\.lab-action-icon\s*\{[\s\S]*stroke:\s*currentColor;/);
});

test('prefers the metadata lab name and falls back to the lab id', () => {
  const { labList, hooks } = loadPublisherHooks();

  hooks.renderLabs([
    {
      labId: '1',
      name: 'StateSpace',
      resourceType: 1,
      listed: true,
      accessKey: 'StateSpace.fmu',
      uri: 'https://gateway.example/lab-1/metadata.json',
      price: '1',
    },
    {
      labId: '2',
      name: '   ',
      resourceType: 0,
      listed: true,
      accessKey: 'guac:id:2',
      uri: 'https://gateway.example/lab-2/metadata.json',
      price: '1',
    },
  ]);

  assert.match(labList.innerHTML, /<div class="item-title">StateSpace FMU /);
  assert.doesNotMatch(labList.innerHTML, /Lab #1 FMU/);
  assert.match(labList.innerHTML, /<div class="item-title">Lab #2 Remote /);
});

test('cache-busts the lab manager assets after lab display updates', () => {
  const index = fs.readFileSync(indexPath, 'utf8');

  assert.match(index, /lab-manager\.css\?v=workflow-tabs-v18/);
  assert.match(index, /lab-manager\.js\?v=workflow-tabs-v18/);
  assert.match(index, /lab-publisher-values\.js\?v=publisher-values-v1[\s\S]*lab-publisher-renderers\.js\?v=publisher-renderers-v1[\s\S]*lab-publisher-resources\.js\?v=publisher-resources-v1[\s\S]*lab-publisher-assets\.js\?v=publisher-assets-v1[\s\S]*lab-publisher-metadata\.js\?v=publisher-metadata-v1[\s\S]*lab-publisher-lab-actions\.js\?v=publisher-lab-actions-v1[\s\S]*lab-publisher\.js\?v=workflow-tabs-v2/);
  assert.match(index, /lab-publisher-lab-actions\.js\?v=publisher-lab-actions-v1[\s\S]*lab-publisher\.js\?v=workflow-tabs-v2/);
});

test('labels pending station candidates and does not expose a manual lab selector', () => {
  const index = fs.readFileSync(indexPath, 'utf8');

  assert.match(index, /Lab Station candidates awaiting configuration:/);
  assert.doesNotMatch(index, /Guacamole connections without an ops host/);
  assert.doesNotMatch(index, /id="provisionHostLabs"/);
});
