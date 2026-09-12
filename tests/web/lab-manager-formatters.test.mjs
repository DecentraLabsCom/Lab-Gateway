import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/core/formatters.js', repoRoot);

function loadFormatters() {
  const context = vm.createContext({ window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'formatters.js',
  });
  return context.window.LabManagerFormatters;
}

test('formats dates and booleans with the existing fallbacks', () => {
  const formatters = loadFormatters();

  assert.equal(formatters.formatDate(''), 'n/a');
  assert.equal(formatters.formatDate('not-a-date'), 'not-a-date');
  assert.notEqual(formatters.formatDate('2024-01-01T00:00:00Z'), 'n/a');
  assert.equal(formatters.formatBool(true), 'yes');
  assert.equal(formatters.formatBool(false), 'no');
  assert.equal(formatters.formatBool(null), 'n/a');
});

test('escapes timeline text without changing safe values', () => {
  const formatters = loadFormatters();

  assert.equal(formatters.htmlEscape('ready'), 'ready');
  assert.equal(
    formatters.htmlEscape(`<unsafe>&\"'` + '`'),
    '&lt;unsafe&gt;&amp;&quot;&#39;&#96;',
  );
  assert.equal(formatters.htmlEscape(null), '');
});
