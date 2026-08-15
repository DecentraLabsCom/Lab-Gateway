import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const stylesheetPath = new URL('../../web/assets/css/lab-manager.css', import.meta.url);

test('uses compatible scrollbar styling without unsupported scrollbar properties', () => {
  const stylesheet = fs.readFileSync(stylesheetPath, 'utf8');

  assert.doesNotMatch(stylesheet, /scrollbar-(?:width|color)\s*:/);
  assert.match(stylesheet, /\.lm-tab-list::\-webkit-scrollbar\s*\{[\s\S]*height:/);
  assert.match(stylesheet, /\.reservation-list::\-webkit-scrollbar\s*\{[\s\S]*width:/);
});
