(function () {
    const publisherValues = window.LabPublisherValues;
    if (!publisherValues) {
        throw new Error('LabPublisherValues must load before lab-publisher.js');
    }
    const publisherRenderers = window.LabPublisherRenderers;
    if (!publisherRenderers) {
        throw new Error('LabPublisherRenderers must load before lab-publisher.js');
    }
    const publisherResources = window.LabPublisherResources;
    if (!publisherResources) {
        throw new Error('LabPublisherResources must load before lab-publisher.js');
    }
    const publisherAssets = window.LabPublisherAssets;
    if (!publisherAssets) {
        throw new Error('LabPublisherAssets must load before lab-publisher.js');
    }
    const publisherMetadata = window.LabPublisherMetadata;
    if (!publisherMetadata) {
        throw new Error('LabPublisherMetadata must load before lab-publisher.js');
    }
    const publisherLabActions = window.LabPublisherLabActions;
    if (!publisherLabActions) {
        throw new Error('LabPublisherLabActions must load before lab-publisher.js');
    }
    const publisherAssetsFeature = window.LabPublisherAssetsFeature;
    if (!publisherAssetsFeature) {
        throw new Error('LabPublisherAssetsFeature must load before lab-publisher.js');
    }
    const publisherResourceFeature = window.LabPublisherResourceFeature;
    if (!publisherResourceFeature) {
        throw new Error('LabPublisherResourceFeature must load before lab-publisher.js');
    }
    const publisherAvailabilityFeature = window.LabPublisherAvailabilityFeature;
    if (!publisherAvailabilityFeature) {
        throw new Error('LabPublisherAvailabilityFeature must load before lab-publisher.js');
    }

    const state = {
        status: null,
        hosts: [],
        guacamole: [],
        fmus: [],
        modelVariables: [],
        imageMode: 'link',
        docMode: 'link',
        fmuDescribeController: null,
        termsController: null,
        labs: [],
        editingLabId: null,
        originalRawPrice: null,
        originalDisplayPrice: null,
        originalPriceUnit: null,
    };

    const parseHourlyCreditsToRaw = publisherValues.parseHourlyCreditsToRaw;
    const normalizePricingUnit = publisherValues.normalizePricingUnit;
    const convertDisplayCreditsToRawPerSecond = publisherValues.convertDisplayCreditsToRawPerSecond;
    const formatRawPriceForUnit = publisherValues.formatRawPriceForUnit;
    const resolveLabPriceUnit = publisherValues.resolveLabPriceUnit;
    const fetchJson = (url, options) => publisherValues.fetchJson(url, options, fetch);
    const assertLabMutationSuccess = publisherValues.assertLabMutationSuccess;
    const CLASSIFICATION_SCHEMES = publisherValues.CLASSIFICATION_SCHEMES;
    const CLASSIFICATION_SCHEME_VERSIONS = publisherValues.CLASSIFICATION_SCHEME_VERSIONS;
    const getFordField = publisherValues.getFordField;
    const normalizeClassificationEntries = publisherValues.normalizeClassificationEntries;
    const buildClassificationEntries = publisherValues.buildClassificationEntries;
    const normalizeMaxConcurrentUsers = publisherValues.normalizeMaxConcurrentUsers;
    const sanitizeAvailableHours = publisherValues.sanitizeAvailableHours;
    const sanitizeUnavailableWindows = publisherValues.sanitizeUnavailableWindows;
    const sanitizeTermsOfUse = publisherValues.sanitizeTermsOfUse;
    const normalizePeriodUnit = publisherValues.normalizePeriodUnit;
    const expandAllowedDurations = publisherValues.expandAllowedDurations;
    const buildPeriodRules = publisherValues.buildPeriodRules;
    const deriveAllowedPeriodRange = publisherValues.deriveAllowedPeriodRange;
    const resolveLabDisplayName = publisherValues.resolveLabDisplayName;
    const resolveSupportedTimezones = publisherValues.resolveSupportedTimezones;
    const resolveBrowserTimezone = publisherValues.resolveBrowserTimezone;
    const metadataAttributes = publisherValues.metadataAttributes;
    const normalizeTraitType = publisherValues.normalizeTraitType;
    const normalizeArray = publisherValues.normalizeArray;
    const splitCsv = publisherValues.splitCsv;
    const mergeMediaUrls = publisherValues.mergeMediaUrls;
    const dateInputToUnix = publisherValues.dateInputToUnix;
    const unixToDateInput = publisherValues.unixToDateInput;
    const guessVersionFromUrl = publisherValues.guessVersionFromUrl;
    const RESOURCE_TYPES = { LAB: 'lab', FMU: 'fmu' };
    const escapeHtml = publisherValues.escapeHtml;
    const escapeAttr = publisherValues.escapeAttr;

    const normalizeConnectionUsers = publisherValues.normalizeConnectionUsers;

    const resolveConnectionAccessKey = publisherValues.resolveConnectionAccessKey;

    const formatConnectionUsers = publisherValues.formatConnectionUsers;
    const renderLabActionIcon = publisherRenderers.renderLabActionIcon;
    const renderModelVariablesTable = publisherRenderers.renderModelVariables;
    const collectDetectedResources = publisherResources.collectDetectedResources;
    const uniqueGuacamole = publisherResources.uniqueGuacamole;
    const fetchFmuMetadata = publisherResources.fetchFmuMetadata;
    const buildAssetUploadRequest = publisherAssets.buildAssetUploadRequest;
    const buildAssetDeleteRequest = publisherAssets.buildAssetDeleteRequest;
    const renderAssetList = publisherAssets.renderAssetList;
    const buildMetadataPayload = publisherMetadata.buildMetadata;
    const $ = (id) => document.getElementById(id);
    let assetsController;
    let resourceFeatureController;
    let labActionsController;
    let availabilityController;

    document.addEventListener('DOMContentLoaded', () => {
        const refresh = $('labPublisherRefreshBtn');
        const submit = $('labPublisherSubmitBtn');
        const cancelEdit = $('labPublisherCancelEditBtn');
        const labList = $('labPublisherList');
        const images = $('labImages');
        const docs = $('labDocs');
        const imageChoose = $('labImagesChooseBtn');
        const docChoose = $('labDocsChooseBtn');
        const assetList = $('labAssetList');
        const termsUrl = $('labTermsUrl');
        const priceUnit = $('labPriceUnit');
        const periodUnit = $('labAllowedPeriodUnit');

        if (!refresh || !submit) return;

        assetsController = publisherAssetsFeature.createController({
            assetListElement: assetList,
            inputs: { images, docs },
            ensureContentId,
            fetchJson,
            buildAssetUploadRequest,
            buildAssetDeleteRequest,
            renderAssetList,
            escapeHtml,
            escapeAttr,
            callbacks: { setStatus },
        });
        assetsController.bind();

        resourceFeatureController = publisherResourceFeature.createController({
            documentImpl: document,
            windowImpl: window,
            getStatus: () => state.status,
            getFmus: () => state.fmus,
            getGuacamole: () => state.guacamole,
            uniqueGuacamole,
            formatConnectionUsers,
            resolveConnectionAccessKey,
            normalizeMaxConcurrentUsers,
            resetFmuDescribeFields,
            autoDetectFmuMetadata,
        });
        resourceFeatureController.bind();

        availabilityController = publisherAvailabilityFeature.createController({
            documentImpl: document,
            fordFieldsGrouped: publisherValues.FORD_FIELDS_GROUPED,
            iscedFields: publisherValues.ISCED_F_FIELDS,
            getSuggestedIscedCodes: publisherValues.getSuggestedIscedCodes,
            weekdayOptions: publisherValues.WEEKDAY_OPTIONS,
            escapeHtml,
            escapeAttr,
            dateCtor: Date,
        });
        availabilityController.initialize();

        labActionsController = publisherLabActions.createController({
            listElement: labList,
            getLabs: () => state.labs,
            getEditingLabId: () => state.editingLabId,
            fetchJson,
            assertLabMutationSuccess,
            renderLabActionIcon,
            escapeHtml,
            escapeAttr,
            formatRawPriceForUnit,
            resolveLabPriceUnit,
            resolveLabDisplayName,
            confirmImpl: message => window.confirm(message),
            callbacks: {
                onEdit: enterEditMode,
                onClearEdit: () => clearEditMode(false),
                onReload: loadPublisherData,
                setStatus,
            },
        });
        labActionsController.bind();

        initMarketplaceFields();
        refresh.addEventListener('click', loadPublisherData);
        submit.addEventListener('click', publishLab);
        if (cancelEdit) cancelEdit.addEventListener('click', () => clearEditMode(true));
        if (priceUnit) priceUnit.addEventListener('change', syncBookingModeFields);
        if (periodUnit) periodUnit.addEventListener('change', () => normalizeAllowedPeriodRange());
        images.addEventListener('change', () => void assetsController.upload(images.files, 'images'));
        docs.addEventListener('change', () => void assetsController.upload(docs.files, 'docs'));
        imageChoose.addEventListener('click', () => images.click());
        docChoose.addEventListener('click', () => docs.click());
        termsUrl.addEventListener('blur', autoFetchTermsMetadata);

        resourceFeatureController.syncSetupMode();
        resourceFeatureController.syncTypeFields();
        syncBookingModeFields();
        let publisherInitialized = false;
        const initializePublisher = () => {
            if (publisherInitialized) return;
            publisherInitialized = true;
            loadPublisherData({ skipAuthPrompt: true });
        };
        document.addEventListener('lab-manager:tab-activated', event => {
            if (event.detail && event.detail.tab === 'laboratories') initializePublisher();
        });
        if (window.LabManagerTabs && window.LabManagerTabs.activeTab === 'laboratories') {
            initializePublisher();
        }
    });

    function initMarketplaceFields() {
        populateTimezoneOptions();
        normalizeAllowedPeriodRange();
        setupMediaMode('images', 'link');
        setupMediaMode('docs', 'link');
        syncBookingModeFields();
        $('labImageMode').querySelectorAll('button').forEach(button => {
            button.addEventListener('click', () => setupMediaMode('images', button.dataset.mode));
        });
        $('labDocMode').querySelectorAll('button').forEach(button => {
            button.addEventListener('click', () => setupMediaMode('docs', button.dataset.mode));
        });
    }

    function syncBookingModeFields() {
        const priceUnit = normalizePricingUnit($('labPriceUnit')?.value || 'hour');
        const mode = getDerivedBookingMode();
        if ($('labBookingMode')) $('labBookingMode').value = mode;
        populateAllowedPeriodUnitOptions(priceUnit);
        normalizeAllowedPeriodRange();
        document.querySelectorAll('.scheduling-grid').forEach(grid => {
            grid.classList.toggle('calendar-period-mode', mode === 'calendar-period');
        });
        document.querySelectorAll('.booking-slot-field').forEach(field => {
            field.classList.toggle('is-hidden', mode !== 'slot');
        });
        document.querySelectorAll('.booking-period-field').forEach(field => {
            field.classList.toggle('is-hidden', mode !== 'calendar-period');
        });
    }

    function getDerivedBookingMode() {
        return normalizePricingUnit($('labPriceUnit')?.value || 'hour') === 'hour' ? 'slot' : 'calendar-period';
    }

    function populateAllowedPeriodUnitOptions(priceUnit = normalizePricingUnit($('labPriceUnit')?.value || 'hour')) {
        const unitSelect = $('labAllowedPeriodUnit');
        if (!unitSelect) return;

        const orderedUnits = [
            { value: 'day', label: 'days' },
            { value: 'week', label: 'weeks' },
            { value: 'month', label: '30-day months' },
        ];
        const minimumUnit = priceUnit === 'month' ? 'month' : priceUnit === 'week' ? 'week' : 'day';
        const minimumIndex = orderedUnits.findIndex(unit => unit.value === minimumUnit);
        const previous = normalizePeriodUnit(unitSelect.value);
        const options = orderedUnits.slice(Math.max(0, minimumIndex));

        unitSelect.innerHTML = '';
        options.forEach(unit => unitSelect.add(new Option(unit.label, unit.value)));
        unitSelect.value = options.some(unit => unit.value === previous) ? previous : options[0].value;
    }

    function normalizeAllowedPeriodRange(preferredRange = {}) {
        const minInput = $('labAllowedPeriodMin');
        const maxInput = $('labAllowedPeriodMax');
        const unit = normalizePeriodUnit($('labAllowedPeriodUnit')?.value || 'day');
        if (!minInput || !maxInput) return;

        const maxByUnit = { day: 90, week: 12, month: 3 };
        const unitMax = maxByUnit[unit] || 90;
        const rawMin = Math.trunc(Number(preferredRange.min ?? minInput.value ?? 1));
        const rawMax = Math.trunc(Number(preferredRange.max ?? maxInput.value ?? rawMin));
        const normalizedMin = Math.min(Math.max(Number.isFinite(rawMin) ? rawMin : 1, 1), unitMax);
        const normalizedMax = Math.min(Math.max(Number.isFinite(rawMax) ? rawMax : normalizedMin, normalizedMin), unitMax);

        [minInput, maxInput].forEach(input => {
            input.min = '1';
            input.max = String(unitMax);
            input.step = '1';
        });
        minInput.value = String(normalizedMin);
        maxInput.min = String(normalizedMin);
        maxInput.value = String(normalizedMax);
    }

    function populateTimezoneOptions() {
        const select = $('labTimezone');
        const options = resolveSupportedTimezones();
        const browserTimezone = resolveBrowserTimezone();
        select.innerHTML = '<option value="">Select timezone</option>';
        options.forEach(timezone => {
            const option = document.createElement('option');
            option.value = timezone;
            option.textContent = timezone;
            select.appendChild(option);
        });
        select.value = options.includes(browserTimezone) ? browserTimezone : 'Europe/Madrid';
    }

    async function loadPublisherData(options = {}) {
        setStatus('Loading provider status...', false);
        try {
            const [status, hosts, labs] = await Promise.all([
                fetchJson('/lab-admin/status', options),
                fetchJson('/ops/api/hosts', options).catch(() => null),
                fetchJson('/lab-admin/labs', options).catch(() => null),
            ]);
            state.status = status;
            state.hosts = hosts?.hosts || [];
            const detectedResources = collectDetectedResources({
                hosts: hosts || {},
                fmuInventory: status?.fmuInventory,
            });
            state.guacamole = detectedResources.guacamole;
            state.fmus = detectedResources.fmus;
            resourceFeatureController.renderOptions();
            state.labs = labs?.labs || [];
            labActionsController.render(state.labs);
            const providerLabel = status?.isProvider
                ? `Provider wallet: ${status.providerAddress}`
                : 'This Gateway wallet is not registered as provider yet.';
            setStatus(providerLabel, !status?.isProvider);
        } catch (err) {
            setStatus(err.message || 'Unable to load Lab Publisher data', true);
        }
    }

    function setupMediaMode(kind, mode) {
        const isImages = kind === 'images';
        const stateKey = isImages ? 'imageMode' : 'docMode';
        const control = $(isImages ? 'labImageMode' : 'labDocMode');
        const linkInput = $(isImages ? 'labImageUrls' : 'labDocUrls');
        const chooseBtn = $(isImages ? 'labImagesChooseBtn' : 'labDocsChooseBtn');
        state[stateKey] = mode;
        control.querySelectorAll('button').forEach(button => {
            button.classList.toggle('active', button.dataset.mode === mode);
        });
        linkInput.hidden = mode !== 'link';
        chooseBtn.hidden = mode !== 'upload';
    }

    async function publishLab() {
        try {
            const payload = buildLabPayload();
            const editing = !!state.editingLabId;

            $('labPublisherSubmitBtn').disabled = true;
            setStatus(editing ? `Updating ${resolveStateLabDisplayName(state.editingLabId)} on-chain...` : 'Publishing lab on-chain...', false);
            const result = await fetchJson(editing ? `/lab-admin/labs/${encodeURIComponent(state.editingLabId)}` : '/lab-admin/labs', {
                method: editing ? 'PUT' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            assertLabMutationSuccess(result, editing ? 'Update' : 'Publish');
            const transactionMessage = result.transactionHash
                ? ` Tx: ${result.transactionHash}`
                : (editing ? ' Metadata saved without an on-chain transaction.' : '');
            const action = String(result.action || '').toLowerCase();
            const createLabel = result.action === 'existingLab' || result.status === 'already_exists'
                ? 'Existing lab'
                : action.includes('andlist') ? 'Listed' : 'Created';
            const resultLabLabel = result.labId ? ` ${resolveStateLabDisplayName(result.labId)}` : '';
            setStatus(`${editing ? 'Updated' : createLabel}.${transactionMessage}${resultLabLabel}`, false);
            if (editing) clearEditMode(false);
            await loadPublisherData();
        } catch (err) {
            setStatus(err.message || (state.editingLabId ? 'Update failed' : 'Publish failed'), true);
        } finally {
            $('labPublisherSubmitBtn').disabled = false;
        }
    }

    function buildLabPayload() {
        resourceFeatureController.syncTypeFields();
        const setupMode = $('labSetupMode').value;
        const isFmu = $('labResourceType').value === '1';
        if (isFmu && !$('labFmuFileName').value.trim()) {
            throw new Error('FMU File Name is required');
        }
        const payload = {
            setupMode,
            listImmediately: $('labListImmediately').value === 'true',
            price: resolvePayloadRawPrice(),
            accessURI: $('labAccessURI').value.trim(),
            accessKey: $('labAccessKey').value.trim(),
            resourceType: Number($('labResourceType').value),
            creatorPucHash: $('labCreatorPucHash').value.trim(),
        };
        if (setupMode === 'quick') {
            payload.metadataUrl = $('labMetadataUrl').value.trim();
        } else {
            payload.metadata = buildMetadata();
        }
        return payload;
    }

    function buildMetadata() {
        resourceFeatureController.syncTypeFields();
        validateMarketplaceFields();
        const availability = availabilityController.getState();
        const imageUrls = state.imageMode === 'link'
            ? splitCsv($('labImageUrls').value)
            : assetsController.getUploadedImages();
        const docs = state.docMode === 'link'
            ? splitCsv($('labDocUrls').value)
            : assetsController.getUploadedDocs();
        const classification = buildClassificationEntries({
            fordCodes: availability.selectedCategories,
            iscedCodes: availability.selectedIscedCodes,
            educationalProgramLinked: availability.educationalProgramLinked,
        });
        const keywords = splitCsv($('labKeywords').value);
        const resourceType = $('labResourceType').value === '1' ? RESOURCE_TYPES.FMU : RESOURCE_TYPES.LAB;
        const fmuFileName = $('labFmuFileName').value.trim();
        const unavailableWindows = sanitizeUnavailableWindows(availability.unavailableWindows);
        const priceUnit = normalizePricingUnit($('labPriceUnit').value || 'hour');
        const rawPricePerSecond = convertDisplayCreditsToRawPerSecond($('labPrice').value || '0', priceUnit);
        const bookingMode = getDerivedBookingMode();
        const timeSlots = splitCsv($('labTimeSlots').value).map(Number).filter(Number.isFinite);
        const allowedDurationRange = bookingMode === 'calendar-period'
            ? getSelectedAllowedPeriodRange()
            : null;
        const allowedDurations = bookingMode === 'calendar-period'
            ? expandAllowedDurations(allowedDurationRange)
            : timeSlots.map(slot => ({ unit: 'minute', value: slot }));
        const periodRules = bookingMode === 'calendar-period'
            ? buildPeriodRules(allowedDurationRange)
            : null;
        const pricing = {
            displayAmount: $('labPrice').value.trim(),
            displayUnit: priceUnit,
            rawPricePerSecond: rawPricePerSecond.toString(),
            roundingMode: 'nearest-per-second',
            billingMode: 'linear-duration',
        };
        const termsOfUse = sanitizeTermsOfUse({
            url: $('labTermsUrl').value.trim(),
            version: $('labTermsVersion').value.trim(),
            effectiveDate: $('labTermsEffectiveDate').value.trim(),
            sha256: $('labTermsSha256').value.trim(),
        });
        return buildMetadataPayload({
            contentId: ensureContentId(),
            name: $('labName').value.trim(),
            description: $('labDescription').value.trim(),
            imageUrls,
            docs,
            demoEnabled: $('labDemoEnabled').checked === true,
            classification,
            educationalProgramLinked: availability.educationalProgramLinked,
            keywords,
            resourceType,
            fmuFileName,
            unavailableWindows,
            bookingMode,
            timeSlots,
            allowedDurationRange,
            allowedDurations,
            periodRules,
            pricing,
            termsOfUse,
            opens: dateInputToUnix($('labOpens').value),
            closes: dateInputToUnix($('labCloses').value),
            availableDays: availability.availableDays,
            availableHours: sanitizeAvailableHours($('labAvailableHoursStart').value, $('labAvailableHoursEnd').value),
            maxConcurrentUsers: normalizeMaxConcurrentUsers($('labMaxConcurrentUsers').value, resourceType === RESOURCE_TYPES.FMU),
            timezone: $('labTimezone').value.trim() || '',
            fmiVersion: $('labFmiVersion').value.trim(),
            simulationType: $('labSimulationType').value.trim(),
            modelVariables: state.modelVariables,
            defaultStartTime: $('labDefaultStartTime').value,
            defaultStopTime: $('labDefaultStopTime').value,
            defaultStepSize: $('labDefaultStepSize').value,
        });
    }

    function validateMarketplaceFields() {
        const isFmu = $('labResourceType').value === '1';
        const required = [
            ['Name', $('labName').value.trim()],
            ['Description', $('labDescription').value.trim()],
            ['Price', $('labPrice').value.trim()],
            ['Access URI', $('labAccessURI').value.trim()],
            ['Timezone', $('labTimezone').value.trim()],
        ];
        const bookingMode = getDerivedBookingMode();
        if (bookingMode === 'slot') {
            required.push(
                ['Daily Start Time', $('labAvailableHoursStart').value.trim()],
                ['Daily End Time', $('labAvailableHoursEnd').value.trim()]
            );
        }
        const missing = required.find(([, value]) => !value);
        if (missing) throw new Error(`${missing[0]} is required`);
        const availability = availabilityController.getState();
        if (!availability.selectedCategories.some(code => getFordField(code))) throw new Error('At least one valid OECD FORD field is required');
        if (!availability.availableDays.length) throw new Error('Select at least one available day');
        if (bookingMode === 'slot' && !splitCsv($('labTimeSlots').value).map(Number).some(Number.isFinite)) {
            throw new Error('Time Slots must include at least one duration in minutes');
        }
        if (bookingMode === 'calendar-period' && !expandAllowedDurations(getSelectedAllowedPeriodRange()).length) {
            throw new Error('Select a valid minimum and maximum period');
        }
        const opens = dateInputToUnix($('labOpens').value);
        const closes = dateInputToUnix($('labCloses').value);
        if (!opens) throw new Error('Opens is required');
        if (!closes) throw new Error('Closes is required');
        if (closes < opens) throw new Error('Closes must be after or equal to Opens');
        if (isFmu) {
            const fmuFileName = $('labFmuFileName').value.trim();
            if (!fmuFileName) throw new Error('FMU File Name is required');
            if (!/^[A-Za-z0-9._/-]+\.fmu$/i.test(fmuFileName)) {
                throw new Error('FMU File Name must end with .fmu and contain only valid characters');
            }
        } else if (!/^guac:id:[1-9][0-9]*$/.test($('labAccessKey').value.trim())) {
            throw new Error('Connection ID is required');
        }
    }

    function ensureContentId() {
        const el = $('labContentId');
        if (!el.value.trim()) {
            setContentId(`lab-${Date.now().toString(36)}`);
        }
        return el.value.trim();
    }

    function setContentId(value) {
        const normalized = String(value || '').trim();
        const input = $('labContentId');
        const display = $('labContentIdDisplay');
        if (input) input.value = normalized;
        if (display) display.textContent = normalized || 'auto-generated';
    }

    async function autoFetchTermsMetadata() {
        const url = $('labTermsUrl').value.trim();
        const status = $('labTermsStatus');
        if (state.termsController) state.termsController.abort();
        $('labTermsVersion').value = '';
        $('labTermsEffectiveDate').value = '';
        $('labTermsSha256').value = '';
        status.textContent = '';
        if (!url) return;
        if (!/^https?:\/\//i.test(url)) {
            status.textContent = 'Terms link must be an absolute HTTP(S) URL.';
            return;
        }

        const controller = new AbortController();
        state.termsController = controller;
        status.textContent = 'Fetching metadata...';
        try {
            const response = await fetch(url, { signal: controller.signal });
            if (!response.ok) throw new Error('Unable to download the Terms of Use document.');
            const buffer = await response.arrayBuffer();
            let shaValue = '';
            if (window.crypto?.subtle?.digest) {
                shaValue = await sha256Hex(buffer);
            }
            $('labTermsVersion').value = guessVersionFromUrl(url);
            $('labTermsEffectiveDate').value = new Date().toISOString().split('T')[0];
            $('labTermsSha256').value = shaValue;
            status.textContent = shaValue
                ? 'Terms metadata auto-filled.'
                : 'Terms date auto-filled; SHA-256 unavailable in this browser context.';
        } catch (err) {
            if (err.name === 'AbortError') return;
            status.textContent = 'Unable to auto-fill version/date/hash for this link.';
        } finally {
            if (state.termsController === controller) state.termsController = null;
        }
    }

    async function autoDetectFmuMetadata() {
        const fmuFileName = $('labFmuFileName').value.trim();
        const gatewayUrl = $('labAccessURI').value.trim();
        const status = $('labFmuDescribeStatus');
        if (!fmuFileName) {
            status.textContent = 'Set FMU File Name first.';
            return;
        }
        if (!gatewayUrl) {
            status.textContent = 'Set Access URI first.';
            return;
        }
        if (state.fmuDescribeController) state.fmuDescribeController.abort();
        const controller = new AbortController();
        state.fmuDescribeController = controller;
        resetFmuDescribeFields(true);
        status.textContent = 'Loading FMU metadata...';
        try {
            const metadata = await fetchFmuMetadata({
                fmuFileName,
                gatewayUrl,
                signal: controller.signal,
                fetchImpl: fetch,
            });
            if (state.fmuDescribeController !== controller) return;
            applyFmuMetadata(metadata);
            status.textContent = 'FMU metadata loaded successfully.';
        } catch (err) {
            if (err.name === 'AbortError') return;
            status.textContent = `Auto-detect failed: ${err.message}`;
        } finally {
            if (state.fmuDescribeController === controller) state.fmuDescribeController = null;
        }
    }

    function resetFmuDescribeFields(keepStatus) {
        $('labFmiVersion').value = '';
        $('labSimulationType').value = '';
        $('labDefaultStartTime').value = '';
        $('labDefaultStopTime').value = '';
        $('labDefaultStepSize').value = '';
        state.modelVariables = [];
        renderModelVariables();
        if (!keepStatus) $('labFmuDescribeStatus').textContent = 'Set Access URI and FMU File Name to enable auto-detect.';
    }

    function applyFmuMetadata(metadata) {
        $('labFmiVersion').value = metadata.fmiVersion || '';
        $('labSimulationType').value = metadata.simulationType || '';
        $('labDefaultStartTime').value = metadata.defaultStartTime ?? '';
        $('labDefaultStopTime').value = metadata.defaultStopTime ?? '';
        $('labDefaultStepSize').value = metadata.defaultStepSize ?? '';
        if (metadata.modelName) {
            $('labName').value = metadata.modelName;
        }
        state.modelVariables = Array.isArray(metadata.modelVariables) ? metadata.modelVariables : [];
        renderModelVariables();
    }

    function renderModelVariables() {
        const wrap = $('labModelVariablesWrap');
        const body = $('labModelVariables');
        const rendered = renderModelVariablesTable({
            modelVariables: state.modelVariables,
            escapeHtml,
        });
        wrap.hidden = rendered.hidden;
        body.innerHTML = rendered.html;
    }

    function resolveStateLabDisplayName(labId) {
        const lab = state.labs.find(item => String(item?.labId) === String(labId));
        return resolveLabDisplayName(lab || { labId });
    }

    async function enterEditMode(lab) {
        state.editingLabId = String(lab.labId);
        resetFmuDescribeFields(false);
        applyLabBaseFields(lab);
        await applyLabMetadata(lab);
        captureOriginalEditPrice(lab);
        resourceFeatureController.syncSetupMode();
        resourceFeatureController.syncTypeFields();
        syncBookingModeFields();
        updateEditControls();
        setStatus(`Editing ${resolveLabDisplayName(lab)}. Use Save Lab to persist changes.`, false);
        $('labName').focus();
    }

    function applyLabBaseFields(lab) {
        $('labSetupMode').value = 'full';
        $('labResourceType').value = String(Number(lab.resourceType) || 0);
        $('labDetectedResource').value = '';
        $('labListImmediately').value = lab.listed ? 'true' : 'false';
        $('labAccessURI').value = lab.accessURI || '';
        $('labCreatorPucHash').value = '';
        $('labAccessKey').value = lab.accessKey || '';
        $('labMaxConcurrentUsers').value = Number(lab.resourceType) === 1 ? '2' : '1';
        const priceUnit = resolveLabPriceUnit(lab);
        $('labPriceUnit').value = priceUnit;
        $('labPrice').value = formatRawPriceForUnit(lab.price || '0', priceUnit);
        $('labMetadataUrl').value = lab.uri || '';
        const contentId = extractContentIdFromMetadataUri(lab.uri);
        setContentId(contentId);
        if (Number(lab.resourceType) === 1) {
            $('labFmuFileName').value = lab.accessKey || '';
        }
    }

    async function applyLabMetadata(lab) {
        const metadataUrl = lab.uri || '';
        if (!metadataUrl) return;
        try {
            const response = await fetch(metadataUrl, { credentials: 'omit' });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const metadata = await response.json();
            populateMetadataForm(metadata);
        } catch (err) {
            $('labSetupMode').value = 'quick';
            $('labMetadataUrl').value = metadataUrl;
            setStatus(`Editing ${resolveLabDisplayName(lab)}. Metadata could not be loaded; quick URL mode enabled.`, true);
        }
    }

    function populateMetadataForm(metadata) {
        $('labName').value = metadata?.name || '';
        $('labDescription').value = metadata?.description || '';
        const attributes = metadataAttributes(metadata?.attributes);
        const classificationFromAttributes = getAttributeValue(attributes, 'classification');
        const keywordsFromAttributes = getAttributeValue(attributes, 'keywords');
        $('labKeywords').value = normalizeArray(metadata?.keywords ?? keywordsFromAttributes).join(', ');
        const normalizedClassification = normalizeClassificationEntries(metadata?.classification ?? classificationFromAttributes);
        const selectedCategories = normalizedClassification
            .filter(entry => entry.scheme === CLASSIFICATION_SCHEMES.FORD)
            .map(entry => entry.code);
        const selectedIscedCodes = normalizedClassification
            .filter(entry => entry.scheme === CLASSIFICATION_SCHEMES.ISCED_F)
            .map(entry => entry.code);
        const educationalProgramLinked = selectedIscedCodes.length > 0
            || getAttributeValue(attributes, 'educationalProgramLinked') === true;
        availabilityController.hydrate({
            selectedCategories,
            selectedIscedCodes,
            iscedSelectionTouched: selectedIscedCodes.length > 0,
            educationalProgramLinked,
        });
        const images = mergeMediaUrls(
            metadata?.image,
            metadata?.images,
            getAttributeValue(attributes, 'additionalImages')
        );
        const docs = mergeMediaUrls(
            metadata?.docs,
            metadata?.documents,
            getAttributeValue(attributes, 'docs'),
            getAttributeValue(attributes, 'documents')
        );
        setupMediaMode('images', 'upload');
        setupMediaMode('docs', 'upload');
        assetsController.setUploadedAssets({ images, docs });
        $('labImageUrls').value = images.join(', ');
        $('labDocUrls').value = docs.join(', ');
        $('labDemoEnabled').checked = metadata?.demoEnabled === true;

        if (metadata?.pricing?.displayUnit) {
            $('labPriceUnit').value = normalizePricingUnit(metadata.pricing.displayUnit);
        }
        if (metadata?.pricing?.displayAmount) {
            $('labPrice').value = metadata.pricing.displayAmount;
        }
        if (metadata?.allowedDurationRange) {
            setAllowedPeriodRangeControls(metadata.allowedDurationRange);
        }
        if (Array.isArray(metadata?.allowedDurations) && metadata.allowedDurations.length) {
            setAllowedPeriodRangeControls(deriveAllowedPeriodRange(metadata.allowedDurations));
        }
        setAttributeValue(attributes, 'timeSlots', value => $('labTimeSlots').value = normalizeArray(value).join(', '));
        setAttributeValue(attributes, 'pricing', value => {
            if (value?.displayUnit) $('labPriceUnit').value = normalizePricingUnit(value.displayUnit);
            if (value?.displayAmount) $('labPrice').value = value.displayAmount;
        });
        setAttributeValue(attributes, 'pricingUnit', value => {
            if (value) $('labPriceUnit').value = normalizePricingUnit(value);
        });
        setAttributeValue(attributes, 'pricingDisplayAmount', value => {
            if (value !== undefined && value !== null && value !== '') $('labPrice').value = String(value);
        });
        setAttributeValue(attributes, 'allowedDurations', value => {
            const range = deriveAllowedPeriodRange(value);
            if (range) setAllowedPeriodRangeControls(range);
        });
        setAttributeValue(attributes, 'allowedDurationRange', value => {
            if (value) setAllowedPeriodRangeControls(value);
        });
        syncBookingModeFields();
        setAttributeValue(attributes, 'opens', value => $('labOpens').value = unixToDateInput(value));
        setAttributeValue(attributes, 'closes', value => $('labCloses').value = unixToDateInput(value));
        setAttributeValue(attributes, 'availableDays', value => {
            availabilityController.hydrate({ availableDays: normalizeArray(value) });
        });
        setAttributeValue(attributes, 'availableHours', value => {
            $('labAvailableHoursStart').value = sanitizeTime(value?.start || '') || '09:00';
            $('labAvailableHoursEnd').value = sanitizeTime(value?.end || '') || '17:00';
        });
        setAttributeValue(attributes, 'maxConcurrentUsers', value => {
            const isFmu = $('labResourceType').value === '1';
            $('labMaxConcurrentUsers').value = String(normalizeMaxConcurrentUsers(value, isFmu));
        });
        setAttributeValue(attributes, 'unavailableWindows', value => {
            availabilityController.hydrate({ unavailableWindows: Array.isArray(value) ? value : [] });
        });
        setAttributeValue(attributes, 'termsOfUse', value => {
            $('labTermsUrl').value = value?.url || '';
            $('labTermsVersion').value = value?.version || '';
            $('labTermsEffectiveDate').value = value?.effectiveDate || '';
            $('labTermsSha256').value = value?.sha256 || '';
        });
        setAttributeValue(attributes, 'timezone', value => {
            if (value) $('labTimezone').value = value;
        });
        setAttributeValue(attributes, 'fmuFileName', value => {
            if (value) $('labFmuFileName').value = value;
        });
        setAttributeValue(attributes, 'fmiVersion', value => $('labFmiVersion').value = value || '');
        setAttributeValue(attributes, 'simulationType', value => $('labSimulationType').value = value || '');
        setAttributeValue(attributes, 'defaultStartTime', value => $('labDefaultStartTime').value = value ?? '');
        setAttributeValue(attributes, 'defaultStopTime', value => $('labDefaultStopTime').value = value ?? '');
        setAttributeValue(attributes, 'defaultStepSize', value => $('labDefaultStepSize').value = value ?? '');
        setAttributeValue(attributes, 'modelVariables', value => {
            state.modelVariables = Array.isArray(value) ? value : [];
            renderModelVariables();
        });
    }

    function clearEditMode(resetStatus = true) {
        state.editingLabId = null;
        state.originalRawPrice = null;
        state.originalDisplayPrice = null;
        state.originalPriceUnit = null;
        resetLabPublisherForm();
        updateEditControls();
        if (resetStatus) setStatus('Edit cancelled.', false);
    }

    function resetLabPublisherForm() {
        if (state.fmuDescribeController) {
            state.fmuDescribeController.abort();
            state.fmuDescribeController = null;
        }

        availabilityController.reset();
        state.modelVariables = [];
        assetsController.clearUploadedAssets();

        setValue('labResourceType', '0');
        setValue('labSetupMode', 'full');
        setValue('labListImmediately', 'true');
        setValue('labAccessKey', '');
        setValue('labPrice', '0');
        setValue('labPriceUnit', 'hour');
        setValue('labAccessURI', '');
        setValue('labCreatorPucHash', '');
        setValue('labMetadataUrl', '');
        setValue('labName', '');
        setValue('labKeywords', '');
        setValue('labDescription', '');
        setValue('labOpens', '');
        setValue('labCloses', '');
        setValue('labTimeSlots', '30,60');
        setValue('labAllowedPeriodMin', '1');
        setValue('labAllowedPeriodMax', '1');
        setValue('labAllowedPeriodUnit', 'day');
        setValue('labAvailableHoursStart', '09:00');
        setValue('labAvailableHoursEnd', '17:00');
        setValue('labMaxConcurrentUsers', '1');
        setValue('labTermsUrl', '');
        setValue('labTermsVersion', '');
        setValue('labTermsEffectiveDate', '');
        setValue('labTermsSha256', '');
        setText('labTermsStatus', '');
        setValue('labFmuFileName', '');
        setValue('labImageUrls', '');
        setValue('labDocUrls', '');
        setValue('labImages', '');
        setValue('labDocs', '');
        setChecked('labEducationalProgramLinked', false);
        setChecked('labDemoEnabled', false);
        setContentId('');
        populateTimezoneOptions();
        resourceFeatureController.renderOptions();
        setupMediaMode('images', 'link');
        setupMediaMode('docs', 'link');
        resetFmuDescribeFields(false);
        resourceFeatureController.syncSetupMode();
        resourceFeatureController.syncTypeFields();
        syncBookingModeFields();
    }

    function setValue(id, value) {
        const el = $(id);
        if (el) el.value = value;
    }

    function setChecked(id, checked) {
        const el = $(id);
        if (el) el.checked = checked;
    }

    function setText(id, value) {
        const el = $(id);
        if (el) el.textContent = value;
    }

    function captureOriginalEditPrice(lab) {
        state.originalRawPrice = String(lab?.price ?? '0');
        state.originalDisplayPrice = String($('labPrice')?.value ?? '').trim();
        state.originalPriceUnit = normalizePricingUnit($('labPriceUnit')?.value || 'hour');
    }

    function resolvePayloadRawPrice() {
        const priceInput = String($('labPrice')?.value ?? '0').trim();
        const priceUnit = normalizePricingUnit($('labPriceUnit')?.value || 'hour');
        const priceUnchangedDuringEdit = !!state.editingLabId
            && state.originalRawPrice !== null
            && priceInput === String(state.originalDisplayPrice ?? '').trim()
            && priceUnit === state.originalPriceUnit;

        if (priceUnchangedDuringEdit) {
            return state.originalRawPrice;
        }

        return convertDisplayCreditsToRawPerSecond(priceInput || '0', priceUnit).toString();
    }

    function updateEditControls() {
        const submit = $('labPublisherSubmitBtn');
        const cancel = $('labPublisherCancelEditBtn');
        const editing = !!state.editingLabId;
        submit.innerHTML = editing ? '<i class="fas fa-save"></i> Save Lab' : '<i class="fas fa-upload"></i> Publish Lab';
        if (cancel) cancel.hidden = !editing;
    }

    function setAttributeValue(attributes, traitType, setter) {
        const attribute = attributes.find(item => normalizeTraitType(item.trait_type) === normalizeTraitType(traitType));
        if (attribute) setter(attribute.value);
    }

    function getAttributeValue(attributes, traitType) {
        return attributes.find(item => normalizeTraitType(item.trait_type) === normalizeTraitType(traitType))?.value;
    }

    function extractContentIdFromMetadataUri(value) {
        try {
            const path = new URL(value, window.location.origin).pathname;
            const match = path.match(/\/lab-content\/content\/([^/]+)\/metadata\.json$/);
            return match ? decodeURIComponent(match[1]) : '';
        } catch {
            return '';
        }
    }

    function setStatus(message, isError) {
        const el = $('labPublisherStatus');
        if (!el) return;
        el.textContent = message;
        el.classList.toggle('error', !!isError);
    }

    async function sha256Hex(buffer) {
        const hashBuffer = await window.crypto.subtle.digest('SHA-256', buffer);
        return Array.from(new Uint8Array(hashBuffer))
            .map(byte => byte.toString(16).padStart(2, '0'))
            .join('');
    }

    function getSelectedAllowedPeriodRange() {
        normalizeAllowedPeriodRange();
        const min = Number($('labAllowedPeriodMin')?.value || 0);
        const max = Number($('labAllowedPeriodMax')?.value || 0);
        const unit = normalizePeriodUnit($('labAllowedPeriodUnit')?.value || 'day');
        return Number.isFinite(min) && Number.isFinite(max) && min > 0 && max >= min
            ? { unit, min, max }
            : null;
    }

    function setAllowedPeriodRangeControls(range) {
        const minInput = $('labAllowedPeriodMin');
        const maxInput = $('labAllowedPeriodMax');
        const unitSelect = $('labAllowedPeriodUnit');
        if (!minInput || !maxInput || !unitSelect || !range) return;

        unitSelect.value = normalizePeriodUnit(range.unit);
        normalizeAllowedPeriodRange({ min: range.min, max: range.max });
    }

})();
