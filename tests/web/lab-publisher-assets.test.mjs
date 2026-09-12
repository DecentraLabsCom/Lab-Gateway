import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-assets.js', repoRoot);

function loadAssets() {
  const window = {};
  const context = vm.createContext({ window });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-publisher-assets.js',
  });
  return context.window.LabPublisherAssets;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"'`]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;',
  })[character]);
}

class TestFormData {
  constructor() {
    this.entries = [];
  }

  append(name, value) {
    this.entries.push([name, value]);
  }
}

test('renders uploaded images and documents with escaped asset values', () => {
  const assets = loadAssets();

  const html = assets.renderAssetList({
    uploadedImages: ['https://gateway.example/image?<unsafe>'],
    uploadedDocs: ['https://gateway.example/terms.pdf'],
    escapeHtml,
    escapeAttr: escapeHtml,
  });

  assert.match(html, /class="asset-row"/g);
  assert.match(html, /https:\/\/gateway\.example\/image\?&lt;unsafe&gt;/);
  assert.match(html, /data-kind="images"/);
  assert.match(html, /data-kind="docs"/);
  assert.doesNotMatch(html, /<unsafe>/);
  assert.equal(assets.renderAssetList({ uploadedImages: [], uploadedDocs: [], escapeHtml, escapeAttr: escapeHtml }), '');
});

test('builds the existing multipart upload request shape', () => {
  const assets = loadAssets();
  const file = { name: 'diagram.png' };
  const request = assets.buildAssetUploadRequest({
    contentId: 'lab-abc',
    kind: 'images',
    file,
    FormDataImpl: TestFormData,
  });

  assert.equal(request.url, '/lab-admin/assets');
  assert.equal(request.options.method, 'POST');
  assert.deepEqual(request.options.body.entries, [
    ['contentId', 'lab-abc'],
    ['kind', 'images'],
    ['file', file],
  ]);
});

test('builds the existing asset delete request shape', () => {
  const assets = loadAssets();
  const request = assets.buildAssetDeleteRequest('/lab-content/content/lab-abc/image.png');

  assert.equal(request.url, '/lab-admin/assets');
  assert.equal(request.options.method, 'DELETE');
  assert.equal(request.options.headers['Content-Type'], 'application/json');
  assert.equal(request.options.body, JSON.stringify({ path: '/lab-content/content/lab-abc/image.png' }));
});
