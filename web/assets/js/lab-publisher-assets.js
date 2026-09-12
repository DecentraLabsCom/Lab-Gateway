(function (global) {
    'use strict';

    function buildAssetEntries(uploadedImages = [], uploadedDocs = []) {
        return [
            ...uploadedImages.map(url => ({ kind: 'images', label: 'Image', url })),
            ...uploadedDocs.map(url => ({ kind: 'docs', label: 'Doc', url })),
        ];
    }

    function renderAssetList({ uploadedImages = [], uploadedDocs = [], escapeHtml, escapeAttr } = {}) {
        const entries = buildAssetEntries(uploadedImages, uploadedDocs);
        if (!entries.length) return '';

        return entries.map(entry => `
                <div class="asset-row">
                    <span>${escapeHtml(entry.label)}</span>
                    <a href="${escapeAttr(entry.url)}" target="_blank" rel="noopener">${escapeHtml(entry.url)}</a>
                    <button class="mini-btn danger asset-delete-btn" type="button" data-kind="${escapeAttr(entry.kind)}" data-url="${escapeAttr(entry.url)}" title="Delete ${escapeAttr(entry.label)}" aria-label="Delete ${escapeAttr(entry.label)}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `).join('');
    }

    function resolveFormData(FormDataImpl) {
        if (typeof FormDataImpl === 'function') return FormDataImpl;
        if (typeof global.FormData === 'function') return global.FormData;
        if (typeof FormData === 'function') return FormData;
        throw new Error('FormData API unavailable');
    }

    function buildAssetUploadRequest({ contentId, kind, file, FormDataImpl } = {}) {
        const form = new (resolveFormData(FormDataImpl))();
        form.append('contentId', contentId);
        form.append('kind', kind);
        form.append('file', file);
        return {
            url: '/lab-admin/assets',
            options: {
                method: 'POST',
                body: form,
            },
        };
    }

    function buildAssetDeleteRequest(path) {
        return {
            url: '/lab-admin/assets',
            options: {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path }),
            },
        };
    }

    global.LabPublisherAssets = Object.freeze({
        buildAssetEntries,
        renderAssetList,
        buildAssetUploadRequest,
        buildAssetDeleteRequest,
    });
}(window));
