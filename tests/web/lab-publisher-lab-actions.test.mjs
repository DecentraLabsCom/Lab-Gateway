import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher.js', repoRoot);
const stylesheetPath = new URL('web/assets/css/lab-manager.css', repoRoot);

function loadPublisherHooks() {
  const source = fs.readFileSync(scriptPath, 'utf8');
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
  const instrumented = source.replace(
    /\}\)\(\);\s*$/,
    `
    window.__labPublisherTestHooks = { renderLabs };
})();`,
  );

  const context = vm.createContext({ document, window, console });
  vm.runInContext(instrumented, context, { filename: 'lab-publisher.js' });
  return { labList, hooks: context.window.__labPublisherTestHooks };
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
