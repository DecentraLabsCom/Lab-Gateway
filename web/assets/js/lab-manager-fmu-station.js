(function (root) {
    'use strict';

    function normalize(value) {
        return String(value || '').trim().replace(/\.$/, '').toLowerCase();
    }

    function createController({
        fetchImpl,
        showLoadingToast = () => {},
        showToast = () => {},
        onStateChanged = () => {},
        logger = console,
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerFmuStation requires fetchImpl');
        }

        let status = null;
        let busyHost = '';

        function getState() {
            return {
                ...(status || {}),
                busyHost,
            };
        }

        function notifyStateChanged() {
            onStateChanged(getState());
        }

        function getLinkStatus() {
            if (status && ['linked', 'unlinked', 'unknown'].includes(status.linkStatus)) {
                return status.linkStatus;
            }
            if (status && typeof status.linked === 'boolean') {
                return status.linked ? 'linked' : 'unlinked';
            }
            if (status && typeof status.runner?.stationAuthenticated === 'boolean') {
                return status.runner.stationAuthenticated ? 'linked' : 'unlinked';
            }
            return 'unknown';
        }

        function isConfiguredTarget(host) {
            return Boolean(host)
                && normalize(host) === normalize(status?.stationHost);
        }

        async function load() {
            try {
                const response = await fetchImpl('/ops/api/fmu/station', {
                    cache: 'no-store',
                });
                const body = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
                status = body;
                notifyStateChanged();
                return true;
            } catch (error) {
                status = null;
                notifyStateChanged();
                logger.warn('Unable to load FMU Station status', error);
                return false;
            }
        }

        async function handleAction(host, action) {
            const targetHost = String(host || '').trim();
            if (!targetHost || !isConfiguredTarget(targetHost)) {
                showToast('This station is not the Gateway FMU Station target', 'error');
                return false;
            }
            if (busyHost) return false;

            const linkStatus = getLinkStatus();
            const linked = linkStatus === 'linked';
            const linking = action === 'link-fmu';
            const releasing = action === 'release-fmu';
            if (!linking && !releasing) return false;
            if (linkStatus === 'unknown') {
                showToast('FMU token link status cannot be verified right now', 'error');
                return false;
            }
            if (linking && linked) {
                showToast('An FMU token is already linked to a Lab Station', 'error');
                return false;
            }
            if (releasing && !linked) {
                showToast('No FMU token is currently linked to this Lab Station', 'error');
                return false;
            }

            busyHost = targetHost;
            notifyStateChanged();
            const endpoint = linking
                ? '/ops/api/fmu/station/enroll'
                : '/ops/api/fmu/station/release';
            showLoadingToast(`${linking ? 'Linking' : 'Releasing'} FMU token on ${targetHost}...`);
            try {
                const response = await fetchImpl(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ host: targetHost }),
                });
                const body = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
                showToast(
                    linking
                        ? `FMU token linked on ${body.host || targetHost}; background service restarted`
                        : `FMU token released from ${body.host || targetHost}; background service restarted`,
                    'success',
                );
                await load();
                return true;
            } catch (error) {
                showToast(
                    `${linking ? 'FMU token link' : 'FMU token release'} failed: ${error.message}`,
                    'error',
                );
                return false;
            } finally {
                busyHost = '';
                notifyStateChanged();
            }
        }

        return Object.freeze({
            getState,
            handleAction,
            initialize: load,
            load,
            link: host => handleAction(host, 'link-fmu'),
            release: host => handleAction(host, 'release-fmu'),
        });
    }

    root.LabManagerFmuStation = Object.freeze({ createController });
})(window);
