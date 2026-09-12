import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-publisher-values.js', repoRoot);

function loadValues() {
  const window = {};
  const context = vm.createContext({ window });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-publisher-values.js',
  });
  return context.window.LabPublisherValues;
}

test('normalizes Guacamole users and removes empty entries', () => {
  const values = loadValues();
  assert.deepEqual(
    values.normalizeConnectionUsers({ users: [' alice ', { username: 'bob' }, { name: 'carol' }, null, ' '] }),
    ['alice', 'bob', 'carol'],
  );
});

test('resolves explicit selectors before the Guacamole ID fallback', () => {
  const values = loadValues();
  assert.equal(values.resolveConnectionAccessKey({ selector: 'station-main', id: 42 }), 'station-main');
  assert.equal(values.resolveConnectionAccessKey({ id: 42 }), 'guac:id:42');
  assert.equal(values.resolveConnectionAccessKey({}), '');
});

test('formats connection users for resource labels', () => {
  const values = loadValues();
  assert.equal(values.formatConnectionUsers({ users: ['alice', { name: 'bob' }] }), ' - alice, bob');
  assert.equal(values.formatConnectionUsers({ users: [] }), '');
});

test('preserves credit precision and pricing-unit conversion rules', () => {
  const values = loadValues();
  assert.equal(values.parseHourlyCreditsToRaw('1.2345678'), 12345678n);
  assert.equal(values.formatRawCredits(12345678n), '1.2345678');
  assert.equal(values.normalizePricingUnit(' WEEK '), 'week');
  assert.equal(values.normalizePricingUnit('unsupported'), 'hour');
  assert.equal(values.convertDisplayCreditsToRawPerSecond('1', 'hour'), 2778n);
  assert.equal(values.formatRawPriceForUnit(2778n, 'hour'), '1');
  assert.equal(values.resolveLabPriceUnit({ metadata: { pricing: { displayUnit: 'day' } } }), 'day');
  assert.equal(values.roundDecimalString('1.23456', 3), '1.235');
});

test('rejects invalid prices while preserving the existing messages', () => {
  const values = loadValues();
  assert.throws(() => values.parseHourlyCreditsToRaw(''), { message: 'Price is required' });
  assert.throws(() => values.parseHourlyCreditsToRaw('1.12345678'), {
    message: 'Price supports up to 7 decimal places',
  });
  assert.throws(() => values.parseHourlyCreditsToRaw('-1'), {
    message: 'Price must be a non-negative number',
  });
});

test('parses API responses and preserves mutation confirmation rules', async () => {
  const values = loadValues();
  const calls = [];
  const okResponse = {
    ok: true,
    status: 200,
    text: async () => JSON.stringify({ labs: [] }),
  };
  const body = await values.fetchJson('/lab-admin/labs', { method: 'GET' }, async (url, options) => {
    calls.push({ url, options });
    return okResponse;
  });
  assert.equal(body.labs.length, 0);
  assert.equal(calls[0].options.credentials, 'include');

  await assert.rejects(
    values.fetchJson('/lab-admin/labs', {}, async () => ({
      ok: false,
      status: 409,
      text: async () => 'conflict',
    })),
    { message: 'conflict' },
  );
  assert.doesNotThrow(() => values.assertLabMutationSuccess({
    success: true,
    action: 'metadataOnly',
  }, 'Update'));
  assert.doesNotThrow(() => values.assertLabMutationSuccess({
    success: true,
    transactionHash: '0xabc',
    status: 'confirmed',
  }, 'Publish'));
  assert.throws(
    () => values.assertLabMutationSuccess({ success: true, status: 'pending' }, 'Publish'),
    { message: 'Publish transaction did not confirm on-chain' },
  );
});

test('normalizes and deduplicates FORD/ISCED classification entries', () => {
  const values = loadValues();
  const entries = values.buildClassificationEntries({
    fordCodes: ['1.2', '1.2', 'invalid'],
    iscedCodes: ['061', '061'],
    educationalProgramLinked: true,
  });
  assert.equal(entries.length, 2);
  assert.equal(entries[0].scheme, 'OECD-FORD');
  assert.equal(entries[0].schemeVersion, 'Frascati Manual 2015');
  assert.equal(entries[1].scheme, 'ISCED-F');
  assert.equal(entries[1].code, '061');
  assert.equal(
    values.getSuggestedIscedCodes(['1.2', '1.4', '1.2']).join(','),
    '061,053,071',
  );
  assert.equal(
    values.normalizeClassificationEntries([
      { scheme: 'OECD-FORD', code: '1.2' },
      { scheme: 'unknown', code: 'x' },
    ]).map(entry => entry.code).join(','),
    '1.2',
  );
});

