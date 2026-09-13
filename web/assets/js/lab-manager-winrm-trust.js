(function (root) {
    'use strict';

    function createController({
        fetchImpl,
        formDataCtor = root.FormData,
        formatErrorMessage = (body, status) => body?.error || `HTTP ${status}`,
        callbacks = {},
    } = {}) {
        if (typeof fetchImpl !== 'function') {
            throw new Error('LabManagerWinrmTrust requires fetchImpl');
        }
        if (typeof formDataCtor !== 'function') {
            throw new Error('LabManagerWinrmTrust requires formDataCtor');
        }

        const {
            onLoaded = () => {},
            onLoadError = () => {},
            onPreview = () => {},
            onReady = () => {},
            onPreviewError = () => {},
            onPreviewFinished = () => {},
            onSaved = () => {},
            onSaveError = () => {},
            onSaveFinished = () => {},
            onRemoved = () => {},
            onRemoveError = () => {},
            onRemoveFinished = () => {},
        } = callbacks;

        async function load(host) {
            try {
                const res = await fetchImpl(`/ops/api/hosts/${encodeURIComponent(host)}/winrm-trust`);
                const body = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(formatErrorMessage(body, res.status));
                if (host) onLoaded(host, body.trust || body);
                return true;
            } catch (err) {
                onLoadError(host, err);
                return false;
            }
        }

        async function preview(host, file) {
            try {
                const form = new formDataCtor();
                form.append('certificate', file, file.name);
                const res = await fetchImpl(
                    `/ops/api/hosts/${encodeURIComponent(host)}/winrm-trust/preview`,
                    { method: 'POST', body: form },
                );
                const body = await res.json().catch(() => ({}));
                if (body.preview) onPreview(body.preview);
                if (!res.ok) throw new Error(formatErrorMessage(body, res.status));
                const readyPreview = { ...body.preview, valid: true };
                onReady(readyPreview);
                return true;
            } catch (err) {
                onPreviewError(err);
                return false;
            } finally {
                onPreviewFinished();
            }
        }

        async function save(host, file, previewData) {
            try {
                const form = new formDataCtor();
                form.append('certificate', file, file.name);
                form.append('fingerprintSha256', previewData.fingerprintSha256);
                form.append('trustRef', previewData.trustRef || '');
                const res = await fetchImpl(
                    `/ops/api/hosts/${encodeURIComponent(host)}/winrm-trust`,
                    { method: 'PUT', body: form },
                );
                const body = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(formatErrorMessage(body, res.status));
                await onSaved(host, body);
                return true;
            } catch (err) {
                onSaveError(err);
                return false;
            } finally {
                onSaveFinished();
            }
        }

        async function remove(host) {
            try {
                const res = await fetchImpl(
                    `/ops/api/hosts/${encodeURIComponent(host)}/winrm-trust`,
                    { method: 'DELETE' },
                );
                const body = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(formatErrorMessage(body, res.status));
                await onRemoved(host, body);
                return true;
            } catch (err) {
                onRemoveError(host, err);
                return false;
            } finally {
                onRemoveFinished();
            }
        }

        return Object.freeze({ load, preview, save, remove });
    }

    root.LabManagerWinrmTrust = Object.freeze({ createController });
})(window);
