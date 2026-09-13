(function (root) {
    'use strict';

    function createController({
        fetchImpl,
        callbacks = {},
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerWinrmCredentials requires fetchImpl');
        }

        const {
            closeModal = () => {},
            loadHostInventory = () => {},
            showToast = () => {},
        } = callbacks;

        async function save(payload, submitButton) {
            if (!payload?.credentialRef || !payload?.user || !payload?.password) {
                showToast('WinRM credential reference, user, and password are required', 'error');
                return false;
            }
            if (submitButton) submitButton.disabled = true;
            try {
                const res = await fetchImpl('/ops/api/hosts/winrm-credentials', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const body = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(body.error || `HTTP ${res.status}`);
                }
                closeModal();
                showToast('WinRM credentials saved', 'success');
                loadHostInventory();
                return true;
            } catch (err) {
                showToast(`WinRM credential save failed: ${err.message}`, 'error');
                return false;
            } finally {
                if (submitButton) submitButton.disabled = false;
            }
        }

        return Object.freeze({ save });
    }

    root.LabManagerWinrmCredentials = Object.freeze({ createController });
})(window);