test('sanitizes availability, booking periods and terms without changing metadata values', () => {
  const values = loadValues();
  assert.equal(JSON.stringify(values.sanitizeAvailableHours('9:05', '18:00')), '{"start":"09:05","end":"18:00"}');
  assert.equal(JSON.stringify(values.sanitizeAvailableHours('24:00', '18:00')), '{}');
  assert.equal(JSON.stringify(values.sanitizeUnavailableWindows([
    { startUnix: 100.9, endUnix: 200.1, reason: ' Maintenance ' },
    { startUnix: 300, endUnix: 200, reason: 'invalid' },
  ])), '[{"startUnix":100,"endUnix":200,"reason":"Maintenance"}]');
  assert.equal(values.normalizePeriodUnit('WEEKS'), 'week');
  assert.equal(
    JSON.stringify(values.expandAllowedDurations({ unit: 'week', min: 2, max: 4 })),
    '[{"unit":"week","value":2},{"unit":"week","value":3},{"unit":"week","value":4}]',
  );
  assert.equal(
    JSON.stringify(values.buildPeriodRules({ unit: 'month', min: 1, max: 3 })),
    '{"startGranularity":"day","allowCustomDateRange":true,"minDurationDays":30,"maxDurationDays":90}',
  );
  assert.equal(
    JSON.stringify(values.sanitizeTermsOfUse({
      url: ' https://example.test/terms ',
      version: 'v2',
      effectiveDate: '2024-02-03',
      sha256: 'ABCDEF',
    })),
    '{"url":" https://example.test/terms ","version":"v2","effectiveDate":1706918400,"sha256":"abcdef"}',
  );
  assert.equal(values.normalizeMaxConcurrentUsers('0', false), 1);
  assert.equal(values.normalizeMaxConcurrentUsers('1', true), 2);
});

test('keeps publisher availability options and timezone fallbacks available as pure values', () => {
  const values = loadValues();
  assert.equal(values.WEEKDAY_OPTIONS.length, 7);
  assert.equal(values.WEEKDAY_OPTIONS[0].value, 'MONDAY');
  assert.equal(values.WEEKDAY_OPTIONS.at(-1).value, 'SUNDAY');
  assert.equal(values.DEFAULT_TIMEZONES.includes('Europe/Madrid'), true);
  assert.equal(Array.isArray(values.resolveSupportedTimezones()), true);
  assert.equal(typeof values.resolveBrowserTimezone(), 'string');
});

test('normalizes metadata values while preserving serialization shapes', () => {
  const values = loadValues();
  assert.equal(JSON.stringify(values.optionalAttribute('keywords', ['physics'])), '[{"trait_type":"keywords","value":["physics"]}]');
  assert.equal(JSON.stringify(values.optionalAttribute('keywords', '')), '[]');
  assert.equal(JSON.stringify(values.optionalNumberAttribute('defaultStepSize', '2.5')), '[{"trait_type":"defaultStepSize","value":2.5}]');
  assert.equal(JSON.stringify(values.optionalNumberAttribute('defaultStepSize', 'invalid')), '[]');
  assert.equal(values.normalizeTraitType(' Available_Hours '), 'availablehours');
  assert.equal(JSON.stringify(values.normalizeArray([' a ', null, 'b'])), '["a","b"]');
  assert.equal(values.splitCsv('a, b,,c').join('|'), 'a|b|c');
  assert.equal(JSON.stringify(values.mergeMediaUrls(['a', 'b'], ['b', 'c'])), '["a","b","c"]');
  assert.equal(values.unixToDateInput(1704067200), '2024-01-01');
  assert.equal(values.guessVersionFromUrl('https://example.test/model-v1.2.fmu'), '1.2');
});

test('escapes HTML text and attribute values consistently', () => {
  const values = loadValues();
  assert.equal(values.escapeHtml('<tag attr="x">&\'`'), '&lt;tag attr=&quot;x&quot;&gt;&amp;&#39;&#96;');
  assert.equal(values.escapeHtml(null), '');
  assert.equal(values.escapeAttr('https://example.test/?q="x"&ok=1'), 'https://example.test/?q=&quot;x&quot;&amp;ok=1');
});

test('derives a stable allowed period range from matching duration entries', () => {
  const values = loadValues();
  assert.equal(
    JSON.stringify(values.deriveAllowedPeriodRange([
      { unit: 'weeks', value: 2 },
      { unit: 'week', value: 4 },
      { unit: 'day', value: 9 },
      { unit: 'week', value: 3 },
    ])),
    '{"unit":"week","min":2,"max":4}',
  );
  assert.equal(values.deriveAllowedPeriodRange([]), null);
});

test('resolves the preferred managed lab display name with an id fallback', () => {
  const values = loadValues();
  assert.equal(values.resolveLabDisplayName({ name: 'Published name', metadata: { name: 'Metadata name' } }), 'Published name');
  assert.equal(values.resolveLabDisplayName({ metadata: { name: 'Metadata name' } }), 'Metadata name');
  assert.equal(values.resolveLabDisplayName({ labId: 42 }), 'Lab #42');
});
