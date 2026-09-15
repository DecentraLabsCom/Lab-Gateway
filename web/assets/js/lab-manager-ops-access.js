(function (root) {
    'use strict';

    function createController({
        opsHintEl,
        refreshHostsBtn,
        timelineBtn,
        fetchImpl,
        groupCandidates = () => [],
        logger = console,
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerOpsAccess requires fetchImpl');
        }
        if (typeof groupCandidates !== 'function') {
            throw new Error('LabManagerOpsAccess requires groupCandidates');
        }

        function updateHint(data) {
            if (!opsHintEl) return;
            if (!data) {
                opsHintEl.textContent = 'The ops inventory could not be loaded.';
                return;
            }
            const stationCount = groupCandidates(data.guacamoleUnmatched).length;
            const guacStatus = data.guacamoleAvailable
                ? `${stationCount} Lab Station candidate${stationCount === 1 ? '' : 's'} awaiting configuration.`
                : 'Guacamole inventory unavailable.';
            opsHintEl.textContent = `Hosts are loaded from ops-worker/hosts.json and ops-data/hosts.json. ${guacStatus}`;
        }

        async function refreshSession() {
            try {
                const res = await fetchImpl('/lab-manager/access-policy', {
                    credentials: 'same-origin',
                    cache: 'no-store',
                    skipAuthPrompt: true,
                });
                return res.ok;
            } catch (err) {
                logger.warn('Unable to refresh Lab Manager session', err);
                return false;
            }
        }

        function showWarning() {
            if (opsHintEl) {
                opsHintEl.innerHTML = `
                    <i class="fas fa-exclamation-triangle warning-icon"></i>
                    <strong>Access policy:</strong> Lab Station operations require an allowed Lab Manager network scope and a valid Lab Manager token.
                    Check ADMIN_DASHBOARD_LOCAL_ONLY, ADMIN_DASHBOARD_ALLOW_PRIVATE, SECURITY_ALLOW_PRIVATE_NETWORKS, and ADMIN_ALLOWED_CIDRS.
                `;
                opsHintEl.style.backgroundColor = '#fff3cd';
                opsHintEl.style.color = '#856404';
                opsHintEl.style.padding = '12px';
                opsHintEl.style.borderRadius = '4px';
                opsHintEl.style.border = '1px solid #ffc107';
            }
            if (refreshHostsBtn) refreshHostsBtn.disabled = true;
            if (timelineBtn) timelineBtn.disabled = true;
        }

        async function checkAvailability() {
            try {
                const res = await fetchImpl('/ops/health', { method: 'HEAD' });
                if (res.status === 403) {
                    showWarning();
                    return false;
                }
                return res.ok || res.status === 401;
            } catch {
                return false;
            }
        }

        return Object.freeze({
            checkAvailability,
            refreshSession,
            showWarning,
            updateHint,
        });
    }

    root.LabManagerOpsAccess = Object.freeze({ createController });
})(window);
