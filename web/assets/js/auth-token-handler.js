/*
 * Administrative session helper.
 *
 * The browser never receives a reusable admin token in a URL or browser storage,
 * an Authorization header.  The token is submitted once to the Gateway's
 * POST login endpoint, which returns a path-scoped HttpOnly cookie.
 */
(function () {
    'use strict';

    const TOKEN_CONFIG = {
        '/lab-manager': { key: 'lab-manager', login: '/lab-manager/login', title: 'Lab Manager Access Token', description: 'This area requires a Lab Manager access token.' },
        '/lab-admin': { key: 'lab-manager', login: '/lab-manager/login', title: 'Lab Manager Access Token', description: 'Lab publishing operations require a Lab Manager access token.' },
        '/ops': { key: 'lab-manager', login: '/lab-manager/login', title: 'Lab Manager Access Token', description: 'Lab Station operations require a Lab Manager access token.' },
        '/aas-admin': { key: 'lab-manager', login: '/lab-manager/login', title: 'Lab Manager Access Token', description: 'AAS administration requires a Lab Manager access token.' },
        '/wallet': { key: 'billing', login: '/admin/login', title: 'Wallet & Billing Access Token', description: 'This area requires a Wallet & Billing access token.' },
        '/billing': { key: 'billing', login: '/admin/login', title: 'Wallet & Billing Access Token', description: 'This area requires a Wallet & Billing access token.' },
        '/wallet-dashboard': { key: 'billing', login: '/admin/login', title: 'Wallet & Billing Access Token', description: 'This area requires a Wallet & Billing access token.' },
        '/institution-config': { key: 'billing', login: '/admin/login', title: 'Wallet & Billing Access Token', description: 'This area requires a Wallet & Billing access token.' }
    };

    const activePrompt = { key: null, callbacks: [] };

    function createTokenModal() {
        if (document.getElementById('authTokenModal')) return;
        document.body.insertAdjacentHTML('beforeend', `
            <div id="authTokenModal" class="auth-token-modal" hidden>
                <div class="auth-token-modal-overlay"></div>
                <div class="auth-token-modal-content">
                    <div class="auth-token-modal-header"><h2 id="authTokenModalTitle">Access Token Required</h2><button id="authTokenModalClose" type="button">&times;</button></div>
                    <div class="auth-token-modal-body"><p id="authTokenModalDescription"></p><input type="password" id="authTokenInput" autocomplete="off" maxlength="512"><div id="authTokenError" class="auth-token-error" hidden></div></div>
                    <div class="auth-token-modal-footer"><button id="authTokenCancel" type="button">Cancel</button><button id="authTokenSubmit" type="button">Submit</button></div>
                </div>
            </div>`);
        const modal = document.getElementById('authTokenModal');
        document.getElementById('authTokenModalClose').addEventListener('click', hideTokenModal);
        document.getElementById('authTokenCancel').addEventListener('click', hideTokenModal);
        modal.querySelector('.auth-token-modal-overlay').addEventListener('click', hideTokenModal);
        document.getElementById('authTokenInput').addEventListener('keydown', e => {
            if (e.key === 'Enter') document.getElementById('authTokenSubmit').click();
        });
    }

    function hideTokenModal() {
        const modal = document.getElementById('authTokenModal');
        if (modal) { modal.hidden = true; modal.classList.remove('show'); }
        activePrompt.key = null;
        activePrompt.callbacks = [];
    }

    function showError(message) {
        const node = document.getElementById('authTokenError');
        node.textContent = message;
        node.hidden = false;
    }

    function showTokenModal(config, callback) {
        createTokenModal();
        const modal = document.getElementById('authTokenModal');
        if (activePrompt.key === config.key && !modal.hidden) {
            if (callback) activePrompt.callbacks.push(callback);
            return;
        }
        activePrompt.key = config.key;
        activePrompt.callbacks = callback ? [callback] : [];
        document.getElementById('authTokenModalTitle').textContent = config.title;
        document.getElementById('authTokenModalDescription').textContent = config.description;
        const input = document.getElementById('authTokenInput');
        const submit = document.getElementById('authTokenSubmit');
        const error = document.getElementById('authTokenError');
        input.value = '';
        error.hidden = true;
        modal.hidden = false;
        modal.classList.add('show');
        input.focus();
        submit.onclick = async function () {
            const token = input.value.trim();
            if (!token) return showError('Please enter a token');
            submit.disabled = true;
            try {
                const response = await fetch(config.login, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: new URLSearchParams({ token })
                });
                if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
                const callbacks = activePrompt.callbacks.slice();
                hideTokenModal();
                callbacks.forEach(cb => cb());
            } catch (err) {
                showError(err.message || 'Authentication failed');
            } finally {
                submit.disabled = false;
            }
        };
    }

    function getTokenConfigForPath(path) {
        let best = null;
        let length = -1;
        for (const [prefix, config] of Object.entries(TOKEN_CONFIG)) {
            if (path.startsWith(prefix) && prefix.length > length) {
                best = config;
                length = prefix.length;
            }
        }
        return best;
    }

    function requestPath(value) {
        try { return new URL(value, window.location.origin).pathname; } catch (_) { return window.location.pathname; }
    }

    function createAuthenticatedFetch() {
        const originalFetch = window.fetch;
        window.fetch = function (url, options = {}) {
            const skip = options.skipAuthPrompt === true;
            if (skip) {
                options = { ...options };
                delete options.skipAuthPrompt;
            }
            const config = getTokenConfigForPath(requestPath(url)) || getTokenConfigForPath(window.location.pathname);
            return originalFetch(url, { credentials: 'same-origin', ...options }).then(response => {
                if (response.status !== 401 || !config || skip) return response;
                return new Promise((resolve, reject) => showTokenModal(config, () => {
                    originalFetch(url, { credentials: 'same-origin', ...options }).then(retry => {
                        if (retry.status === 401) reject(new Error('Authentication failed'));
                        else resolve(retry);
                    }).catch(reject);
                }));
            });
        };
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => { createTokenModal(); createAuthenticatedFetch(); });
    } else {
        createTokenModal();
        createAuthenticatedFetch();
    }

    window.AuthTokenHandler = { showTokenModal, hideTokenModal, getTokenConfigForPath };
})();
