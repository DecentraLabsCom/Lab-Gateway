(function (root) {
    'use strict';

    function createController({
        fetchImpl,
        getEventSource = () => root.EventSource,
        getOrigin = () => root.location.origin,
        state,
        callbacks = {},
        logger = console,
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerHosts requires fetchImpl');
        }
        if (!state || !state.hostState || !state.hostMetadata
            || !state.heartbeatSources || !state.heartbeatStreamErrorShown
            || typeof state.getHostNames !== 'function'
            || typeof state.setHostNames !== 'function') {
            throw new Error('LabManagerHosts requires host state');
        }

        const {
            renderHosts = () => {},
            loadActivityFeed = () => {},
            setGuacamoleCandidates = () => {},
            renderGuacamoleCandidates = () => {},
            rememberGuacamoleCandidate = () => {},
            groupGuacamoleCandidates = candidates => candidates,
            updateOpsHint = () => {},
            showOpsWarning = () => {},
            showLoadingToast = () => {},
            showToast = () => {},
            formatHeartbeatError = (host) => `Heartbeat unavailable for ${host}`,
            isHeartbeatConfigurationError = () => false,
        } = callbacks;

        const hostState = state.hostState;
        const hostMetadata = state.hostMetadata;
        const heartbeatSources = state.heartbeatSources;
        const heartbeatStreamErrorShown = state.heartbeatStreamErrorShown;
        const localModeOverrides = {};

        function stopHeartbeatStream(host) {
            const source = heartbeatSources[host];
            if (!source) return;
            try {
                source.close();
            } catch (_) {
                // Ignore errors while closing a browser-owned stream.
            }
            delete heartbeatSources[host];
            delete heartbeatStreamErrorShown[host];
        }

        function startHeartbeatStream(host) {
            const meta = hostMetadata[host] || {};
            const EventSourceCtor = getEventSource();
            if (
                !host
                || !EventSourceCtor
                || heartbeatSources[host]
                || meta.winrmConfigured !== true
                || meta.winrmTrustStatus !== 'ready'
            ) return;

            const url = new URL('/ops/api/heartbeat/stream', getOrigin());
            url.searchParams.set('host', host);
            url.searchParams.set('include_events', 'false');

            const source = new EventSourceCtor(url.toString());
            heartbeatSources[host] = source;

            source.addEventListener('heartbeat', evt => {
                try {
                    const data = JSON.parse(evt.data || '{}');
                    applyHeartbeatData(host, data);
                    delete heartbeatStreamErrorShown[host];
                    renderHosts();
                    loadActivityFeed();
                } catch (err) {
                    logger.warn('Heartbeat SSE parse failed', err);
                }
            });

            source.addEventListener('error', evt => {
                let errorPayload = null;
                try {
                    errorPayload = JSON.parse(evt?.data || '');
                } catch (_) {
                    // Browser connection errors do not always include a payload.
                }
                if (isHeartbeatConfigurationError(errorPayload?.code)) {
                    stopHeartbeatStream(host);
                    showToast(formatHeartbeatError(host, errorPayload), 'error');
                    return;
                }
                if (source.readyState === EventSourceCtor.CLOSED) {
                    stopHeartbeatStream(host);
                }
                if (!heartbeatStreamErrorShown[host]) {
                    heartbeatStreamErrorShown[host] = true;
                    showToast(formatHeartbeatError(host, errorPayload), 'error');
                }
            });
        }

        function applyHeartbeatData(host, data) {
            const override = localModeOverrides[host];
            const reported = data?.heartbeat?.status?.localModeEnabled;
            if (typeof override !== 'boolean') {
                hostState[host] = data;
                return;
            }
            if (reported === override) {
                delete localModeOverrides[host];
                hostState[host] = data;
                return;
            }
            const heartbeat = data?.heartbeat && typeof data.heartbeat === 'object'
                ? data.heartbeat
                : {};
            const status = heartbeat.status && typeof heartbeat.status === 'object'
                ? heartbeat.status
                : {};
            hostState[host] = {
                ...data,
                heartbeat: {
                    ...heartbeat,
                    status: {
                        ...status,
                        localModeEnabled: override,
                    },
                },
            };
        }

        async function loadInventory(options = {}) {
            try {
                const res = await fetchImpl('/ops/api/hosts', options);
                if (res.status === 403) {
                    showOpsWarning();
                    if (!options.skipAuthPrompt) showToast('Access denied: /ops blocked by Lab Manager access policy', 'error');
                    return false;
                }
                if (res.status === 401) {
                    if (!options.skipAuthPrompt) {
                        showToast('Lab Manager session required to load Lab Station hosts', 'error');
                    }
                    return false;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                const hosts = Array.isArray(data.hosts) ? data.hosts : [];
                Object.keys(hostMetadata).forEach(key => delete hostMetadata[key]);
                hosts.forEach(host => {
                    if (host && host.name) {
                        hostMetadata[host.name] = host;
                    }
                });

                const nextHostNames = hosts.map(host => host.name).filter(Boolean);
                const nextSet = new Set(nextHostNames);
                state.getHostNames()
                    .filter(name => !nextSet.has(name))
                    .forEach(stopHeartbeatStream);
                state.setHostNames(nextHostNames);
                state.getHostNames()
                    .filter(name => {
                        const meta = hostMetadata[name] || {};
                        return meta.winrmConfigured !== true || meta.winrmTrustStatus !== 'ready';
                    })
                    .forEach(stopHeartbeatStream);
                renderHosts();
                const candidates = Array.isArray(data.guacamoleUnmatched)
                    ? data.guacamoleUnmatched
                    : [];
                setGuacamoleCandidates(candidates);
                candidates.forEach(rememberGuacamoleCandidate);
                renderGuacamoleCandidates(groupGuacamoleCandidates(candidates));
                state.getHostNames().forEach(startHeartbeatStream);
                updateOpsHint(data);
                return true;
            } catch (err) {
                logger.warn('Unable to load ops host inventory', err);
                updateOpsHint(null);
                if (!options.skipAuthPrompt) showToast(`Hosts refresh failed: ${err.message}`, 'error');
                return false;
            }
        }

        async function refreshAllHosts() {
            showLoadingToast('Refreshing Lab Station hosts…');
            const loaded = await loadInventory();
            if (!loaded) return false;
            const EventSourceCtor = getEventSource();
            const hostNames = state.getHostNames();
            if (EventSourceCtor) {
                const streamableHosts = hostNames.filter(host =>
                    hostMetadata[host]?.winrmConfigured === true
                    && hostMetadata[host]?.winrmTrustStatus === 'ready'
                );
                streamableHosts.forEach(startHeartbeatStream);
                showToast(
                    streamableHosts.length
                        ? 'Heartbeat streaming started for configured hosts'
                        : 'Heartbeat streaming unavailable: configure WinRM credentials and TLS trust',
                    streamableHosts.length ? 'success' : 'error',
                );
                return true;
            }
            hostNames.forEach(pollHeartbeat);
            if (!hostNames.length) showToast('Hosts inventory refreshed; no hosts configured', 'success');
            return true;
        }

        async function pollHeartbeat(host, { silent = false } = {}) {
            if (!silent) showLoadingToast(`Checking heartbeat for ${host}…`);
            try {
                const res = await fetchImpl('/ops/api/heartbeat/poll', {
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
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    showToast(formatHeartbeatError(host, data), 'error');
                    return;
                }
                applyHeartbeatData(host, data);
                renderHosts();
                loadActivityFeed();
                if (!silent) showToast(`Heartbeat ${host} ok`, 'success');
                return data;
            } catch (err) {
                logger.error(err);
                showToast(`Heartbeat failed for ${host}: ${err.message}`, 'error');
            }
        }

        function updateLocalModeState(host, enabled) {
            if (!host) return;
            const localModeEnabled = enabled === true;
            localModeOverrides[host] = localModeEnabled;
            const current = hostState[host] || {};
            const heartbeat = current.heartbeat || {};
            const status = heartbeat.status || {};
            hostState[host] = {
                ...current,
                heartbeat: {
                    ...heartbeat,
                    status: {
                        ...status,
                        localModeEnabled,
                    },
                },
            };
            renderHosts();
        }

        return Object.freeze({
            loadInventory,
            startHeartbeatStream,
            stopHeartbeatStream,
            refreshAllHosts,
            pollHeartbeat,
            updateLocalModeState,
        });
    }

    root.LabManagerHosts = Object.freeze({ createController });
})(window);
