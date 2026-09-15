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
    const publisherSchedulingFeature = window.LabPublisherSchedulingFeature;
    if (!publisherSchedulingFeature) {
        throw new Error('LabPublisherSchedulingFeature must load before lab-publisher.js');
    }
    const publisherTermsFeature = window.LabPublisherTermsFeature;
    if (!publisherTermsFeature) {
        throw new Error('LabPublisherTermsFeature must load before lab-publisher.js');
    }
    const publisherFmuMetadataFeature = window.LabPublisherFmuMetadataFeature;
    if (!publisherFmuMetadataFeature) {
        throw new Error('LabPublisherFmuMetadataFeature must load before lab-publisher.js');
    }

    const state = {
        status: null,
        hosts: [],
        guacamole: [],
        fmus: [],
        imageMode: 'link',
        docMode: 'link',
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
    const expandAllowedDurations = publisherValues.expandAllowedDurations;
    const buildPeriodRules = publisherValues.buildPeriodRules;
    const deriveAllowedPeriodRange = publisherValues.deriveAllowedPeriodRange;
    const resolveLabDisplayName = publisherValues.resolveLabDisplayName;
    const metadataAttributes = publisherValues.metadataAttributes;
    const normalizeTraitType = publisherValues.normalizeTraitType;
    const normalizeArray = publisherValues.normalizeArray;
    const splitCsv = publisherValues.splitCsv;
    const mergeMediaUrls = publisherValues.mergeMediaUrls;
    const dateInputToUnix = publisherValues.dateInputToUnix;
    const unixToDateInput = publisherValues.unixToDateInput;
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
    let schedulingController;
    let termsController;
    let fmuMetadataController;

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
            resetFmuDescribeFields: (...args) => fmuMetadataController.reset(...args),
            autoDetectFmuMetadata: () => fmuMetadataController.autoDetect(),
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

        schedulingController = publisherSchedulingFeature.createController({
            documentImpl: document,
            normalizePricingUnit,
            normalizePeriodUnit: publisherValues.normalizePeriodUnit,
            resolveSupportedTimezones: publisherValues.resolveSupportedTimezones,
            resolveBrowserTimezone: publisherValues.resolveBrowserTimezone,
        });

        termsController = publisherTermsFeature.createController({
            documentImpl: document,
            fetchImpl: fetch,
            guessVersionFromUrl: publisherValues.guessVersionFromUrl,
        });
        termsController.bind();

        fmuMetadataController = publisherFmuMetadataFeature.createController({
            documentImpl: document,
            fetchFmuMetadata,
            fetchImpl: fetch,
            renderModelVariables: renderModelVariablesTable,
            escapeHtml,
        });

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
        images.addEventListener('change', () => void assetsController.upload(images.files, 'images'));
        docs.addEventListener('change', () => void assetsController.upload(docs.files, 'docs'));
        imageChoose.addEventListener('click', () => images.click());
        docChoose.addEventListener('click', () => docs.click());

        resourceFeatureController.syncSetupMode();
        resourceFeatureController.syncTypeFields();
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
        schedulingController.initialize();
        setupMediaMode('images', 'link');
        setupMediaMode('docs', 'link');
        $('labImageMode').querySelectorAll('button').forEach(button => {
            button.addEventListener('click', () => setupMediaMode('images', button.dataset.mode));
        });
        $('labDocMode').querySelectorAll('button').forEach(button => {
            button.addEventListener('click', () => setupMediaMode('docs', button.dataset.mode));
        });
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
        const bookingMode = schedulingController.getDerivedBookingMode();
        const timeSlots = splitCsv($('labTimeSlots').value).map(Number).filter(Number.isFinite);
        const allowedDurationRange = bookingMode === 'calendar-period'
            ? schedulingController.getSelectedAllowedPeriodRange()
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
        const termsOfUse = sanitizeTermsOfUse(termsController.getState());
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
            modelVariables: fmuMetadataController.getModelVariables(),
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
        const bookingMode = schedulingController.getDerivedBookingMode();
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
        if (bookingMode === 'calendar-period' && !expandAllowedDurations(schedulingController.getSelectedAllowedPeriodRange()).length) {
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

    function resolveStateLabDisplayName(labId) {
        const lab = state.labs.find(item => String(item?.labId) === String(labId));
        return resolveLabDisplayName(lab || { labId });
    }

    async function enterEditMode(lab) {
        state.editingLabId = String(lab.labId);
        fmuMetadataController.reset(false);
        applyLabBaseFields(lab);
        await applyLabMetadata(lab);
        captureOriginalEditPrice(lab);
        resourceFeatureController.syncSetupMode();
        resourceFeatureController.syncTypeFields();
        schedulingController.syncBookingModeFields();
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
            schedulingController.setAllowedPeriodRangeControls(metadata.allowedDurationRange);
        }
        if (Array.isArray(metadata?.allowedDurations) && metadata.allowedDurations.length) {
            schedulingController.setAllowedPeriodRangeControls(deriveAllowedPeriodRange(metadata.allowedDurations));
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
            if (range) schedulingController.setAllowedPeriodRangeControls(range);
        });
        setAttributeValue(attributes, 'allowedDurationRange', value => {
            if (value) schedulingController.setAllowedPeriodRangeControls(value);
        });
        schedulingController.syncBookingModeFields();
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
        setAttributeValue(attributes, 'termsOfUse', value => termsController.hydrate(value));
        setAttributeValue(attributes, 'timezone', value => {
            if (value) $('labTimezone').value = value;
        });
        setAttributeValue(attributes, 'fmuFileName', value => {
            if (value) $('labFmuFileName').value = value;
        });
        setAttributeValue(attributes, 'fmiVersion', value => fmuMetadataController.hydrate({ fmiVersion: value }));
        setAttributeValue(attributes, 'simulationType', value => fmuMetadataController.hydrate({ simulationType: value }));
        setAttributeValue(attributes, 'defaultStartTime', value => fmuMetadataController.hydrate({ defaultStartTime: value }));
        setAttributeValue(attributes, 'defaultStopTime', value => fmuMetadataController.hydrate({ defaultStopTime: value }));
        setAttributeValue(attributes, 'defaultStepSize', value => fmuMetadataController.hydrate({ defaultStepSize: value }));
        setAttributeValue(attributes, 'modelVariables', value => fmuMetadataController.hydrate({ modelVariables: Array.isArray(value) ? value : [] }));
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
        availabilityController.reset();
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
        termsController.reset();
        setValue('labFmuFileName', '');
        setValue('labImageUrls', '');
        setValue('labDocUrls', '');
        setValue('labImages', '');
        setValue('labDocs', '');
        setChecked('labEducationalProgramLinked', false);
        setChecked('labDemoEnabled', false);
        setContentId('');
        schedulingController.reset();
        resourceFeatureController.renderOptions();
        setupMediaMode('images', 'link');
        setupMediaMode('docs', 'link');
        fmuMetadataController.reset(false);
        resourceFeatureController.syncSetupMode();
        resourceFeatureController.syncTypeFields();
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

})();
