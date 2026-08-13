import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';
import test from 'node:test';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const webRoot = path.join(repoRoot, 'web');

function contentType(filePath) {
  if (filePath.endsWith('.html')) return 'text/html; charset=utf-8';
  if (filePath.endsWith('.js')) return 'text/javascript; charset=utf-8';
  if (filePath.endsWith('.css')) return 'text/css; charset=utf-8';
  return 'application/octet-stream';
}

function startSmokeServer() {
  const requests = [];
  const server = http.createServer((request, response) => {
    const requestUrl = new URL(request.url, 'http://127.0.0.1');
    requests.push(requestUrl.pathname);
    if (requestUrl.pathname.startsWith('/ops/') || requestUrl.pathname.startsWith('/lab-admin/')) {
      response.writeHead(200, { 'Content-Type': 'application/json' });
      if (requestUrl.pathname.endsWith('/power/controllers')) {
        response.end(JSON.stringify({ controllers: [] }));
      } else if (requestUrl.pathname.endsWith('/power/policies')) {
        response.end(JSON.stringify({ policies: [] }));
      } else if (requestUrl.pathname.endsWith('/labs')) {
        response.end(JSON.stringify({ labs: [] }));
      } else {
        response.end(JSON.stringify({}));
      }
      return;
    }

    const relativePath = requestUrl.pathname === '/'
      ? '/lab-manager/index.html'
      : requestUrl.pathname;
    const filePath = path.resolve(webRoot, `.${relativePath}`);
    if (!filePath.startsWith(`${webRoot}${path.sep}`) || !fs.existsSync(filePath)) {
      response.writeHead(404);
      response.end('Not found');
      return;
    }
    response.writeHead(200, { 'Content-Type': contentType(filePath) });
    response.end(fs.readFileSync(filePath));
  });

  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      resolve({ server, url: `http://127.0.0.1:${address.port}/lab-manager/index.html`, requests });
    });
  });
}

function firefoxPath() {
  const candidates = [
    process.env.LAB_MANAGER_FIREFOX,
    'C:\\Program Files\\Mozilla Firefox\\firefox.exe',
    'C:\\Program Files (x86)\\Mozilla Firefox\\firefox.exe',
    '/usr/bin/firefox',
    '/usr/lib/firefox/firefox',
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function stopFirefoxProcessTree(pid) {
  if (!pid) return;
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], {
      stdio: 'ignore',
      windowsHide: true,
    });
  } else {
    try {
      process.kill(pid, 'SIGKILL');
    } catch {
      // The browser may already have exited.
    }
  }
}

async function runFirefoxScreenshot(browser, args, screenshot) {
  const child = spawn(browser, args, { windowsHide: true, stdio: 'pipe' });
  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
  child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
  const close = new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('close', (status, signal) => resolve({ status, signal, stdout, stderr }));
  });
  const deadline = Date.now() + 15000;
  try {
    while (!fs.existsSync(screenshot) && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    const result = await Promise.race([
      close,
      new Promise((resolve) => setTimeout(() => resolve({ status: null, signal: null, stdout, stderr }), 1000)),
    ]);
    return { ...result, screenshotReady: fs.existsSync(screenshot) };
  } finally {
    stopFirefoxProcessTree(child.pid);
  }
}

test('renders Lab Manager Power Controllers in a real headless browser', async (t) => {
  const browser = firefoxPath();
  if (!browser) {
    t.skip('Firefox is not installed; set LAB_MANAGER_FIREFOX to run the browser smoke test');
    return;
  }

  const { server, url, requests } = await startSmokeServer();
  const tempDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'lab-manager-smoke-'));
  const screenshot = path.join(tempDirectory, 'lab-manager.png');
  try {
    const result = await runFirefoxScreenshot(browser, [
      '--headless',
      '--no-remote',
      '--profile', tempDirectory,
      '--window-size', '1440,1200',
      '--screenshot', screenshot,
      url,
    ], screenshot);
    assert.ok(result.status === 0 || result.screenshotReady, `${result.stdout}\n${result.stderr}`);
    assert.ok(
      result.screenshotReady,
      `Firefox did not produce a screenshot; files: ${fs.readdirSync(tempDirectory).join(', ')}`,
    );
    assert.ok(fs.statSync(screenshot).size > 0, 'Firefox produced an empty screenshot');
    assert.ok(requests.includes('/ops/api/power/controllers'), 'Lab Manager did not load power controllers');
  } finally {
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(tempDirectory, { recursive: true, force: true });
  }
});
