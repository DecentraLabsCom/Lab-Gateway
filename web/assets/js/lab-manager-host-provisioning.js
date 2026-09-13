(function (root) {
    'use strict';

    function createController({
        fetchImpl,
        callbacks = {},
        logger = console,
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerHostProvisioning requires fetchImpl');
        }

        const {
            closeModal = () => {},
            loadHostInventory = () => {},
            showToast = () => {},
        } = callbacks;

        async function save(payload, submitButton) {
            if (!payload?.connectionId || !payload?.name || !payload?.address) {
                showToast('Name and address are required', 'error');
                return false;
            }
            if (submitButton) submitButton.disabled = true;
            try {
                const res = await fetchImpl('/ops/api/hosts/provision', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const body = await res.json().catch(() => ({}));
                if (!res.ok) {
                    const requestSuffix = body.requestId ? ` (request ID ${body.requestId})` : '';
                    throw new Error(`${body.error || `HTTP ${res.status}`}${requestSuffix}`);
                }
                closeModal();
                showToast(`Ops host ${body.host?.name || payload.name} configured`, 'success');
                loadHostInventory();
                return true;
            } catch (err) {
                logger.error(err);
                showToast(`Configure host failed: ${err.message}`, 'error');
                return false;
            } finally {
                if (submitButton) submitButton.disabled = false;
            }
        }

        return Object.freeze({ save });
    }

    root.LabManagerHostProvisioning = Object.freeze({ createController });
})(window);
