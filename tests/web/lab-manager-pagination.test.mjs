import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/core/pagination.js', repoRoot);

function loadPagination() {
  const context = vm.createContext({ window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'pagination.js',
  });
  return context.window.LabManagerPagination;
}

test('preserves explicit pagination metadata', () => {
  const pagination = loadPagination().normalizePagination(
    { limit: 20, total: 100, nextOffset: 40, hasMore: true, page: 2, pageSize: 20 },
    20,
    20,
    8,
  );

  assert.equal(pagination.limit, 20);
  assert.equal(pagination.offset, 20);
  assert.equal(pagination.returned, 20);
  assert.equal(pagination.total, 100);
  assert.equal(pagination.nextOffset, 40);
  assert.equal(pagination.hasMore, true);
  assert.equal(pagination.page, 2);
  assert.equal(pagination.pageSize, 20);
});

test('derives safe defaults when pagination metadata is missing or invalid', () => {
  const pagination = loadPagination().normalizePagination(
    { limit: 0, total: 'invalid', nextOffset: 'invalid', hasMore: undefined, page: NaN, pageSize: 'invalid' },
    12,
    3,
    8,
  );

  assert.equal(pagination.limit, 8);
  assert.equal(pagination.offset, 12);
  assert.equal(pagination.returned, 3);
  assert.equal(pagination.total, 15);
  assert.equal(pagination.nextOffset, 15);
  assert.equal(pagination.hasMore, false);
  assert.equal(pagination.page, 2);
  assert.equal(pagination.pageSize, 8);
});
