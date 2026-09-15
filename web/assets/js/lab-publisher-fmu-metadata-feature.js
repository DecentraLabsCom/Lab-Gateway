(function (global) {
    'use strict';

    function createController({
        documentImpl = global.document,
        fetchFmuMetadata = async () => ({}),
        fetchImpl = global.fetch?.bind(global),
        renderModelVariables = () => ({ hidden: true, html: '' }),
        escapeHtml = value => String(value ?? ''),
    } = {}) {
        const state = { modelVariables: [] };
        let activeRequest = null;
        const $ = id => documentImpl?.getElementById?.(id);

        function render() {
            const wrap = $('labModelVariablesWrap');
            const body = $('labModelVariables');
            if (!wrap || !body) return;
            const rendered = renderModelVariables({
                modelVariables: state.modelVariables,
                escapeHtml,
            });
            wrap.hidden = rendered.hidden;
            body.innerHTML = rendered.html;
        }

        function clearFields(keepStatus = false) {
            $('labFmiVersion') && ($('labFmiVersion').value = '');
            $('labSimulationType') && ($('labSimulationType').value = '');
            $('labDefaultStartTime') && ($('labDefaultStartTime').value = '');
            $('labDefaultStopTime') && ($('labDefaultStopTime').value = '');
            $('labDefaultStepSize') && ($('labDefaultStepSize').value = '');
            state.modelVariables = [];
            render();
            if (!keepStatus && $('labFmuDescribeStatus')) {
                $('labFmuDescribeStatus').textContent = 'Set Access URI and FMU File Name to enable auto-detect.';
            }
        }

        function reset(keepStatus = false) {
            activeRequest?.abort();
            activeRequest = null;
            clearFields(keepStatus);
        }

        function hydrate(metadata = {}) {
            if ('fmiVersion' in metadata && $('labFmiVersion')) $('labFmiVersion').value = metadata.fmiVersion || '';
            if ('simulationType' in metadata && $('labSimulationType')) $('labSimulationType').value = metadata.simulationType || '';
            if ('defaultStartTime' in metadata && $('labDefaultStartTime')) $('labDefaultStartTime').value = metadata.defaultStartTime ?? '';
            if ('defaultStopTime' in metadata && $('labDefaultStopTime')) $('labDefaultStopTime').value = metadata.defaultStopTime ?? '';
            if ('defaultStepSize' in metadata && $('labDefaultStepSize')) $('labDefaultStepSize').value = metadata.defaultStepSize ?? '';
            if (metadata.modelName && $('labName')) {
                $('labName').value = metadata.modelName;
            }
            if ('modelVariables' in metadata) {
                state.modelVariables = Array.isArray(metadata.modelVariables) ? metadata.modelVariables : [];
                render();
            }
        }

        async function autoDetect() {
            const fmuFileName = $('labFmuFileName')?.value.trim() || '';
            const gatewayUrl = $('labAccessURI')?.value.trim() || '';
            const status = $('labFmuDescribeStatus');
            if (!fmuFileName) {
                if (status) status.textContent = 'Set FMU File Name first.';
                return;
            }
            if (!gatewayUrl) {
                if (status) status.textContent = 'Set Access URI first.';
                return;
            }
            activeRequest?.abort();
            const request = new AbortController();
            activeRequest = request;
            clearFields(true);
            if (status) status.textContent = 'Loading FMU metadata...';
            try {
                const metadata = await fetchFmuMetadata({
                    fmuFileName,
                    gatewayUrl,
                    signal: request.signal,
                    fetchImpl,
                });
                if (activeRequest !== request) return;
                hydrate(metadata);
                if (status) status.textContent = 'FMU metadata loaded successfully.';
            } catch (err) {
                if (err.name === 'AbortError') return;
                if (status) status.textContent = `Auto-detect failed: ${err.message}`;
            } finally {
                if (activeRequest === request) activeRequest = null;
            }
        }

        function getModelVariables() {
            return state.modelVariables;
        }

        return {
            autoDetect,
            getModelVariables,
            hydrate,
            render,
            reset,
        };
    }

    global.LabPublisherFmuMetadataFeature = { createController };
})(window);
