import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-metadata-feature.js', repoRoot);

function createElement(id) {
  return { id, value: '', checked: false };
}

function loadFeature() {
  const source = fs.readFileSync(scriptPath, 'utf8');
  const elements = new Map([
    'labName',
    'labDescription',
    'labKeywords',
    'labDemoEnabled',
    'labImageUrls',
    'labDocUrls',
  ].map(id => [id, createElement(id)]));
  const document = { getElementById: id => elements.get(id) || null };
  const context = vm.createContext({ window: {}, document, console });
  vm.runInContext(source, context, { filename: 'lab-publisher-metadata-feature.js' });
  const controller = context.window.LabPublisherMetadataFeature.createController({
    documentImpl: document,
    splitCsv: value => String(value || '').split(',').map(item => item.trim()).filter(Boolean),
  });
  return { controller, elements };
}

test('hydrates descriptive metadata and returns link-mode media', () => {
  const { controller, elements } = loadFeature();

  controller.hydrate({
    name: 'Spring Damper',
    description: 'A reusable FMU lab',
    keywords: ['fmu', 'mechanics'],
    demoEnabled: true,
    imageUrls: ['https://example.test/cover.png'],
    docUrls: ['https://example.test/readme.pdf'],
  });

  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState({ imageMode: 'link', docMode: 'link' }))), {
    name: 'Spring Damper',
    description: 'A reusable FMU lab',
    keywords: ['fmu', 'mechanics'],
    demoEnabled: true,
    imageUrls: ['https://example.test/cover.png'],
    docs: ['https://example.test/readme.pdf'],
  });
  assert.equal(elements.get('labKeywords').value, 'fmu, mechanics');
});

test('switches media sources by mode and resets all owned fields', () => {
  const { controller, elements } = loadFeature();
  elements.get('labName').value = 'Draft';
  elements.get('labDescription').value = 'Description';
  elements.get('labKeywords').value = 'one, two';
  elements.get('labDemoEnabled').checked = true;
  elements.get('labImageUrls').value = 'https://example.test/link.png';
  elements.get('labDocUrls').value = 'https://example.test/link.pdf';

  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState({
    imageMode: 'upload',
    docMode: 'upload',
    uploadedImages: ['https://example.test/upload.png'],
    uploadedDocs: ['https://example.test/upload.pdf'],
  }))), {
    name: 'Draft',
    description: 'Description',
    keywords: ['one', 'two'],
    demoEnabled: true,
    imageUrls: ['https://example.test/upload.png'],
    docs: ['https://example.test/upload.pdf'],
  });

  controller.reset();
  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState())), {
    name: '',
    description: '',
    keywords: [],
    demoEnabled: false,
    imageUrls: [],
    docs: [],
  });
});
