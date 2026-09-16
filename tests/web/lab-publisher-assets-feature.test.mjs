import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-assets-feature.js', repoRoot);

function createAssetList() {
  const listeners = [];
  return {
    innerHTML: '',
    addEventListener(type, listener) {
      listeners.push({ type, listener });
    },
    dispatchClick(target) {
      const binding = listeners.find(item => item.type === 'click');
      return binding?.listener({ target });
    },
  };
}

function loadFeature() {
  const source = fs.readFileSync(scriptPath, 'utf8');
  const context = vm.createContext({ window: {}, console });
  vm.runInContext(source, context, { filename: 'lab-publisher-assets-feature.js' });

  const assetListElement = createAssetList();
  const imageInput = { value: 'selected-image' };
  const docInput = { value: 'selected-doc' };
  let uploadedImages = [];
  let uploadedDocs = [];
  const calls = [];
  const toasts = [];
  const controller = context.window.LabPublisherAssetsFeature.createController({
    assetListElement,
    inputs: { images: imageInput, docs: docInput },
    getUploadedImages: () => uploadedImages,
    getUploadedDocs: () => uploadedDocs,
    setUploadedImages: value => { uploadedImages = value; },
    setUploadedDocs: value => { uploadedDocs = value; },
    ensureContentId: () => 'lab-content-1',
    fetchJson: async (url, options) => {
      calls.push({ url, options });
      return { url: 'https://cdn.example/asset-1' };
    },
    buildAssetUploadRequest: ({ contentId, kind, file }) => ({
      url: `/lab-admin/content/${contentId}/${kind}`,
      options: { method: 'POST', body: file },
    }),
    buildAssetDeleteRequest: url => ({
      url: `/lab-admin/content/delete?url=${encodeURIComponent(url)}`,
      options: { method: 'DELETE' },
    }),
    renderAssetList: ({ uploadedImages: images, uploadedDocs: docs }) => JSON.stringify({ images, docs }),
    escapeHtml: value => String(value ?? ''),
    escapeAttr: value => String(value ?? ''),
    callbacks: {
      setStatus: (message, isError) => calls.push({ type: 'status', message, isError }),
      showToast: (message, type) => toasts.push({ message, type }),
    },
  });
  controller.bind();
  return {
    controller,
    assetListElement,
    imageInput,
    calls,
    toasts,
  };
}

test('uploads assets through the existing request builder and reports success', async () => {
  const { controller, imageInput, calls, toasts } = loadFeature();

  await controller.upload([{ name: 'cover.png' }], 'images');

  assert.deepEqual(JSON.parse(JSON.stringify(controller.getUploadedImages())), ['https://cdn.example/asset-1']);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), {
    url: '/lab-admin/content/lab-content-1/images',
    options: { method: 'POST', body: { name: 'cover.png' } },
  });
  assert.equal(imageInput.value, '');
  assert.deepEqual(toasts, [{ message: 'Uploaded 1 image.', type: 'success' }]);
});

test('removes an asset through delegated clicks and rerenders the remaining lists', async () => {
  const { controller, assetListElement, calls } = loadFeature();
  await controller.upload([{ name: 'cover.png' }], 'images');
  calls.length = 0;

  await assetListElement.dispatchClick({
    closest: () => ({ dataset: { url: 'https://cdn.example/asset-1', kind: 'images' }, disabled: false }),
  });

  assert.deepEqual(JSON.parse(JSON.stringify(controller.getUploadedImages())), []);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), {
    url: '/lab-admin/content/delete?url=https%3A%2F%2Fcdn.example%2Fasset-1',
    options: { method: 'DELETE' },
  });
  assert.deepEqual(JSON.parse(assetListElement.innerHTML), { images: [], docs: [] });
  assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))), {
    type: 'status',
    message: 'Asset deleted.',
    isError: false,
  });
});
