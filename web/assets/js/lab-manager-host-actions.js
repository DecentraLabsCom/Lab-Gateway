(function (root) {
    'use strict';

    function createController({
        fetchImpl,
        callbacks = {},
        logger = console,
        waitImpl = delayMs => new Promise(resolve => root.setTimeout(resolve, delayMs)),
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerHostActions requires fetchImpl');
        }

        const {
            pollHeartbeat = () => {},
            updateLocalModeState = () => {},
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
                const localModeEnabled = typeof data.localModeEnabled === 'boolean'
                    ? data.localModeEnabled
                    : enabled;
                updateLocalModeState(host, localModeEnabled);
                showToast(`Local mode ${localModeEnabled ? 'enabled' : 'disabled'} for ${host}`, 'success');
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
                // Lab Station can finish the session guard just before its
                // telemetry writer publishes the new heartbeat. Give that
                // writer a short settling window, then retry once. This also
                // applies to exit_code 1 because the session guard may still
                // have completed successfully with a warning.
                if (command === 'prepare-session') {
                    await waitImpl(2000);
                    await pollHeartbeat(host, { silent: true });
                    await waitImpl(3000);
                    await pollHeartbeat(host, { silent: true });
                }
                if (command === 'power') {
                    await waitImpl(1000);
                    await pollHeartbeat(host, { silent: true });
                }
                showToast(`${command} on ${host}: ${ok ? 'ok' : 'err'}`, ok ? 'success' : 'error');
            } catch (err) {
                logger.error(err);
                showToast(`${command} failed on ${host}: ${err.message}`, 'error');
            }
        }

        return Object.freeze({
            toggleLocalMode,
            triggerWol,
            triggerWinrm,
        });
    }

    root.LabManagerHostActions = Object.freeze({ createController });
})(window);
