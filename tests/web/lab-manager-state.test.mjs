import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/core/state.js', repoRoot);

function loadState() {
  const context = vm.createContext({ window: {} });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'state.js',
  });
  return context.window.LabManagerState;
}

test('claims each manager tab only once per bootstrap', () => {
  const stateModule = loadState();
  const state = stateModule.createTabActivationState();

  assert.equal(state.claimTab('operations'), true);
  assert.equal(state.claimTab('operations'), false);
  assert.equal(state.isTabInitialized('operations'), true);
  assert.equal(state.isTabInitialized('energy'), false);
  assert.equal(state.claimTab(''), false);
  assert.equal(state.claimTab(null), false);
});
