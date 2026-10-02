import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repoRoot = new URL('../../', import.meta.url);
const scriptPath = new URL('web/assets/js/auth-token-handler.js', repoRoot);

function createElement(id) {
  const listeners = new Map();
  return {
    id,
    hidden: false,
    disabled: false,
    value: '',
    textContent: '',
    classList: { add() {}, remove() {} },
    addEventListener(type, handler) { listeners.set(type, handler); },
    click() { return this.onclick?.(); },
    focus() {},
    select() {},
    querySelector() { return createElement(`${id}-overlay`); },
  };
}

function loadHandler(fetchImpl) {
  const elements = new Map();
  const document = {
    readyState: 'complete',
    body: {
      insertAdjacentHTML() {
        for (const id of [
          'authTokenModal',
          'authTokenModalClose',
          'authTokenCancel',
          'authTokenModalTitle',
          'authTokenModalDescription',
          'authTokenInput',
          'authTokenError',
          'authTokenSubmit',
        ]) {
          elements.set(id, createElement(id));
        }
      },
    },
    getElementById(id) { return elements.get(id) || null; },
  };
  const window = {
    location: { origin: 'https://gateway.example', pathname: '/lab-manager/' },
    fetch: fetchImpl,
  };
  const context = vm.createContext({
    document,
    window,
    fetch: fetchImpl,
    URL,
    URLSearchParams,
    Promise,
  });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, {
    filename: 'auth-token-handler.js',
  });
  return { handler: context.window.AuthTokenHandler, elements };
}

test('establishes the billing session before releasing the Notifications callback', async () => {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (url === '/admin/login') {
      return { ok: true, status: 204, text: async () => '' };
    }
    if (url === '/wallet-dashboard/') {
      return {
        ok: true,
        status: 200,
        url: 'https://gateway.example/wallet-dashboard/',
      };
    }
    throw new Error(`Unexpected request: ${url}`);
  };
  const { handler, elements } = loadHandler(fetchImpl);
  let callbackCalls = 0;

  handler.showTokenModal({
    key: 'billing',
    login: '/admin/login',
    title: 'Gateway administrator token required',
    description: 'Enter the Gateway administrator token for Wallet & Billing.',
    invalidMessage: 'Invalid Gateway administrator token.',
  }, () => {
    callbackCalls += 1;
  });
  elements.get('authTokenInput').value = 'billing-secret';
  await elements.get('authTokenSubmit').click();

  assert.equal(callbackCalls, 1, elements.get('authTokenError').textContent);
  assert.deepEqual(calls.map(({ url }) => url), ['/admin/login', '/wallet-dashboard/']);
  assert.equal(calls[0].options.method, 'POST');
});
