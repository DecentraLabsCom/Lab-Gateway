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
const FIREFOX_SCREENSHOT_ATTEMPTS = 2;

function contentType(filePath) {
  if (filePath.endsWith('.html')) return 'text/html; charset=utf-8';
  if (filePath.endsWith('.js')) return 'text/javascript; charset=utf-8';
  if (filePath.endsWith('.css')) return 'text/css; charset=utf-8';
  return 'application/octet-stream';
}

function startSmokeServer() {
  const requests = [];
  let liteMode = false;
  const server = http.createServer((request, response) => {
    const requestUrl = new URL(request.url, 'http://127.0.0.1');
    requests.push(requestUrl.pathname);
    if (requestUrl.pathname === '/gateway/mode') {
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ mode: liteMode ? 'lite' : 'full', lite: liteMode }));
      return;
    }
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
      resolve({
        server,
        url: `http://127.0.0.1:${address.port}/lab-manager/index.html`,
        requests,
        setLiteMode: (value) => { liteMode = Boolean(value); },
      });
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

async function runFirefoxScreenshotOnce(browser, args, screenshot, isReady = () => true) {
  const child = spawn(browser, args, {
    cwd: path.dirname(screenshot),
    windowsHide: true,
    stdio: 'pipe',
  });
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
    const readinessDeadline = Date.now() + 15000;
    while (fs.existsSync(screenshot) && !isReady() && Date.now() < readinessDeadline) {
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

async function runFirefoxScreenshot(browser, args, screenshot, isReady = () => true) {
  let result;
  for (let attempt = 1; attempt <= FIREFOX_SCREENSHOT_ATTEMPTS; attempt += 1) {
    fs.rmSync(screenshot, { force: true });
    result = await runFirefoxScreenshotOnce(browser, args, screenshot, isReady);
    result.attempts = attempt;
    if (result.screenshotReady) return result;
  }
  return result;
}

function firefoxScreenshotArgs(profile, url) {
  return [
    '--headless',
    '--no-remote',
    '--profile', profile,
    '--window-size', '1440,1200',
    '--screenshot',
    url,
  ];
}

function firefoxFailureMessage(result, screenshot, directory) {
  return [
    `Firefox did not produce ${screenshot} after ${result.attempts} attempt(s)`,
    `status=${result.status ?? 'unknown'}`,
    `signal=${result.signal ?? 'none'}`,
    `screenshotReady=${result.screenshotReady}`,
    `files=${fs.readdirSync(directory).join(', ')}`,
    `stdout=${result.stdout}`,
    `stderr=${result.stderr}`,
  ].join('\n');
}

test('renders workflow tabs and lazily loads their data in a real headless browser', async (t) => {
  const browser = firefoxPath();
  if (!browser) {
    t.skip('Firefox is not installed; set LAB_MANAGER_FIREFOX to run the browser smoke test');
    return;
  }

  const { server, url, requests, setLiteMode } = await startSmokeServer();
  const tempDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'lab-manager-smoke-'));
  const labsProfile = path.join(tempDirectory, 'labs-profile');
  const energyProfile = path.join(tempDirectory, 'energy-profile');
  const liteProfile = path.join(tempDirectory, 'lite-profile');
  const labsOutput = path.join(tempDirectory, 'labs-output');
  const energyOutput = path.join(tempDirectory, 'energy-output');
  const liteOutput = path.join(tempDirectory, 'lite-output');
  fs.mkdirSync(labsProfile);
  fs.mkdirSync(energyProfile);
  fs.mkdirSync(liteProfile);
  fs.mkdirSync(labsOutput);
  fs.mkdirSync(energyOutput);
  fs.mkdirSync(liteOutput);
  const labsScreenshot = path.join(labsOutput, 'screenshot.png');
  const energyScreenshot = path.join(energyOutput, 'screenshot.png');
  const liteScreenshot = path.join(liteOutput, 'screenshot.png');
  try {
    const labsResult = await runFirefoxScreenshot(
      browser,
      firefoxScreenshotArgs(labsProfile, url),
      labsScreenshot,
      () => requests.includes('/lab-admin/status'),
    );
    assert.ok(labsResult.screenshotReady, firefoxFailureMessage(labsResult, labsScreenshot, tempDirectory));
    assert.ok(fs.statSync(labsScreenshot).size > 0, 'Firefox produced an empty Laboratories screenshot');
    assert.ok(requests.includes('/lab-admin/status'), 'The default Laboratories tab did not load publisher status');
    assert.equal(requests.includes('/ops/api/power/controllers'), false, 'Energy loaded before its tab was opened');
    assert.equal(requests.includes('/billing/admin/notifications'), false, 'Notifications loaded before its tab was opened');

    requests.length = 0;
    const energyResult = await runFirefoxScreenshot(
      browser,
      firefoxScreenshotArgs(energyProfile, `${url}#energy`),
      energyScreenshot,
      () => requests.includes('/ops/api/power/policies'),
    );
    assert.ok(energyResult.screenshotReady, firefoxFailureMessage(energyResult, energyScreenshot, tempDirectory));
    assert.ok(fs.statSync(energyScreenshot).size > 0, 'Firefox produced an empty Energy screenshot');
    assert.ok(requests.includes('/ops/api/power/controllers'), 'Lab Manager did not load power controllers');
    assert.ok(requests.includes('/ops/api/power/credentials'), 'Lab Manager did not load power credentials');
    assert.ok(requests.includes('/ops/api/power/policies'), 'Lab Manager did not load power policies');
    assert.equal(requests.includes('/billing/admin/notifications'), false, 'Energy requested the Notifications admin session');

    requests.length = 0;
    setLiteMode(true);
    const liteResult = await runFirefoxScreenshot(
      browser,
      firefoxScreenshotArgs(liteProfile, `${url}#notifications`),
      liteScreenshot,
      () => requests.includes('/lab-admin/status'),
    );
    assert.ok(liteResult.screenshotReady, firefoxFailureMessage(liteResult, liteScreenshot, tempDirectory));
    assert.ok(requests.includes('/lab-admin/status'), 'A Full-only deep link did not fall back to Laboratories in Lite mode');
    assert.equal(requests.includes('/billing/admin/notifications'), false, 'Lite mode attempted to open Full-only Notifications');
  } finally {
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(tempDirectory, {
      recursive: true,
      force: true,
      maxRetries: 20,
      retryDelay: 200,
    });
  }
});
