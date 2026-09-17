(function (root) {
    'use strict';

    const streamErrorMessages = Object.freeze({
        WINRM_CREDENTIALS_REQUIRED: 'WinRM credentials are required',
        WINRM_TRUST_REQUIRED: 'WinRM certificate trust is required',
        WINRM_TRUST_INVALID: 'WinRM certificate trust is invalid',
        WINRM_CERTIFICATE_INVALID: 'WinRM certificate trust is invalid',
        WINRM_CERTIFICATE_HOST_MISMATCH: 'WinRM certificate does not match the host address',
        WINRM_CERTIFICATE_EXPIRED: 'WinRM certificate is expired',
        WINRM_CERTIFICATE_NOT_YET_VALID: 'WinRM certificate is not yet valid',
        WINRM_TLS_FAILED: 'WinRM TLS validation failed',
        WINRM_TRUST_STORAGE_UNAVAILABLE: 'WinRM certificate trust storage is unavailable',
        WINRM_UNREACHABLE: 'Lab Station is unreachable',
        INTERNAL_ERROR: 'temporary Ops Worker error',
    });
    const configurationErrorCodes = new Set([
        'WINRM_CREDENTIALS_REQUIRED',
        'WINRM_TRUST_REQUIRED',
        'WINRM_TRUST_INVALID',
        'WINRM_CERTIFICATE_INVALID',
        'WINRM_CERTIFICATE_HOST_MISMATCH',
        'WINRM_CERTIFICATE_EXPIRED',
        'WINRM_CERTIFICATE_NOT_YET_VALID',
        'WINRM_TLS_FAILED',
        'WINRM_TRUST_STORAGE_UNAVAILABLE',
    ]);

    function normalizeCode(value) {
        return String(value || '').trim().toUpperCase();
    }

    function isConfigurationError(value) {
        return configurationErrorCodes.has(normalizeCode(value));
    }

    function formatHeartbeatError(host, payload) {
        const code = normalizeCode(payload?.code);
        let message = streamErrorMessages[code] || 'connection error';
        if (code === 'WINRM_UNREACHABLE') {
            const address = String(payload?.address || '').trim();
            const port = String(payload?.port || '').trim();
            const endpoint = address && port ? `${address}:${port}` : address;
            message = endpoint
                ? `Lab Station is unreachable at ${endpoint} (it may be powered off or WinRM may be unavailable)`
                : 'Lab Station is unreachable (it may be powered off or WinRM may be unavailable)';
        }
        const requestId = String(payload?.requestId || '').trim();
        const safeRequestId = /^[A-Za-z0-9._:-]{1,128}$/.test(requestId) ? requestId : '';
        const requestSuffix = code === 'INTERNAL_ERROR' && safeRequestId
            ? ` (request ID ${safeRequestId})`
            : '';
        return `Heartbeat unavailable for ${host}: ${message}${requestSuffix}`;
    }

    root.LabManagerHeartbeatErrors = Object.freeze({
        isConfigurationError,
        formatHeartbeatError,
    });
})(window);
