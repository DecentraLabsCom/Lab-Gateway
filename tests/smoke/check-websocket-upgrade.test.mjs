import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import tls from 'node:tls';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import test from 'node:test';

const smokeDir = path.dirname(fileURLToPath(import.meta.url));
const probePath = path.join(smokeDir, 'check-websocket-upgrade.mjs');
const certificate = fs.readFileSync(path.join(smokeDir, 'certs', 'fullchain.pem'));
const privateKey = fs.readFileSync(path.join(smokeDir, 'certs', 'privkey.pem'));

function runProbe(port) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [probePath, '127.0.0.1', String(port), 'lab.test']);
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('error', reject);
    child.on('close', (code) => resolve({ code, stdout, stderr }));
  });
}

async function withTlsServer(response, assertion) {
  const server = tls.createServer({ cert: certificate, key: privateKey }, (socket) => {
    socket.on('error', () => {});
    socket.once('data', () => socket.end(response));
  });

  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });

  try {
    await assertion(server.address().port);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

test('reports a bare WebSocket 101 upgrade as successful', async () => {
  await withTlsServer(
    'HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n',
    async (port) => {
      const result = await runProbe(port);
      assert.equal(result.code, 0, result.stderr);
      assert.equal(result.stdout, '101\n');
    }
  );
});

test('rejects a non-upgrade HTTP response', async () => {
  await withTlsServer('HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n', async (port) => {
    const result = await runProbe(port);
    assert.equal(result.code, 0, result.stderr);
    assert.equal(result.stdout, '000\n');
  });
});
