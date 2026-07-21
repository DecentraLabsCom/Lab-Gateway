(function () {
    'use strict';
    const form = document.getElementById('adminLoginForm');
    const input = document.getElementById('token');
    const error = document.getElementById('error');
    const scope = new URLSearchParams(window.location.search).get('scope') || 'billing';
    const isLabManager = scope === 'lab-manager';
    const destination = isLabManager ? '/lab-manager/' :
        (scope === 'institution-config' ? '/institution-config/' : '/wallet-dashboard/');
    const endpoint = isLabManager ? '/lab-manager/login' : '/admin/login';
    document.title = isLabManager ? 'Lab Manager sign-in' : 'Gateway administrator sign-in';
    document.getElementById('loginTitle').textContent = isLabManager
        ? 'Lab Manager sign-in'
        : 'Gateway administrator sign-in';
    document.getElementById('loginDescription').textContent = isLabManager
        ? 'Enter the Lab Manager token. It is exchanged for an HttpOnly session cookie and is never stored in browser storage.'
        : 'Enter the Gateway administrator token for Wallet & Billing. It is exchanged for an HttpOnly session cookie and is never stored in browser storage.';
    document.getElementById('tokenLabel').textContent = isLabManager
        ? 'Lab Manager token'
        : 'Gateway administrator token';
    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        error.hidden = true;
        const token = input.value.trim();
        if (!token) return;
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ token })
            });
            if (!response.ok) {
                const message = await response.text();
                throw new Error(response.status === 401
                    ? (isLabManager ? 'Invalid Lab Manager token.' : 'Invalid Gateway administrator token.')
                    : (message || `HTTP ${response.status}`));
            }
            window.location.replace(destination);
        } catch (err) {
            error.textContent = err.message || 'Sign-in failed';
            error.hidden = false;
            input.focus();
            input.select();
        }
    });
})();
