(function (global) {
    'use strict';

    const DESCRIBE_TOKEN_PATH = '/lab-admin/fmu/provider-describe-token';
    const DESCRIBE_PATH = '/api/v1/simulations/describe';

    function asArray(value) {
        return Array.isArray(value) ? value : [];
    }

    function uniqueGuacamole(connections) {
        const seen = new Set();
        return asArray(connections).filter(connection => {
            const key = String(connection?.id);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }

    function collectDetectedResources({ hosts = {}, fmuInventory = [] } = {}) {
        const hostConnections = asArray(hosts.hosts).flatMap(host => asArray(host?.guacamole?.connections));
        return {
            fmus: asArray(fmuInventory),
            guacamole: uniqueGuacamole([
                ...asArray(hosts.guacamoleUnmatched),
                ...hostConnections,
            ]),
        };
    }

    function buildFmuDescribeUrl(gatewayUrl, fmuFileName) {
        return `${String(gatewayUrl || '').replace(/\/+$/, '')}${DESCRIBE_PATH}?fmuFileName=${encodeURIComponent(fmuFileName)}`;
    }

    function resolveFetch(fetchImpl) {
        if (typeof fetchImpl === 'function') return fetchImpl;
        if (typeof global.fetch === 'function') return global.fetch.bind(global);
        if (typeof fetch === 'function') return fetch;
        throw new Error('Fetch API unavailable');
    }

    async function readJson(response) {
        if (typeof response?.json !== 'function') return {};
        return response.json().catch(() => ({}));
    }

    async function fetchFmuMetadata({ fmuFileName, gatewayUrl, signal, fetchImpl } = {}) {
        const request = resolveFetch(fetchImpl);
        const tokenResponse = await request(DESCRIBE_TOKEN_PATH, {
            method: 'POST',
            credentials: 'include',
            signal,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fmuFileName }),
        });
        const tokenBody = await readJson(tokenResponse);
        if (!tokenResponse.ok || !tokenBody.token) {
            throw new Error(tokenBody.error || `Describe token request returned HTTP ${tokenResponse.status}`);
        }

        const describeResponse = await request(buildFmuDescribeUrl(gatewayUrl, fmuFileName), {
            signal,
            headers: { Authorization: `Bearer ${tokenBody.token}` },
        });
        const metadata = await readJson(describeResponse);
        if (!describeResponse.ok) {
            throw new Error(metadata.error || `Gateway returned HTTP ${describeResponse.status}`);
        }
        return metadata;
    }

    global.LabPublisherResources = Object.freeze({
        collectDetectedResources,
        uniqueGuacamole,
        buildFmuDescribeUrl,
        fetchFmuMetadata,
    });
}(window));
