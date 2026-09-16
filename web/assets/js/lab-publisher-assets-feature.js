(function (global) {
    'use strict';

    function createController({
        assetListElement,
        inputs = {},
        ensureContentId,
        fetchJson,
        buildAssetUploadRequest,
        buildAssetDeleteRequest,
        renderAssetList,
        escapeHtml,
        escapeAttr,
        callbacks = {},
    } = {}) {
        let uploadedImages = [];
        let uploadedDocs = [];
        let bound = false;
        const setStatus = callbacks.setStatus || (() => {});
        const showToast = callbacks.showToast || (() => {});

        function getUploadedImages() {
            return [...uploadedImages];
        }

        function getUploadedDocs() {
            return [...uploadedDocs];
        }

        function render() {
            if (!assetListElement) return;
            assetListElement.innerHTML = renderAssetList({
                uploadedImages,
                uploadedDocs,
                escapeHtml,
                escapeAttr,
            });
        }

        function setUploadedAssets({ images = [], docs = [] } = {}) {
            uploadedImages = Array.isArray(images) ? [...images] : [];
            uploadedDocs = Array.isArray(docs) ? [...docs] : [];
            render();
        }

        function clearUploadedAssets() {
            uploadedImages = [];
            uploadedDocs = [];
            render();
        }

        async function upload(files, kind) {
            const list = Array.from(files || []);
            if (!list.length) return;
            const contentId = ensureContentId();
            try {
                for (const file of list) {
                    const request = buildAssetUploadRequest({ contentId, kind, file });
                    const result = await fetchJson(request.url, request.options);
                    if (kind === 'images') uploadedImages.push(result.url);
                    else uploadedDocs.push(result.url);
                }
                const label = kind === 'images' ? 'image' : 'document';
                const count = list.length;
                showToast(`Uploaded ${count} ${label}${count === 1 ? '' : 's'}.`, 'success');
            } catch (err) {
                const message = err.message || 'Upload failed';
                setStatus(message, true);
                showToast(message, 'error');
            } finally {
                const input = inputs[kind];
                if (input) input.value = '';
                render();
            }
        }

        async function handleAssetListClick(event) {
            const button = event?.target?.closest?.('button[data-url][data-kind]');
            if (!button) return;
            const url = button.dataset.url || '';
            const kind = button.dataset.kind || '';
            button.disabled = true;
            try {
                const request = buildAssetDeleteRequest(url);
                await fetchJson(request.url, request.options);
                if (kind === 'images') uploadedImages = uploadedImages.filter(item => item !== url);
                else uploadedDocs = uploadedDocs.filter(item => item !== url);
                setStatus('Asset deleted.', false);
                showToast('Asset deleted.', 'success');
            } catch (err) {
                const message = err.message || 'Delete failed';
                setStatus(message, true);
                showToast(message, 'error');
            } finally {
                render();
            }
        }

        function bind() {
            if (bound || !assetListElement) return;
            bound = true;
            assetListElement.addEventListener('click', handleAssetListClick);
        }

        return Object.freeze({
            bind,
            clearUploadedAssets,
            getUploadedDocs,
            getUploadedImages,
            render,
            setUploadedAssets,
            upload,
        });
    }

    global.LabPublisherAssetsFeature = Object.freeze({ createController });
}(window));
