import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const stylesheetPath = new URL('web/assets/css/lab-manager.css', repoRoot);

test('uses the same calendar icon color for date, time and unavailable-window controls', () => {
  const stylesheet = fs.readFileSync(stylesheetPath, 'utf8');
  const indicatorRule = stylesheet.match(
    /\.field input\[type="date"\]::-webkit-calendar-picker-indicator,[\s\S]*?\{([\s\S]*?)\}/,
  );

  assert.ok(indicatorRule, 'calendar picker indicator rule should exist');
  assert.match(indicatorRule[0], /\.field input\[type="time"\]::-webkit-calendar-picker-indicator/);
  assert.match(indicatorRule[0], /\.field input\[type="datetime-local"\]::-webkit-calendar-picker-indicator/);
  assert.match(indicatorRule[1], /filter:\s*invert\(1\) brightness\(1\.8\) contrast\(1\.05\)/);
});

test('centers the unavailable-window remove action with the form controls', () => {
  const stylesheet = fs.readFileSync(stylesheetPath, 'utf8');
  const actionRule = stylesheet.match(
    /\.unavailable-window \.action-field\s*\{([\s\S]*?)\}/,
  );

  assert.ok(actionRule, 'unavailable-window action alignment rule should exist');
  assert.match(actionRule[1], /justify-content:\s*center/);
});
