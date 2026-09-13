(function (root) {
    'use strict';

    function createController({
        fetchImpl,
        candidateState,
        callbacks = {},
        logger = console,
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerHostDiscovery requires fetchImpl');
        }
        if (!candidateState) {
            throw new Error('LabManagerHostDiscovery requires candidate state');
        }

        const {
            renderCandidates = () => {},
            loadHostInventory = () => {},
            showToast = () => {},
        } = callbacks;

        async function probe(stationKey, station, button) {
            const representative = station?.connections?.[0];
            candidateState[stationKey] = {
                ...(candidateState[stationKey] || {}),
                candidate: representative,
                connectionId: representative?.id,
                status: 'checking',
            };
            if (button) button.disabled = true;
            renderCandidates();
            try {
                const res = await fetchImpl('/ops/api/hosts/discover', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ connectionId: representative?.id }),
                });
                const body = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(body.error || `HTTP ${res.status}`);
                }
                const winrmOpen = Object.entries(body.checks?.winrm || {})
                    .filter(([, open]) => open)
                    .map(([port]) => port);
                const suggestedMac = body.opsHostDraft?.mac;
                const detail = body.status === 'labstation-detected'
                    ? `HTTP health matched at ${body.checks?.labStationHttp?.url || 'configured discovery endpoint'}`
                    : winrmOpen.length
                        ? `Open WinRM port${winrmOpen.length === 1 ? '' : 's'}: ${winrmOpen.join(', ')}`
                        : 'No Lab Station health endpoint or WinRM port detected.';
                candidateState[stationKey] = {
                    ...(candidateState[stationKey] || {}),
                    candidate: body.connection || representative,
                    connectionId: body.connection?.id || representative?.id,
                    status: body.status,
                    detail: suggestedMac ? `${detail} Suggested MAC: ${suggestedMac}` : detail,
                    opsHostDraft: body.opsHostDraft || {},
                };
                showToast(
                    `Discovery finished for ${body.connection?.hostname || station.address || representative?.id}`,
                    'success',
                );
            } catch (err) {
                logger.error(err);
                candidateState[stationKey] = {
                    ...(candidateState[stationKey] || {}),
                    candidate: representative,
                    connectionId: representative?.id,
                    status: 'error',
                    detail: err.message,
                };
                showToast(`Lab Station check failed: ${err.message}`, 'error');
            } finally {
                loadHostInventory();
            }
        }

        return Object.freeze({ probe });
    }

    root.LabManagerHostDiscovery = Object.freeze({ createController });
})(window);
