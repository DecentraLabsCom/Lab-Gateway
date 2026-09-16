(function (global) {
    'use strict';

    function createController({
        documentImpl = global.document,
        fetchImpl = global.fetch?.bind(global),
        digestImpl = global.crypto?.subtle?.digest?.bind(global.crypto.subtle),
        guessVersionFromUrl = () => '',
        now = () => new Date(),
        showToast = () => {},
    } = {}) {
        let bound = false;
        let activeRequest = null;
        const $ = id => documentImpl?.getElementById?.(id);

        function setValue(id, value) {
            const input = $(id);
            if (input) input.value = value ?? '';
        }

        function getState() {
            return {
                url: $('labTermsUrl')?.value || '',
                version: $('labTermsVersion')?.value || '',
                effectiveDate: $('labTermsEffectiveDate')?.value || '',
                sha256: $('labTermsSha256')?.value || '',
            };
        }

        function hydrate(terms = {}) {
            setValue('labTermsUrl', terms.url || '');
            setValue('labTermsVersion', terms.version || '');
            setValue('labTermsEffectiveDate', terms.effectiveDate || '');
            setValue('labTermsSha256', terms.sha256 || '');
        }

        function reset() {
            activeRequest?.abort();
            activeRequest = null;
            hydrate();
            const status = $('labTermsStatus');
            if (status) status.textContent = '';
        }

        async function sha256Hex(buffer) {
            if (!digestImpl) return '';
            const hashBuffer = await digestImpl('SHA-256', buffer);
            return Array.from(new Uint8Array(hashBuffer))
                .map(byte => byte.toString(16).padStart(2, '0'))
                .join('');
        }

        async function fetchMetadata() {
            const url = $('labTermsUrl')?.value.trim() || '';
            activeRequest?.abort();
            setValue('labTermsVersion', '');
            setValue('labTermsEffectiveDate', '');
            setValue('labTermsSha256', '');
            const status = $('labTermsStatus');
            if (status) status.textContent = '';
            if (!url) return;
            if (!/^https?:\/\//i.test(url)) {
                if (status) status.textContent = 'Terms link must be an absolute HTTP(S) URL.';
                showToast('Terms link must be an absolute HTTP(S) URL.', 'error');
                return;
            }
            if (!fetchImpl) {
                if (status) status.textContent = 'Unable to auto-fill version/date/hash for this link.';
                showToast('Unable to auto-fill Terms metadata.', 'error');
                return;
            }

            const request = new AbortController();
            activeRequest = request;
            if (status) status.textContent = 'Fetching metadata...';
            try {
                const response = await fetchImpl(url, { signal: request.signal });
                if (!response.ok) throw new Error('Unable to download the Terms of Use document.');
                const buffer = await response.arrayBuffer();
                const shaValue = await sha256Hex(buffer);
                setValue('labTermsVersion', guessVersionFromUrl(url));
                setValue('labTermsEffectiveDate', now().toISOString().split('T')[0]);
                setValue('labTermsSha256', shaValue);
                if (status) {
                    status.textContent = shaValue
                        ? 'Terms metadata auto-filled.'
                        : 'Terms date auto-filled; SHA-256 unavailable in this browser context.';
                }
                showToast('Terms metadata loaded', 'success');
            } catch (err) {
                if (err.name === 'AbortError') return;
                const message = 'Unable to auto-fill version/date/hash for this link.';
                if (status) status.textContent = message;
                showToast(message, 'error');
            } finally {
                if (activeRequest === request) activeRequest = null;
            }
        }

        function bind() {
            if (bound) return;
            bound = true;
            $('labTermsUrl')?.addEventListener('blur', fetchMetadata);
        }

        return {
            bind,
            fetchMetadata,
            getState,
            hydrate,
            reset,
        };
    }

    global.LabPublisherTermsFeature = { createController };
})(window);
