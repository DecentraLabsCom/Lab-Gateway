(function (global) {
    'use strict';

    function createController({
        documentImpl = global.document,
        splitCsv = value => String(value || '').split(',').map(item => item.trim()).filter(Boolean),
    } = {}) {
        const $ = id => documentImpl?.getElementById?.(id);

        function setValue(id, value) {
            const input = $(id);
            if (input) input.value = value ?? '';
        }

        function asList(value) {
            return Array.isArray(value) ? value : splitCsv(value);
        }

        function getState({
            imageMode = 'link',
            docMode = 'link',
            uploadedImages = [],
            uploadedDocs = [],
        } = {}) {
            return {
                name: $('labName')?.value?.trim() || '',
                description: $('labDescription')?.value?.trim() || '',
                keywords: splitCsv($('labKeywords')?.value || ''),
                demoEnabled: $('labDemoEnabled')?.checked === true,
                imageUrls: imageMode === 'link' ? splitCsv($('labImageUrls')?.value || '') : uploadedImages,
                docs: docMode === 'link' ? splitCsv($('labDocUrls')?.value || '') : uploadedDocs,
            };
        }

        function hydrate(metadata = {}) {
            if ('name' in metadata) setValue('labName', metadata.name || '');
            if ('description' in metadata) setValue('labDescription', metadata.description || '');
            if ('keywords' in metadata) setValue('labKeywords', asList(metadata.keywords).join(', '));
            if ('demoEnabled' in metadata) {
                const input = $('labDemoEnabled');
                if (input) input.checked = metadata.demoEnabled === true;
            }
            if ('imageUrls' in metadata) setValue('labImageUrls', asList(metadata.imageUrls).join(', '));
            if ('docUrls' in metadata) setValue('labDocUrls', asList(metadata.docUrls).join(', '));
        }

        function reset() {
            hydrate({
                name: '',
                description: '',
                keywords: [],
                demoEnabled: false,
                imageUrls: [],
                docUrls: [],
            });
        }

        return { getState, hydrate, reset };
    }

    global.LabPublisherMetadataFeature = { createController };
})(window);
