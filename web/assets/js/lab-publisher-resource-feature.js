(function (global) {
    'use strict';

    function createController({
        documentImpl = global.document,
        windowImpl = global,
        getStatus = () => null,
        getFmus = () => [],
        getGuacamole = () => [],
        uniqueGuacamole = connections => connections,
        formatConnectionUsers = () => '',
        resolveConnectionAccessKey = connection => connection?.id || '',
        normalizeMaxConcurrentUsers = value => value,
        resetFmuDescribeFields = () => {},
        autoDetectFmuMetadata = async () => {},
        urlCtor = typeof URL === 'function' ? URL : global.URL,
    } = {}) {
        let bound = false;
        const $ = id => documentImpl?.getElementById?.(id);

        function recommendedRemoteAccessURI() {
            return getStatus()?.recommendedRemoteAccessURI || `${windowImpl.location.origin}/guacamole`;
        }

        function recommendedFmuAccessURI() {
            return getStatus()?.recommendedFmuAccessURI || `${windowImpl.location.origin}/fmu`;
        }

        function accessURIHasSegment(value, segment) {
            const text = String(value || '').trim();
            if (!text) return false;
            const normalizedSegment = String(segment || '').trim().toLowerCase();
            try {
                const url = new urlCtor(text, windowImpl.location.origin);
                return url.pathname
                    .split('/')
                    .map(part => part.toLowerCase())
                    .includes(normalizedSegment);
            } catch {
                return text.toLowerCase().includes(`/${normalizedSegment}`);
            }
        }

        function syncSetupMode() {
            const quick = $('labSetupMode')?.value === 'quick';
            const fullMetadataPanel = $('fullMetadataPanel');
            const quickMetadataField = $('quickMetadataField');
            if (fullMetadataPanel) fullMetadataPanel.hidden = quick;
            if (quickMetadataField) quickMetadataField.hidden = !quick;
        }

        function setGroupHidden(selector, hidden) {
            documentImpl?.querySelectorAll?.(selector)?.forEach(element => {
                element.hidden = hidden;
            });
        }

        function syncTypeFields() {
            const isFmu = $('labResourceType')?.value === '1';
            const accessKeyInput = $('labAccessKey');
            const accessURIInput = $('labAccessURI');
            const fmuFileNameInput = $('labFmuFileName');
            const maxConcurrentUsersInput = $('labMaxConcurrentUsers');
            if (!accessKeyInput || !accessURIInput || !fmuFileNameInput || !maxConcurrentUsersInput) return;

            syncSetupMode();
            const fmuConfigTitle = $('fmuConfigTitle');
            const fmuConfigPanel = $('fmuConfigPanel');
            if (fmuConfigTitle) fmuConfigTitle.hidden = !isFmu;
            if (fmuConfigPanel) fmuConfigPanel.hidden = !isFmu;
            setGroupHidden('.lab-access-key-field', isFmu);
            setGroupHidden('.lab-fmu-file-field', !isFmu);
            setGroupHidden('.lab-max-concurrent-users-field', !isFmu);
            if (isFmu && !fmuFileNameInput.value.trim() && accessKeyInput.value.trim().toLowerCase().endsWith('.fmu')) {
                fmuFileNameInput.value = accessKeyInput.value.trim();
            }
            if (isFmu && fmuFileNameInput.value.trim()) {
                accessKeyInput.value = fmuFileNameInput.value.trim();
            }
            const currentAccessURI = accessURIInput.value.trim();
            if (isFmu) {
                if (!currentAccessURI || accessURIHasSegment(currentAccessURI, 'guacamole')) {
                    accessURIInput.value = recommendedFmuAccessURI();
                }
                maxConcurrentUsersInput.value = String(normalizeMaxConcurrentUsers(maxConcurrentUsersInput.value, true));
            } else {
                if (accessKeyInput.value.trim() && !/^guac:id:[1-9][0-9]*$/.test(accessKeyInput.value.trim())) {
                    accessKeyInput.value = '';
                }
                fmuFileNameInput.value = '';
                maxConcurrentUsersInput.value = '1';
                resetFmuDescribeFields(false);
                if (!currentAccessURI || !accessURIHasSegment(currentAccessURI, 'guacamole')) {
                    accessURIInput.value = recommendedRemoteAccessURI();
                }
            }
            accessKeyInput.readOnly = true;
            accessURIInput.readOnly = true;
        }

        async function applySelectedResource() {
            const type = $('labResourceType')?.value;
            const index = $('labDetectedResource')?.value;
            const preview = $('labResourcePreview');
            if (!preview || index === undefined) return;
            if (index === '') {
                preview.textContent = 'No resource selected.';
                resetFmuDescribeFields(false);
                return;
            }
            if (type === '1') {
                const fmu = getFmus()[Number(index)];
                const fmuFileName = fmu?.fileName || '';
                $('labAccessURI').value = recommendedFmuAccessURI();
                $('labAccessKey').value = fmuFileName;
                $('labFmuFileName').value = fmuFileName;
                $('labName').value = fmuFileName ? fmuFileName.replace(/\.fmu$/i, '') : '';
                preview.textContent = `FMU: ${fmu?.relativePath || fmuFileName || 'selected'}`;
                $('labMaxConcurrentUsers').value = Math.max(2, Number($('labMaxConcurrentUsers').value) || 2);
                syncTypeFields();
                if (fmuFileName) {
                    await autoDetectFmuMetadata();
                } else {
                    resetFmuDescribeFields(false);
                }
                return;
            }

            const conn = uniqueGuacamole(getGuacamole())[Number(index)];
            $('labAccessURI').value = recommendedRemoteAccessURI();
            $('labAccessKey').value = resolveConnectionAccessKey(conn);
            $('labName').value = conn?.name || '';
            const selector = resolveConnectionAccessKey(conn);
            preview.textContent = `Guacamole: ${conn?.name || 'Connection'} (${conn?.hostname || 'no host'}) - connection ${selector || 'n/a'}`;
            $('labMaxConcurrentUsers').value = 1;
            resetFmuDescribeFields(false);
            syncTypeFields();
        }

        function renderOptions() {
            const select = $('labDetectedResource');
            if (!select) return;
            const type = $('labResourceType')?.value;
            select.innerHTML = '<option value="">Manual entry</option>';
            const resources = type === '1' ? getFmus() : uniqueGuacamole(getGuacamole());
            resources.forEach((resource, index) => {
                const option = documentImpl.createElement('option');
                option.value = String(index);
                option.textContent = type === '1'
                    ? `${resource.fileName} (${resource.relativePath || 'fmu-data'})`
                    : `${resource.name || 'Connection'} #${resource.id} ${resource.hostname ? '- ' + resource.hostname : ''}${formatConnectionUsers(resource)}`;
                select.appendChild(option);
            });
            void applySelectedResource();
        }

        function bind() {
            if (bound) return;
            bound = true;
            const resourceType = $('labResourceType');
            const resourceSelect = $('labDetectedResource');
            const setupMode = $('labSetupMode');
            const fmuFileName = $('labFmuFileName');
            resourceType?.addEventListener('change', () => {
                renderOptions();
                syncTypeFields();
            });
            resourceSelect?.addEventListener('change', () => {
                void applySelectedResource();
            });
            setupMode?.addEventListener('change', syncSetupMode);
            fmuFileName?.addEventListener('input', () => {
                if (resourceType?.value === '1') $('labAccessKey').value = fmuFileName.value.trim();
                resetFmuDescribeFields(false);
            });
        }

        return Object.freeze({
            applySelected: applySelectedResource,
            bind,
            renderOptions,
            syncSetupMode,
            syncTypeFields,
        });
    }

    global.LabPublisherResourceFeature = Object.freeze({ createController });
}(window));
