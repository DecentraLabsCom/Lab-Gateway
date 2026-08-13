import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const htmlPath = new URL('web/lab-manager/index.html', repoRoot);
const tabsScriptPath = new URL('web/assets/js/lab-manager-tabs.js', repoRoot);

test('Lab Manager exposes five accessible workflow tabs with mapped sections', () => {
  const html = fs.readFileSync(htmlPath, 'utf8');
  const expectedTabs = [
    'laboratories',
    'operations',
    'energy',
    'digital-twins',
    'notifications',
  ];

  assert.match(html, /role="tablist"/);
  for (const tab of expectedTabs) {
    assert.match(html, new RegExp(`data-lm-tab="${tab}"`));
    assert.match(html, new RegExp(`aria-controls="lm-panel-${tab}"`));
    assert.match(html, new RegExp(`data-lm-tab-section="${tab}"`));
  }
  assert.match(html, /data-lm-tab="digital-twins"[^>]*data-full-only="true"/);
  assert.match(html, /data-lm-tab="notifications"[^>]*data-full-only="true"/);
  assert.match(html, /id="notificationsAccessGate"/);
  assert.match(html, /id="unlockNotificationsBtn"/);
});

test('tab controller supports hashes, keyboard navigation, Lite restrictions and activation events', () => {
  const source = fs.readFileSync(tabsScriptPath, 'utf8');

  assert.match(source, /window\.location\.hash/);
  assert.match(source, /ArrowLeft/);
  assert.match(source, /ArrowRight/);
  assert.match(source, /Home/);
  assert.match(source, /End/);
  assert.match(source, /\/gateway\/mode/);
  assert.match(source, /data-full-only/);
  assert.match(source, /lab-manager:tab-activated/);
});
