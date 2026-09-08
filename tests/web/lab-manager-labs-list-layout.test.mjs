import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const repoRoot = new URL('../../', import.meta.url);
const htmlPath = new URL('web/lab-manager/index.html', repoRoot);

function isClass(value, className) {
  return value.split(/\s+/).includes(className);
}

function elementIsInside(html, targetClass, ancestorClass) {
  const stack = [];
  const tagPattern = /<\/?div\b[^>]*>/g;
  let match;

  while ((match = tagPattern.exec(html)) !== null) {
    const tag = match[0];
    if (tag.startsWith('</')) {
      stack.pop();
      continue;
    }

    const classes = tag.match(/\bclass="([^"]*)"/);
    const classValue = classes?.[1] ?? '';
    if (isClass(classValue, targetClass)) {
      return stack.some((element) => isClass(element, ancestorClass));
    }

    stack.push(classValue);
  }

  return false;
}

test('places the managed labs card inside the publisher grid for consistent spacing', () => {
  const html = fs.readFileSync(htmlPath, 'utf8');

  assert.equal(elementIsInside(html, 'labs-list-card', 'publisher-layout'), true);
});

test('labels the managed labs section as Manage Labs', () => {
  const html = fs.readFileSync(htmlPath, 'utf8');

  assert.match(html, /<h3><i class="fas fa-list"><\/i> Manage Labs<\/h3>/);
  assert.doesNotMatch(html, /> Managed Labs<\/h3>/);
});
