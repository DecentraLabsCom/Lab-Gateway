import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-payload-feature.js', repoRoot);

function createDocument() {
  const values = {
    labSetupMode: 'full',
    labListImmediately: 'true',
    labAccessURI: 'https://gateway.example/guacamole',
    labAccessKey: 'guac:id:42',
    labResourceType: '0',
    labCreatorPucHash: '',
    labFmuFileName: '',
    labTimeSlots: '30,60',
    labOpens: '2026-01-01',
    labCloses: '2026-12-31',
    labAvailableHoursStart: '09:00',
    labAvailableHoursEnd: '17:00',
    labMaxConcurrentUsers: '1',
    labTimezone: 'Europe/Madrid',
    labFmiVersion: '',
    labSimulationType: '',
    labDefaultStartTime: '',
    labDefaultStopTime: '',
    labDefaultStepSize: '',
    labMetadataUrl: 'https://gateway.example/metadata.json',
  };
  const elements = new Map(Object.entries(values).map(([id, value]) => [id, { value }]));
  return {
    values,
    getElementById: id => elements.get(id) || null,
  };
}

function loadFeature() {
  const documentImpl = createDocument();
  const source = fs.readFileSync(scriptPath, 'utf8');
  const context = vm.createContext({ window: {}, document: documentImpl, console });
  vm.runInContext(source, context, { filename: 'lab-publisher-payload-feature.js' });
  let contentOptions;
  let synced = 0;
  const controller = context.window.LabPublisherPayloadFeature.createController({
    documentImpl,
    RESOURCE_TYPES: { LAB: 'lab', FMU: 'fmu' },
    syncResourceTypeFields: () => { synced += 1; },
    validate: () => {},
    ensureContentId: () => 'lab-content-42',
    getContentState: options => {
      contentOptions = options;
      return {
        name: 'Remote Lab',
        description: 'A test lab',
        imageUrls: options.imageMode === 'upload' ? options.uploadedImages : ['https://example.test/image.png'],
        docs: options.docMode === 'upload' ? options.uploadedDocs : ['https://example.test/docs.pdf'],
        demoEnabled: true,
        keywords: ['test'],
      };
    },
    getMediaState: () => ({ imageMode: 'upload', docMode: 'link' }),
    getUploadedAssets: () => ({ images: ['uploaded-image'], docs: ['uploaded-doc'] }),
    getAvailabilityState: () => ({
      selectedCategories: ['1.2'],
      selectedIscedCodes: [],
      educationalProgramLinked: false,
      unavailableWindows: [],
      availableDays: ['MONDAY'],
    }),
    getPricingState: () => ({ displayAmount: '2', displayUnit: 'hour' }),
    resolvePayloadRawPrice: () => 'raw-42',
    getBookingMode: () => 'slot',
    getAllowedPeriodRange: () => null,
    getTermsState: () => ({ url: 'https://example.test/terms.pdf' }),
    getModelVariables: () => [{ name: 'speed' }],
    buildClassificationEntries: input => ({ input }),
    sanitizeUnavailableWindows: value => value,
    expandAllowedDurations: () => [],
    buildPeriodRules: () => null,
    sanitizeTermsOfUse: value => value,
    sanitizeAvailableHours: (start, end) => ({ start, end }),
    normalizeMaxConcurrentUsers: value => Number(value),
    dateInputToUnix: value => value ? 100 : 0,
    splitCsv: value => String(value || '').split(',').map(item => item.trim()).filter(Boolean),
    buildMetadataPayload: input => input,
  });
  return { controller, documentImpl, contentOptions: () => contentOptions, synced: () => synced };
}

test('composes full publisher metadata from delegated feature state', () => {
  const { controller, contentOptions, synced } = loadFeature();

  const payload = controller.buildLabPayload();
  const metadata = payload.metadata;

  assert.equal(payload.price, 'raw-42');
  assert.equal(payload.setupMode, 'full');
  assert.equal(metadata.contentId, 'lab-content-42');
  assert.equal(metadata.resourceType, 'lab');
  assert.deepEqual(JSON.parse(JSON.stringify(metadata.imageUrls)), ['uploaded-image']);
  assert.deepEqual(JSON.parse(JSON.stringify(metadata.docs)), ['https://example.test/docs.pdf']);
  assert.equal(contentOptions().imageMode, 'upload');
  assert.equal(contentOptions().docMode, 'link');
  assert.equal(synced(), 2);
});

test('keeps quick setup as a metadata URL payload', () => {
  const { controller, documentImpl } = loadFeature();
  documentImpl.getElementById('labSetupMode').value = 'quick';

  assert.deepEqual(JSON.parse(JSON.stringify(controller.buildLabPayload())), {
    setupMode: 'quick',
    listImmediately: true,
    price: 'raw-42',
    accessURI: 'https://gateway.example/guacamole',
    accessKey: 'guac:id:42',
    resourceType: 0,
    creatorPucHash: '',
    metadataUrl: 'https://gateway.example/metadata.json',
  });
});
