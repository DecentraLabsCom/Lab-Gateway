(function () {
    'use strict';
    const form = document.getElementById('adminLoginForm');
    const input = document.getElementById('token');
    const error = document.getElementById('error');
    const scope = new URLSearchParams(window.location.search).get('scope') || 'billing';
    const destination = scope === 'lab-manager' ? '/lab-manager/' :
        (scope === 'institution-config' ? '/institution-config/' : '/wallet-dashboard/');
    const endpoint = scope === 'lab-manager' ? '/lab-manager/login' : '/admin/login';
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
            if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
            window.location.replace(destination);
        } catch (err) {
            error.textContent = err.message || 'Sign-in failed';
            error.hidden = false;
            input.select();
        }
    });
})();
