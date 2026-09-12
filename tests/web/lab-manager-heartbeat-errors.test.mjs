import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/lab-manager-heartbeat-errors.js', repoRoot);

function loadHeartbeatErrors() {
  const window = {};
  const context = vm.createContext({ window });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'lab-manager-heartbeat-errors.js',
  });
  return window.LabManagerHeartbeatErrors;
}

test('classifies only the existing WinRM configuration heartbeat errors', () => {
  const errors = loadHeartbeatErrors();

  assert.equal(errors.isConfigurationError(' WINRM_TRUST_REQUIRED '), true);
  assert.equal(errors.isConfigurationError('WINRM_CERTIFICATE_EXPIRED'), true);
  assert.equal(errors.isConfigurationError('INTERNAL_ERROR'), false);
  assert.equal(errors.isConfigurationError('UNKNOWN_ERROR'), false);
  assert.equal(errors.isConfigurationError(null), false);
});

test('formats public heartbeat errors and restricts request IDs to generic failures', () => {
  const errors = loadHeartbeatErrors();

  assert.equal(
    errors.formatStreamError('PC-Siemens', {
      code: 'WINRM_TRUST_REQUIRED',
      requestId: 'trust-request-1',
      error: 'private server detail',
    }),
    'Heartbeat unavailable for PC-Siemens: WinRM certificate trust is required',
  );
  assert.equal(
    errors.formatStreamError('PC-Siemens', {
      code: 'INTERNAL_ERROR',
      requestId: 'f33bb129cf1e475f8bc3db34ce2fe5dc',
    }),
    'Heartbeat unavailable for PC-Siemens: temporary Ops Worker error (request ID f33bb129cf1e475f8bc3db34ce2fe5dc)',
  );
  assert.equal(
    errors.formatStreamError('PC-Siemens', {
      code: 'INTERNAL_ERROR',
      requestId: '{"error":"secret"}',
    }),
    'Heartbeat unavailable for PC-Siemens: temporary Ops Worker error',
  );
});
