(function (root) {
    'use strict';

    function createController({
        fetchImpl,
        callbacks = {},
        logger = console,
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerHostActions requires fetchImpl');
        }

        const {
            pollHeartbeat = () => {},
            showLoadingToast = () => {},
            showToast = () => {},
        } = callbacks;

        async function toggleLocalMode(host, enabled) {
            showLoadingToast(`${enabled ? 'Enabling' : 'Disabling'} local mode for ${host}…`);
            try {
                const res = await fetchImpl('/ops/api/hosts/local-mode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ host, enabled }),
                });
                if (res.status === 403) {
                    showToast('Access denied: /ops blocked by Lab Manager access policy', 'error');
                    return;
                }
                if (res.status === 401) {
                    showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                await pollHeartbeat(host);
                showToast(`Local mode ${data.localModeEnabled ? 'enabled' : 'disabled'} for ${host}`, 'success');
            } catch (err) {
                logger.error(err);
                showToast(`Local mode toggle failed for ${host}: ${err.message}`, 'error');
            }
        }

        async function triggerWol(host) {
            showLoadingToast(`Waking ${host}…`);
            try {
                const res = await fetchImpl('/ops/api/wol', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ host }),
                });
                if (res.status === 403) {
                    showToast('Access denied: /ops blocked by Lab Manager access policy', 'error');
                    return;
                }
                if (res.status === 401) {
                    showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                    return;
                }
                let data;
                try {
                    data = await res.json();
                } catch (err) {
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    throw err;
                }
                if (!res.ok) {
                    const reason = data && typeof data.error === 'string' && data.error.trim()
                        ? data.error
                        : `HTTP ${res.status}`;
                    throw new Error(reason);
                }
                showToast(`WoL ${host}: ${data.success ? 'sent' : 'failed'}`, data.success ? 'success' : 'error');
            } catch (err) {
                logger.error(err);
                showToast(`WoL failed for ${host}: ${err.message}`, 'error');
            }
        }

        async function triggerWinrm(host, command, args = []) {
            showLoadingToast(`${command} on ${host}…`);
            try {
                const res = await fetchImpl('/ops/api/winrm', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ host, command, args }),
                });
                if (res.status === 403) {
                    showToast('Access denied: /ops blocked by Lab Manager access policy', 'error');
                    return;
                }
                if (res.status === 401) {
                    showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                const ok = data.exit_code === 0;
                showToast(`${command} on ${host}: ${ok ? 'ok' : 'err'}`, ok ? 'success' : 'error');
            } catch (err) {
                logger.error(err);
                showToast(`${command} failed on ${host}: ${err.message}`, 'error');
            }
        }

        async function syncAasHost(host) {
            showLoadingToast(`Syncing AAS for ${host}…`);
            try {
                const res = await fetchImpl('/ops/api/aas-sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ host }),
                });
                if (res.status === 403) {
                    showToast('Access denied: /ops blocked by Lab Manager access policy', 'error');
                    return;
                }
                if (res.status === 401) {
                    showToast('Unauthorized: check LAB_MANAGER_TOKEN', 'error');
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                const labs = data.labs || [];
                if (!labs.length) {
                    showToast(`AAS sync ${host}: no catalog labs resolved`, 'error');
                    return;
                }
                const disabled = labs.every(l => l.disabled);
                if (disabled) {
                    showToast(`AAS sync ${host}: AAS not configured on this gateway`, 'error');
                    return;
                }
                const errors = labs.filter(l => l.error);
                if (errors.length) {
                    showToast(`AAS sync ${host}: ${errors.length}/${labs.length} failed`, 'error');
                } else {
                    showToast(`AAS sync ${host}: ${labs.length} lab(s) synced`, 'success');
                }
            } catch (err) {
                logger.error(err);
                showToast(`AAS sync failed for ${host}: ${err.message}`, 'error');
            }
        }

        return Object.freeze({
            toggleLocalMode,
            triggerWol,
            triggerWinrm,
            syncAasHost,
        });
    }

    root.LabManagerHostActions = Object.freeze({ createController });
})(window);
