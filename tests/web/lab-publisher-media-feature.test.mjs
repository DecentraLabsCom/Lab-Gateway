import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-media-feature.js', repoRoot);

function createButton(mode) {
  const listeners = new Map();
  return {
    dataset: { mode },
    classList: {
      active: false,
      toggle(name, enabled) {
        if (name === 'active') this.active = enabled;
      },
    },
    addEventListener(name, listener) {
      listeners.set(name, listener);
    },
    click() {
      listeners.get('click')?.();
    },
  };
}

function createElement(id, buttons = []) {
  return {
    id,
    hidden: false,
    buttons,
    querySelectorAll: () => buttons,
  };
}

function loadFeature() {
  const imageButtons = [createButton('link'), createButton('upload')];
  const docButtons = [createButton('link'), createButton('upload')];
  const elements = new Map([
    ['labImageMode', createElement('labImageMode', imageButtons)],
    ['labDocMode', createElement('labDocMode', docButtons)],
    ['labImageUrls', createElement('labImageUrls')],
    ['labDocUrls', createElement('labDocUrls')],
    ['labImagesChooseBtn', createElement('labImagesChooseBtn')],
    ['labDocsChooseBtn', createElement('labDocsChooseBtn')],
  ]);
  const document = { getElementById: id => elements.get(id) || null };
  const context = vm.createContext({ window: {}, document, console });
  const source = fs.readFileSync(scriptPath, 'utf8');
  vm.runInContext(source, context, { filename: 'lab-publisher-media-feature.js' });
  const controller = context.window.LabPublisherMediaFeature.createController({ documentImpl: document });
  return { controller, elements, imageButtons, docButtons };
}

test('owns media mode controls and exposes the selected modes', () => {
  const { controller, elements, imageButtons, docButtons } = loadFeature();

  controller.bind();
  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState())), {
    imageMode: 'link',
    docMode: 'link',
  });
  assert.equal(elements.get('labImageUrls').hidden, false);
  assert.equal(elements.get('labImagesChooseBtn').hidden, true);
  assert.equal(imageButtons[0].classList.active, true);
  assert.equal(imageButtons[1].classList.active, false);

  imageButtons[1].click();
  docButtons[1].click();
  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState())), {
    imageMode: 'upload',
    docMode: 'upload',
  });
  assert.equal(elements.get('labImageUrls').hidden, true);
  assert.equal(elements.get('labImagesChooseBtn').hidden, false);
  assert.equal(elements.get('labDocUrls').hidden, true);
  assert.equal(elements.get('labDocsChooseBtn').hidden, false);
});

test('reset returns both media modes to link inputs', () => {
  const { controller, elements } = loadFeature();

  controller.bind();
  controller.setMode('images', 'upload');
  controller.setMode('docs', 'upload');
  controller.reset();

  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState())), {
    imageMode: 'link',
    docMode: 'link',
  });
  assert.equal(elements.get('labImageUrls').hidden, false);
  assert.equal(elements.get('labImagesChooseBtn').hidden, true);
  assert.equal(elements.get('labDocUrls').hidden, false);
  assert.equal(elements.get('labDocsChooseBtn').hidden, true);
});
