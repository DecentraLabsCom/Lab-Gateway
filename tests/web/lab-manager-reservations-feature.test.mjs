import fs from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-reservations-feature.js', repoRoot);

function createElement(id) {
  const listeners = new Map();
  return {
    id,
    addEventListener: (type, handler) => listeners.set(type, handler),
    dispatchEvent: (event) => listeners.get(event.type)?.(event),
  };
}

function loadFeature() {
  const elements = new Map([
    'timelineReservationId',
    'loadTimelineBtn',
    'timelineResult',
    'upcomingReservationsList',
    'upcomingReservationsStatus',
  ].map((id) => [id, createElement(id)]));
  const document = {
    querySelector: (selector) => elements.get(selector.slice(1)) || null,
  };
  const calls = [];
  const managedLabs = [{ labId: 'lab-7', name: 'Thermal Lab' }];
  const timeline = {
    bind: () => calls.push('timeline.bind'),
    load: (...args) => calls.push(['timeline.load', ...args]),
  };
  const actionableReservations = {
    bind: () => calls.push('actionable.bind'),
    load: (...args) => calls.push(['actionable.load', ...args]),
  };
  const window = {
    LabManagerReservationValues: {
      createController: () => ({
        formatReservationDate: value => `date:${value}`,
        formatRange: () => 'range',
        isReservationWindowEnded: () => false,
        normalizeReservationStatus: value => Number(value),
        cancellationButtonLabel: () => 'Cancel',
        shortAddress: value => String(value),
      }),
    },
    LabManagerReservationRenderers: {
      createController: (options) => {
        calls.push('renderers.create');
        assert.equal(options.resolveReservationLabDisplayName({ labId: 'lab-7' }), 'Thermal Lab');
        return {
          renderTimelineMarkup: () => '<timeline />',
          renderUpcomingReservationsMarkup: () => '<reservations />',
        };
      },
    },
    LabManagerTimeline: {
      createController: (options) => {
        calls.push('timeline.create');
        assert.equal(options.renderTimelineMarkup(), '<timeline />');
        return timeline;
      },
    },
    LabManagerActionableReservations: {
      createController: (options) => {
        calls.push('actionable.create');
        assert.equal(options.renderMarkup(), '<reservations />');
        return actionableReservations;
      },
    },
  };
  const context = vm.createContext({
    document,
    window,
    console,
    Promise,
  });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-reservations-feature.js',
  });
  return { context, document, elements, calls, managedLabs };
}

test('reservations feature composes timeline and actionable reservations', () => {
  const { context, document, elements, calls, managedLabs } = loadFeature();
  const controller = context.window.LabManagerReservationsFeature.createController({
    documentImpl: document,
    fetchImpl: () => Promise.resolve(),
    normalizePagination: () => ({}),
    escapeHtml: value => String(value),
    htmlEscape: value => String(value),
    formatDate: value => String(value),
    formatBool: value => String(value),
    showToast: () => {},
    getManagedLabs: () => managedLabs,
    resolveLabDisplayName: lab => lab.name || `Lab #${lab.labId}`,
  });

  controller.initialize();
  assert.deepEqual(calls, [
    'renderers.create',
    'timeline.create',
    'actionable.create',
    'timeline.bind',
    'actionable.bind',
  ]);
  assert.equal(controller.hasReservationList(), true);
  assert.equal(controller.timelineButton, elements.get('loadTimelineBtn'));
  assert.equal(controller.resolveReservationLabDisplayName({ labId: 'lab-7' }), 'Thermal Lab');

  controller.loadActionableReservations({ skipAuthPrompt: true });
  assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))), [
    'actionable.load',
    { skipAuthPrompt: true },
  ]);
});
