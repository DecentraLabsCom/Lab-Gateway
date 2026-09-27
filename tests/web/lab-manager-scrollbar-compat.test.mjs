import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const stylesheetPath = new URL('../../web/assets/css/lab-manager.css', import.meta.url);

test('uses compatible scrollbar styling without unsupported scrollbar properties', () => {
  const stylesheet = fs.readFileSync(stylesheetPath, 'utf8');
  const normalizedStylesheet = stylesheet.replace(/\s+/g, ' ');

  assert.doesNotMatch(stylesheet, /scrollbar-(?:width|color)\s*:/);
  assert.match(stylesheet, /\.lm-tab-list::\-webkit-scrollbar\s*\{[\s\S]*height:/);
  assert.match(
    normalizedStylesheet,
    /\.fixed-height::\-webkit-scrollbar, \.multi-select-menu::\-webkit-scrollbar, \.reservation-list::\-webkit-scrollbar, \.host-list::\-webkit-scrollbar, \.modal-body::\-webkit-scrollbar, \.table-wrap::\-webkit-scrollbar \{ width:/,
  );
});
