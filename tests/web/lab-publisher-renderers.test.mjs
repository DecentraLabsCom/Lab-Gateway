import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-renderers.js', repoRoot);

function loadRenderers() {
  const window = {};
  const context = vm.createContext({ window });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-publisher-renderers.js',
  });
  return context.window.LabPublisherRenderers;
}

test('renders the publisher action icons as self-contained SVGs', () => {
  const renderers = loadRenderers();

  assert.match(renderers.renderLabActionIcon('edit'), /<svg class="lab-action-icon"/);
  assert.match(renderers.renderLabActionIcon('edit'), /M12 20h9/);
  assert.match(renderers.renderLabActionIcon('list'), /<circle cx="12" cy="12" r="2\.5"\/>/);
  assert.match(renderers.renderLabActionIcon('unlist'), /m3 3 18 18/);
  assert.match(renderers.renderLabActionIcon('delete'), /M6 7l1 13h10l1-13/);
  assert.equal((renderers.renderLabActionIcon('list').match(/stroke="currentColor"/g) || []).length, 1);
});

test('renders FMI model variables and preserves safe empty-state visibility', () => {
  const renderers = loadRenderers();
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[character]);

  const populated = renderers.renderModelVariables({
    modelVariables: [{ name: '<speed>', causality: 'output', type: 'Real', unit: 'm/s', start: 0 }],
    escapeHtml,
  });
  assert.equal(populated.hidden, false);
  assert.match(populated.html, /&lt;speed&gt;/);
  assert.match(populated.html, /<td>0<\/td>/);
  assert.doesNotMatch(populated.html, /<speed>/);

  const empty = renderers.renderModelVariables({ modelVariables: [], escapeHtml });
  assert.equal(empty.hidden, true);
  assert.equal(empty.html, '');
});