import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-pricing-feature.js', repoRoot);

function createElement(id) {
  return { id, value: '' };
}

function loadFeature() {
  const source = fs.readFileSync(scriptPath, 'utf8');
  const elements = new Map(['labPrice', 'labPriceUnit'].map(id => [id, createElement(id)]));
  const document = { getElementById: id => elements.get(id) || null };
  const context = vm.createContext({ window: {}, document, console });
  vm.runInContext(source, context, { filename: 'lab-publisher-pricing-feature.js' });
  const controller = context.window.LabPublisherPricingFeature.createController({
    documentImpl: document,
    normalizePricingUnit: value => ['hour', 'day', 'week', 'month'].includes(value) ? value : 'hour',
    convertDisplayCreditsToRawPerSecond: (amount, unit) => BigInt(Math.trunc(Number(amount) * 10)) * BigInt({ hour: 1, day: 2, week: 3, month: 4 }[unit]),
    resolveLabPriceUnit: lab => lab?.metadata?.pricing?.displayUnit || 'hour',
    formatRawPriceForUnit: (raw, unit) => `${raw}-${unit}`,
  });
  return { controller, elements };
}

test('owns pricing hydration and raw-per-second conversion', () => {
  const { controller, elements } = loadFeature();

  controller.hydrate({ displayAmount: '2.5', displayUnit: 'day' });
  assert.deepEqual(JSON.parse(JSON.stringify(controller.getState())), {
    displayAmount: '2.5',
    displayUnit: 'day',
    rawPricePerSecond: '50',
    roundingMode: 'nearest-per-second',
    billingMode: 'linear-duration',
  });

  controller.reset();
  assert.equal(elements.get('labPrice').value, '0');
  assert.equal(elements.get('labPriceUnit').value, 'hour');
});

test('preserves the original raw price until the edited display changes', () => {
  const { controller, elements } = loadFeature();
  controller.hydrate({ displayAmount: '3', displayUnit: 'week' });
  controller.captureOriginalEditPrice({ metadata: { pricing: { displayUnit: 'day' } }, price: 'raw-123' });

  assert.equal(controller.resolvePayloadRawPrice(), 'raw-123');
  elements.get('labPrice').value = '4';
  assert.equal(controller.resolvePayloadRawPrice(), '120');
});
