(function (global) {
    'use strict';

    function createController({ documentImpl = global.document } = {}) {
        const modes = {
            images: 'link',
            docs: 'link',
        };
        const $ = id => documentImpl?.getElementById?.(id);

        function resolveKind(kind) {
            return kind === 'docs' ? 'docs' : 'images';
        }

        function setMode(kind, mode) {
            const resolvedKind = resolveKind(kind);
            const isImages = resolvedKind === 'images';
            const resolvedMode = mode === 'upload' ? 'upload' : 'link';
            const control = $(isImages ? 'labImageMode' : 'labDocMode');
            const linkInput = $(isImages ? 'labImageUrls' : 'labDocUrls');
            const chooseBtn = $(isImages ? 'labImagesChooseBtn' : 'labDocsChooseBtn');

            modes[resolvedKind] = resolvedMode;
            control?.querySelectorAll?.('button')?.forEach(button => {
                button.classList.toggle('active', button.dataset.mode === resolvedMode);
            });
            if (linkInput) linkInput.hidden = resolvedMode !== 'link';
            if (chooseBtn) chooseBtn.hidden = resolvedMode !== 'upload';
        }

        function bindModeButtons(kind, controlId) {
            $(controlId)?.querySelectorAll?.('button')?.forEach(button => {
                button.addEventListener('click', () => setMode(kind, button.dataset.mode));
            });
        }

        function bind() {
            setMode('images', 'link');
            setMode('docs', 'link');
            bindModeButtons('images', 'labImageMode');
            bindModeButtons('docs', 'labDocMode');
        }

        function getState() {
            return {
                imageMode: modes.images,
                docMode: modes.docs,
            };
        }

        function reset() {
            setMode('images', 'link');
            setMode('docs', 'link');
        }

        return { bind, getState, reset, setMode };
    }

    global.LabPublisherMediaFeature = { createController };
})(window);
