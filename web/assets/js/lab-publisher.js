(function () {
    const state = {
        status: null,
        hosts: [],
        guacamole: [],
        fmus: [],
        uploadedImages: [],
        uploadedDocs: [],
        selectedCategories: [],
        availableDays: ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY'],
        unavailableWindows: [],
        modelVariables: [],
        imageMode: 'link',
        docMode: 'link',
        fmuDescribeController: null,
        termsController: null,
    };

    const CREDIT_DECIMALS = 5;
    const RAW_PER_CREDIT = 10n ** BigInt(CREDIT_DECIMALS);
    const SECONDS_PER_HOUR = 3600n;
    const DISPLAY_PRICE_DECIMALS = 1;
    const RESOURCE_TYPES = { LAB: 'lab', FMU: 'fmu' };
    const WEEKDAY_OPTIONS = [
        { value: 'MONDAY', label: 'Mon' },
        { value: 'TUESDAY', label: 'Tue' },
        { value: 'WEDNESDAY', label: 'Wed' },
        { value: 'THURSDAY', label: 'Thu' },
        { value: 'FRIDAY', label: 'Fri' },
        { value: 'SATURDAY', label: 'Sat' },
        { value: 'SUNDAY', label: 'Sun' },
    ];
    const DEFAULT_TIMEZONES = [
        'UTC',
        'Europe/Madrid',
        'Europe/London',
        'Europe/Paris',
        'Europe/Berlin',
        'Europe/Rome',
        'Europe/Amsterdam',
        'America/New_York',
        'America/Chicago',
        'America/Denver',
        'America/Los_Angeles',
        'America/Mexico_City',
        'America/Bogota',
        'America/Sao_Paulo',
        'America/Argentina/Buenos_Aires',
        'Africa/Johannesburg',
        'Asia/Tokyo',
        'Asia/Seoul',
        'Asia/Shanghai',
        'Asia/Singapore',
        'Asia/Kolkata',
        'Australia/Sydney',
        'Pacific/Auckland',
    ];

    function normalizeConnectionUsers(connection) {
        const rawUsers = Array.isArray(connection?.users) ? connection.users : [];
        return rawUsers
            .map(user => {
                if (typeof user === 'string') return user.trim();
                if (user && typeof user === 'object') return String(user.username || user.name || '').trim();
                return '';
            })
            .filter(Boolean);
    }

    function resolveConnectionAccessKey(connection) {
        const users = normalizeConnectionUsers(connection);
        const nonDemoUser = users.find(user => user.toLowerCase() !== 'demo');
        return nonDemoUser || users[0] || (connection?.id ? String(connection.id) : (connection?.name || ''));
    }

    function formatConnectionUsers(connection) {
        const users = normalizeConnectionUsers(connection);
        return users.length ? ` - ${users.join(', ')}` : '';
    }
    const LAB_CATEGORIES_GROUPED = {
        'Mathematics & Computer Science': [
            'Mathematics',
            'Statistics & Probability',
            'Computer Science',
            'Artificial Intelligence & Machine Learning',
            'Data Science',
            'Cybersecurity',
            'Software Engineering',
        ],
        'Physical Sciences': [
            'Physics',
            'Nuclear Physics',
            'Particle Physics',
            'Astronomy & Astrophysics',
            'Optics & Photonics',
            'Condensed Matter Physics',
        ],
        'Chemical Sciences': [
            'Chemistry',
            'Organic Chemistry',
            'Inorganic Chemistry',
            'Physical Chemistry',
            'Analytical Chemistry',
            'Biochemistry',
            'Pharmaceutical Chemistry',
        ],
        'Earth & Space Sciences': [
            'Geology',
            'Geophysics',
            'Meteorology',
            'Oceanography',
            'Environmental Sciences',
            'Climate Science',
        ],
        'Biological Sciences': [
            'Biology',
            'Molecular Biology',
            'Cell Biology',
            'Genetics',
            'Microbiology',
            'Botany',
            'Zoology',
            'Ecology',
            'Marine Biology',
            'Neuroscience',
            'Biotechnology',
        ],
        'Engineering & Technology': [
            'Civil Engineering',
            'Mechanical Engineering',
            'Electrical Engineering',
            'Electronic Engineering',
            'Telecommunications Engineering',
            'Chemical Engineering',
            'Materials Engineering',
            'Aerospace Engineering',
            'Robotics',
            'Automation & Control Systems',
            'Nanotechnology',
            'Biomedical Engineering',
        ],
        'Medical & Health Sciences': [
            'Medicine',
            'Clinical Medicine',
            'Pharmacology',
            'Toxicology',
            'Pathology',
            'Immunology',
            'Public Health',
            'Nursing',
            'Medical Imaging',
            'Laboratory Medicine',
        ],
        'Agricultural & Veterinary Sciences': [
            'Agriculture',
            'Animal Science',
            'Veterinary Medicine',
            'Forestry',
            'Fisheries',
            'Soil Science',
            'Agricultural Engineering',
        ],
        'Social Sciences': [
            'Psychology',
            'Experimental Psychology',
            'Cognitive Science',
            'Economics',
            'Experimental Economics',
            'Sociology',
            'Political Science',
            'Anthropology',
        ],
        'Humanities': [
            'Linguistics',
            'Computational Linguistics',
            'Digital Humanities',
            'Archaeology',
        ],
        'Multidisciplinary & Other': [
            'Environmental Engineering',
            'Energy Engineering',
            'Renewable Energy',
            'Food Science & Technology',
            'Quality Control',
            'Metrology',
            'Other',
        ],
    };

    const $ = (id) => document.getElementById(id);

    document.addEventListener('DOMContentLoaded', () => {
        const refresh = $('labPublisherRefreshBtn');
        const submit = $('labPublisherSubmitBtn');
        const resourceType = $('labResourceType');
        const resourceSelect = $('labDetectedResource');
        const setupMode = $('labSetupMode');
        const images = $('labImages');
        const docs = $('labDocs');
        const imageChoose = $('labImagesChooseBtn');
        const docChoose = $('labDocsChooseBtn');
        const assetList = $('labAssetList');
        const addWindow = $('labAddUnavailableWindow');
        const termsUrl = $('labTermsUrl');
        const fmuAutoDetect = $('labFmuAutoDetectBtn');
        const categorySelect = $('labCategorySelect');
        const fmuFileName = $('labFmuFileName');

        if (!refresh || !submit) return;

        initMarketplaceFields();
        refresh.addEventListener('click', loadPublisherData);
        submit.addEventListener('click', publishLab);
        resourceType.addEventListener('change', () => {
            renderResourceOptions();
            syncResourceTypeFields();
        });
        resourceSelect.addEventListener('change', applySelectedResource);
        setupMode.addEventListener('change', syncSetupMode);
        images.addEventListener('change', () => uploadAssets(images.files, 'images'));
        docs.addEventListener('change', () => uploadAssets(docs.files, 'docs'));
        imageChoose.addEventListener('click', () => images.click());
        docChoose.addEventListener('click', () => docs.click());
        if (assetList) assetList.addEventListener('click', handleAssetListClick);
        addWindow.addEventListener('click', addUnavailableWindow);
        termsUrl.addEventListener('blur', autoFetchTermsMetadata);
        fmuAutoDetect.addEventListener('click', autoDetectFmuMetadata);
        fmuFileName.addEventListener('input', () => {
            if ($('labResourceType').value === '1') $('labAccessKey').value = fmuFileName.value.trim();
            resetFmuDescribeFields(false);
        });
        categorySelect.addEventListener('click', toggleCategoryMenu);
        categorySelect.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                toggleCategoryMenu();
            }
            if (event.key === 'Escape') closeCategoryMenu();
        });
        document.addEventListener('click', (event) => {
            const menu = $('labCategoryMenu');
            if (!categorySelect.contains(event.target) && !menu.contains(event.target)) {
                closeCategoryMenu();
            }
        });

        syncSetupMode();
        syncResourceTypeFields();
        loadPublisherData();
    });

    function initMarketplaceFields() {
        populateTimezoneOptions();
        renderCategoryMenu();
        renderCategoryChips();
        renderDayToggles();
        renderUnavailableWindows();
        setupMediaMode('images', 'link');
        setupMediaMode('docs', 'link');
        $('labImageMode').querySelectorAll('button').forEach(button => {
            button.addEventListener('click', () => setupMediaMode('images', button.dataset.mode));
        });
        $('labDocMode').querySelectorAll('button').forEach(button => {
            button.addEventListener('click', () => setupMediaMode('docs', button.dataset.mode));
        });
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

    function resolveSupportedTimezones() {
        if (typeof Intl !== 'undefined' && typeof Intl.supportedValuesOf === 'function') {
            try {
                const values = Intl.supportedValuesOf('timeZone');
                if (Array.isArray(values) && values.length > 0) return values;
            } catch {
                // Fall through to defaults.
            }
        }
        return DEFAULT_TIMEZONES;
    }

    function resolveBrowserTimezone() {
        if (typeof Intl !== 'undefined' && typeof Intl.DateTimeFormat === 'function') {
            try {
                const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
                if (timezone && typeof timezone === 'string') return timezone;
            } catch {
                // Fall through to UTC.
            }
        }
        return 'UTC';
    }

    async function loadPublisherData() {
        setStatus('Loading provider status...', false);
        try {
            const [status, hosts, labs] = await Promise.all([
                fetchJson('/lab-admin/status'),
                fetchJson('/ops/api/hosts').catch(() => null),
                fetchJson('/lab-admin/labs').catch(() => null),
            ]);
            state.status = status;
            state.hosts = hosts?.hosts || [];
            state.guacamole = [
                ...(hosts?.guacamoleUnmatched || []),
                ...state.hosts.flatMap(host => host?.guacamole?.connections || []),
            ];
            state.fmus = status?.fmuInventory || [];
            renderResourceOptions();
            renderLabs(labs?.labs || []);
            const providerLabel = status?.isProvider
                ? `Provider wallet: ${status.providerAddress}`
                : 'This Gateway wallet is not registered as provider yet.';
            setStatus(providerLabel, !status?.isProvider);
        } catch (err) {
            setStatus(err.message || 'Unable to load Lab Publisher data', true);
        }
    }

    function renderResourceOptions() {
        const select = $('labDetectedResource');
        const type = $('labResourceType').value;
        select.innerHTML = '<option value="">Manual entry</option>';
        const resources = type === '1' ? state.fmus : uniqueGuacamole();
        resources.forEach((resource, index) => {
            const option = document.createElement('option');
            option.value = String(index);
            option.textContent = type === '1'
                ? `${resource.fileName} (${resource.relativePath || 'fmu-data'})`
                : `${resource.name || 'Connection'} #${resource.id} ${resource.hostname ? '- ' + resource.hostname : ''}${formatConnectionUsers(resource)}`;
            select.appendChild(option);
        });
        applySelectedResource();
    }

    function uniqueGuacamole() {
        const seen = new Set();
        return state.guacamole.filter(conn => {
            const key = String(conn.id);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }

    function renderCategoryMenu() {
        const menu = $('labCategoryMenu');
        menu.innerHTML = Object.entries(LAB_CATEGORIES_GROUPED).map(([groupName, categories]) => `
            <div class="multi-select-group">
                <div class="multi-select-group-title">${escapeHtml(groupName)}</div>
                ${categories.map(category => `
                    <label class="multi-select-option">
                        <input type="checkbox" value="${escapeAttr(category)}">
                        <span>${escapeHtml(category)}</span>
                    </label>
                `).join('')}
            </div>
        `).join('');
        menu.querySelectorAll('input[type="checkbox"]').forEach(input => {
            input.addEventListener('change', () => toggleCategory(input.value));
        });
    }

    function toggleCategoryMenu() {
        const select = $('labCategorySelect');
        const menu = $('labCategoryMenu');
        const open = !menu.classList.contains('open');
        menu.classList.toggle('open', open);
        select.classList.toggle('open', open);
        select.setAttribute('aria-expanded', String(open));
        if (open) {
            const rect = select.getBoundingClientRect();
            menu.style.left = `${rect.left}px`;
            menu.style.top = `${rect.bottom + 4}px`;
        }
    }

    function closeCategoryMenu() {
        $('labCategoryMenu').classList.remove('open');
        $('labCategorySelect').classList.remove('open');
        $('labCategorySelect').setAttribute('aria-expanded', 'false');
    }

    function toggleCategory(category) {
        state.selectedCategories = state.selectedCategories.includes(category)
            ? state.selectedCategories.filter(item => item !== category)
            : [...state.selectedCategories, category];
        renderCategoryChips();
    }

    function renderCategoryChips() {
        const chips = $('labCategoryChips');
        const menu = $('labCategoryMenu');
        chips.innerHTML = state.selectedCategories.length
            ? state.selectedCategories.map(category => `
                <span class="chip">
                    ${escapeHtml(category)}
                    <button type="button" data-category="${escapeAttr(category)}" aria-label="Remove ${escapeAttr(category)}">&times;</button>
                </span>
            `).join('')
            : '<span class="placeholder">Select one or more categories...</span>';
        chips.querySelectorAll('button[data-category]').forEach(button => {
            button.addEventListener('click', (event) => {
                event.stopPropagation();
                toggleCategory(button.dataset.category);
            });
        });
        menu.querySelectorAll('input[type="checkbox"]').forEach(input => {
            input.checked = state.selectedCategories.includes(input.value);
        });
    }

    function renderDayToggles() {
        const target = $('labAvailableDays');
        target.innerHTML = WEEKDAY_OPTIONS.map(day => `
            <button type="button" data-day="${day.value}" class="${state.availableDays.includes(day.value) ? 'active' : ''}">
                ${day.label}
            </button>
        `).join('');
        target.querySelectorAll('button[data-day]').forEach(button => {
            button.addEventListener('click', () => {
                const day = button.dataset.day;
                state.availableDays = state.availableDays.includes(day)
                    ? state.availableDays.filter(item => item !== day)
                    : [...state.availableDays, day];
                renderDayToggles();
            });
        });
    }

    function addUnavailableWindow() {
        state.unavailableWindows.push({
            clientId: cryptoRandomId(),
            startUnix: null,
            endUnix: null,
            reason: '',
        });
        renderUnavailableWindows();
    }

    function renderUnavailableWindows() {
        const target = $('labUnavailableWindows');
        target.innerHTML = state.unavailableWindows.length
            ? state.unavailableWindows.map((window, index) => `
                <div class="unavailable-window" data-index="${index}">
                    <div class="form-grid">
                        <label class="field">
                            <span>Starts</span>
                            <input type="datetime-local" data-field="startUnix" value="${escapeAttr(toDatetimeLocal(window.startUnix))}">
                        </label>
                        <label class="field">
                            <span>Ends</span>
                            <input type="datetime-local" data-field="endUnix" value="${escapeAttr(toDatetimeLocal(window.endUnix))}">
                        </label>
                        <label class="field">
                            <span>Reason</span>
                            <input type="text" data-field="reason" placeholder="Reason (e.g., Maintenance, Calibration)" value="${escapeAttr(window.reason || '')}">
                        </label>
                        <label class="field action-field">
                            <span>Remove</span>
                            <button class="mini-btn danger" type="button" data-remove-window="${index}">
                                <i class="fas fa-trash"></i> Remove
                            </button>
                        </label>
                    </div>
                </div>
            `).join('')
            : '<div class="hint">No unavailable windows configured.</div>';

        target.querySelectorAll('.unavailable-window').forEach(row => {
            const index = Number(row.dataset.index);
            row.querySelectorAll('[data-field]').forEach(input => {
                input.addEventListener('change', () => updateUnavailableWindow(index, input.dataset.field, input.value));
                input.addEventListener('input', () => {
                    if (input.dataset.field === 'reason') updateUnavailableWindow(index, input.dataset.field, input.value);
                });
            });
        });
        target.querySelectorAll('[data-remove-window]').forEach(button => {
            button.addEventListener('click', () => {
                state.unavailableWindows.splice(Number(button.dataset.removeWindow), 1);
                renderUnavailableWindows();
            });
        });
    }

    function updateUnavailableWindow(index, field, value) {
        const current = state.unavailableWindows[index];
        if (!current) return;
        if (field === 'startUnix' || field === 'endUnix') {
            current[field] = value ? Math.floor(new Date(value).getTime() / 1000) : null;
            return;
        }
        current[field] = value;
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
        linkInput.style.display = mode === 'link' ? '' : 'none';
        chooseBtn.style.display = mode === 'upload' ? '' : 'none';
    }

    function applySelectedResource() {
        const type = $('labResourceType').value;
        const index = $('labDetectedResource').value;
        const preview = $('labResourcePreview');
        if (index === '') {
            preview.textContent = 'No resource selected.';
            return;
        }
        if (type === '1') {
            const fmu = state.fmus[Number(index)];
            $('labAccessURI').value = state.status?.recommendedFmuAccessURI || `${window.location.origin}/fmu`;
            $('labAccessKey').value = fmu?.fileName || '';
            $('labFmuFileName').value = fmu?.fileName || '';
            if (!$('labName').value) $('labName').value = (fmu?.fileName || '').replace(/\.fmu$/i, '');
            preview.textContent = `FMU: ${fmu?.relativePath || fmu?.fileName || 'selected'}`;
            $('labMaxConcurrentUsers').value = Math.max(2, Number($('labMaxConcurrentUsers').value) || 2);
            syncResourceTypeFields();
            return;
        }

        const conn = uniqueGuacamole()[Number(index)];
        $('labAccessURI').value = state.status?.recommendedRemoteAccessURI || `${window.location.origin}/guacamole`;
        $('labAccessKey').value = resolveConnectionAccessKey(conn);
        if (!$('labName').value) $('labName').value = conn?.name || '';
        const accessUser = resolveConnectionAccessKey(conn);
        preview.textContent = `Guacamole: ${conn?.name || 'Connection'} (${conn?.hostname || 'no host'}) - access user: ${accessUser || 'n/a'}`;
        $('labMaxConcurrentUsers').value = 1;
        syncResourceTypeFields();
    }

    function syncSetupMode() {
        const quick = $('labSetupMode').value === 'quick';
        $('fullMetadataPanel').style.display = quick ? 'none' : '';
        $('quickMetadataField').style.display = quick ? '' : 'none';
    }

    function syncResourceTypeFields() {
        const isFmu = $('labResourceType').value === '1';
        $('fmuConfigTitle').style.display = isFmu ? '' : 'none';
        $('fmuConfigPanel').style.display = isFmu ? '' : 'none';
        if (isFmu && !$('labFmuFileName').value.trim() && $('labAccessKey').value.trim().toLowerCase().endsWith('.fmu')) {
            $('labFmuFileName').value = $('labAccessKey').value.trim();
        }
        if (isFmu && $('labFmuFileName').value.trim()) {
            $('labAccessKey').value = $('labFmuFileName').value.trim();
        }
    }

    async function uploadAssets(files, kind) {
        const list = Array.from(files || []);
        if (!list.length) return;
        const contentId = ensureContentId();
        try {
            for (const file of list) {
                const form = new FormData();
                form.append('contentId', contentId);
                form.append('kind', kind);
                form.append('file', file);
                const result = await fetchJson('/lab-admin/assets', { method: 'POST', body: form });
                if (kind === 'images') state.uploadedImages.push(result.url);
                else state.uploadedDocs.push(result.url);
            }
        } catch (err) {
            setStatus(err.message || 'Upload failed', true);
        } finally {
            const input = $(kind === 'images' ? 'labImages' : 'labDocs');
            if (input) input.value = '';
            renderAssets();
        }
    }

    async function publishLab() {
        try {
            const setupMode = $('labSetupMode').value;
            const payload = {
                setupMode,
                listImmediately: $('labListImmediately').value === 'true',
                price: convertHourlyCreditsToRawPerSecond($('labPrice').value || '0').toString(),
                accessURI: $('labAccessURI').value.trim(),
                accessKey: $('labAccessKey').value.trim(),
                resourceType: Number($('labResourceType').value),
            };
            if (setupMode === 'quick') {
                payload.metadataUrl = $('labMetadataUrl').value.trim();
            } else {
                payload.metadata = buildMetadata();
            }

            $('labPublisherSubmitBtn').disabled = true;
            setStatus('Publishing lab on-chain...', false);
            const result = await fetchJson('/lab-admin/labs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            setStatus(`Published. Tx: ${result.transactionHash || 'pending'}${result.labId ? ' Lab #' + result.labId : ''}`, false);
            await loadPublisherData();
        } catch (err) {
            setStatus(err.message || 'Publish failed', true);
        } finally {
            $('labPublisherSubmitBtn').disabled = false;
        }
    }

    function buildMetadata() {
        syncResourceTypeFields();
        validateMarketplaceFields();
        const imageUrls = state.imageMode === 'link'
            ? splitCsv($('labImageUrls').value)
            : [...state.uploadedImages];
        const docs = state.docMode === 'link'
            ? splitCsv($('labDocUrls').value)
            : [...state.uploadedDocs];
        const categories = [...state.selectedCategories];
        const keywords = splitCsv($('labKeywords').value);
        const resourceType = $('labResourceType').value === '1' ? RESOURCE_TYPES.FMU : RESOURCE_TYPES.LAB;
        const fmuFileName = $('labFmuFileName').value.trim();
        const unavailableWindows = sanitizeUnavailableWindows(state.unavailableWindows);
        const termsOfUse = sanitizeTermsOfUse({
            url: $('labTermsUrl').value.trim(),
            version: $('labTermsVersion').value.trim(),
            effectiveDate: $('labTermsEffectiveDate').value.trim(),
            sha256: $('labTermsSha256').value.trim(),
        });
        const attributes = [
            { trait_type: 'category', value: categories },
            { trait_type: 'keywords', value: keywords },
            { trait_type: 'timeSlots', value: splitCsv($('labTimeSlots').value).map(Number).filter(Number.isFinite) },
            { trait_type: 'opens', value: dateInputToUnix($('labOpens').value) },
            { trait_type: 'closes', value: dateInputToUnix($('labCloses').value) },
            { trait_type: 'additionalImages', value: imageUrls.slice(1) },
            { trait_type: 'docs', value: docs },
            { trait_type: 'availableDays', value: [...state.availableDays] },
            { trait_type: 'availableHours', value: sanitizeAvailableHours($('labAvailableHoursStart').value, $('labAvailableHoursEnd').value) },
            { trait_type: 'maxConcurrentUsers', value: Number($('labMaxConcurrentUsers').value) || 1 },
            { trait_type: 'unavailableWindows', value: unavailableWindows },
            { trait_type: 'termsOfUse', value: termsOfUse },
            { trait_type: 'timezone', value: $('labTimezone').value.trim() || '' },
            { trait_type: 'resourceType', value: resourceType },
            ...(resourceType === RESOURCE_TYPES.FMU && fmuFileName ? [{ trait_type: 'fmuFileName', value: fmuFileName }] : []),
            ...optionalAttribute('fmiVersion', $('labFmiVersion').value.trim()),
            ...optionalAttribute('simulationType', $('labSimulationType').value.trim()),
            ...optionalAttribute('modelVariables', state.modelVariables.length ? state.modelVariables : null),
            ...optionalNumberAttribute('defaultStartTime', $('labDefaultStartTime').value),
            ...optionalNumberAttribute('defaultStopTime', $('labDefaultStopTime').value),
            ...optionalNumberAttribute('defaultStepSize', $('labDefaultStepSize').value),
        ];
        return {
            contentId: ensureContentId(),
            name: $('labName').value.trim(),
            description: $('labDescription').value.trim(),
            image: imageUrls[0] || '',
            images: imageUrls,
            category: categories,
            keywords,
            docs,
            demoEnabled: $('labDemoEnabled').checked === true,
            attributes,
        };
    }

    function validateMarketplaceFields() {
        const required = [
            ['Name', $('labName').value.trim()],
            ['Description', $('labDescription').value.trim()],
            ['Price per hour', $('labPrice').value.trim()],
            ['Access URI', $('labAccessURI').value.trim()],
            ['Timezone', $('labTimezone').value.trim()],
            ['Daily Start Time', $('labAvailableHoursStart').value.trim()],
            ['Daily End Time', $('labAvailableHoursEnd').value.trim()],
        ];
        const missing = required.find(([, value]) => !value);
        if (missing) throw new Error(`${missing[0]} is required`);
        if (!state.selectedCategories.length) throw new Error('Category is required');
        if (!state.availableDays.length) throw new Error('Select at least one available day');
        if (!splitCsv($('labTimeSlots').value).map(Number).some(Number.isFinite)) {
            throw new Error('Time Slots must include at least one duration in minutes');
        }
        const opens = dateInputToUnix($('labOpens').value);
        const closes = dateInputToUnix($('labCloses').value);
        if (!opens) throw new Error('Opens is required');
        if (!closes) throw new Error('Closes is required');
        if (closes < opens) throw new Error('Closes must be after or equal to Opens');
        if ($('labResourceType').value === '1') {
            const fmuFileName = $('labFmuFileName').value.trim();
            if (!fmuFileName) throw new Error('FMU File Name is required');
            if (!/^[A-Za-z0-9._/-]+\.fmu$/i.test(fmuFileName)) {
                throw new Error('FMU File Name must end with .fmu and contain only valid characters');
            }
        } else if (!$('labAccessKey').value.trim()) {
            throw new Error('Access Key is required');
        }
    }

    function optionalAttribute(traitType, value) {
        return value === null || value === undefined || value === ''
            ? []
            : [{ trait_type: traitType, value }];
    }

    function optionalNumberAttribute(traitType, value) {
        if (value === null || value === undefined || value === '') return [];
        const parsed = Number(value);
        return Number.isFinite(parsed) ? [{ trait_type: traitType, value: parsed }] : [];
    }

    function dateInputToUnix(value) {
        if (!value) return null;
        const parsed = new Date(`${value}T00:00:00`);
        return Number.isFinite(parsed.getTime()) ? Math.floor(parsed.getTime() / 1000) : null;
    }

    function sanitizeAvailableHours(start, end) {
        const safeStart = sanitizeTime(start);
        const safeEnd = sanitizeTime(end);
        return safeStart && safeEnd ? { start: safeStart, end: safeEnd } : {};
    }

    function sanitizeTime(value) {
        const text = String(value || '').trim();
        if (!/^\d{1,2}:\d{2}$/.test(text)) return '';
        const [hours, minutes] = text.split(':').map(Number);
        if (hours > 23 || minutes > 59) return '';
        return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
    }

    function sanitizeUnavailableWindows(windows) {
        return (Array.isArray(windows) ? windows : [])
            .map(window => {
                const startUnix = Number(window?.startUnix || 0);
                const endUnix = Number(window?.endUnix || 0);
                const reason = String(window?.reason || '').trim();
                if (!Number.isFinite(startUnix) || !Number.isFinite(endUnix) || startUnix <= 0 || endUnix <= 0) return null;
                if (!reason || startUnix >= endUnix) return null;
                return {
                    startUnix: Math.floor(startUnix),
                    endUnix: Math.floor(endUnix),
                    reason,
                };
            })
            .filter(Boolean);
    }

    function sanitizeTermsOfUse(terms) {
        const result = {};
        if (terms.url) result.url = terms.url;
        if (terms.version) result.version = terms.version;
        if (terms.effectiveDate) result.effectiveDate = terms.effectiveDate;
        if (terms.sha256) result.sha256 = terms.sha256.toLowerCase();
        return result;
    }

    function ensureContentId() {
        const el = $('labContentId');
        if (!el.value.trim()) {
            el.value = `lab-${Date.now().toString(36)}`;
        }
        return el.value.trim();
    }

    function renderAssets() {
        const target = $('labAssetList');
        const entries = [
            ...state.uploadedImages.map(url => ({ kind: 'images', label: 'Image', url })),
            ...state.uploadedDocs.map(url => ({ kind: 'docs', label: 'Doc', url })),
        ];
        target.innerHTML = entries.length
            ? entries.map(entry => `
                <div class="asset-row">
                    <span>${escapeHtml(entry.label)}</span>
                    <a href="${escapeAttr(entry.url)}" target="_blank" rel="noopener">${escapeHtml(entry.url)}</a>
                    <button class="mini-btn danger asset-delete-btn" type="button" data-kind="${escapeAttr(entry.kind)}" data-url="${escapeAttr(entry.url)}" title="Delete ${escapeAttr(entry.label)}" aria-label="Delete ${escapeAttr(entry.label)}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `).join('')
            : '';
    }

    async function handleAssetListClick(event) {
        const button = event.target.closest('button[data-url][data-kind]');
        if (!button) return;
        const url = button.dataset.url || '';
        const kind = button.dataset.kind || '';
        button.disabled = true;
        try {
            await fetchJson('/lab-admin/assets', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: url }),
            });
            const stateKey = kind === 'images' ? 'uploadedImages' : 'uploadedDocs';
            state[stateKey] = state[stateKey].filter(item => item !== url);
            setStatus('Asset deleted.', false);
        } catch (err) {
            setStatus(err.message || 'Delete failed', true);
        } finally {
            renderAssets();
        }
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
        $('labFmuAutoDetectBtn').disabled = true;
        try {
            const tokenResponse = await fetch('/lab-admin/fmu/provider-describe-token', {
                method: 'POST',
                credentials: 'include',
                signal: controller.signal,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ fmuFileName }),
            });
            const tokenBody = await tokenResponse.json().catch(() => ({}));
            if (!tokenResponse.ok || !tokenBody.token) {
                throw new Error(tokenBody.error || `Describe token request returned HTTP ${tokenResponse.status}`);
            }
            const describeUrl = `${gatewayUrl.replace(/\/+$/, '')}/api/v1/simulations/describe?fmuFileName=${encodeURIComponent(fmuFileName)}`;
            const describeResponse = await fetch(describeUrl, {
                signal: controller.signal,
                headers: { Authorization: `Bearer ${tokenBody.token}` },
            });
            const metadata = await describeResponse.json().catch(() => ({}));
            if (!describeResponse.ok) {
                throw new Error(metadata.error || `Gateway returned HTTP ${describeResponse.status}`);
            }
            applyFmuMetadata(metadata);
            status.textContent = 'FMU metadata loaded successfully.';
        } catch (err) {
            if (err.name === 'AbortError') return;
            status.textContent = `Auto-detect failed: ${err.message}`;
        } finally {
            $('labFmuAutoDetectBtn').disabled = false;
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
        state.modelVariables = Array.isArray(metadata.modelVariables) ? metadata.modelVariables : [];
        renderModelVariables();
    }

    function renderModelVariables() {
        const wrap = $('labModelVariablesWrap');
        const body = $('labModelVariables');
        wrap.style.display = state.modelVariables.length ? '' : 'none';
        body.innerHTML = state.modelVariables.map(variable => `
            <tr>
                <td>${escapeHtml(variable.name || '')}</td>
                <td>${escapeHtml(variable.causality || '')}</td>
                <td>${escapeHtml(variable.type || '')}</td>
                <td>${escapeHtml(variable.unit || '')}</td>
                <td>${escapeHtml(variable.start ?? '')}</td>
            </tr>
        `).join('');
    }

    function renderLabs(labs) {
        const target = $('labPublisherList');
        if (!labs.length) {
            target.classList.add('empty');
            target.textContent = 'No labs published by this provider wallet yet.';
            return;
        }
        target.classList.remove('empty');
        target.innerHTML = labs.map(lab => `
            <div class="lab-row">
                <div>
                    <div class="item-title">Lab #${escapeHtml(lab.labId)} ${lab.resourceType === 1 ? 'FMU' : 'Remote'}</div>
                    <div class="item-meta">${escapeHtml(lab.accessKey || '')} · ${escapeHtml(lab.uri || '')}</div>
                </div>
                <div class="item-meta">${escapeHtml(formatRawPricePerHour(lab.price || '0'))} credits/hour</div>
            </div>
        `).join('');
    }

    async function fetchJson(url, options) {
        const res = await fetch(url, { credentials: 'include', ...(options || {}) });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(body.error || body.detail || `HTTP ${res.status}`);
        }
        return body;
    }

    function setStatus(message, isError) {
        const el = $('labPublisherStatus');
        if (!el) return;
        el.textContent = message;
        el.classList.toggle('error', !!isError);
    }

    function splitCsv(value) {
        return String(value || '').split(',').map(v => v.trim()).filter(Boolean);
    }

    function cryptoRandomId() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
        return `${Date.now()}-${Math.random()}`;
    }

    function toDatetimeLocal(unixSeconds) {
        const timestamp = Number(unixSeconds);
        if (!Number.isFinite(timestamp) || timestamp <= 0) return '';
        const date = new Date(timestamp * 1000);
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    }

    function guessVersionFromUrl(url) {
        const filename = String(url || '').split('/').pop() || '';
        const match = filename.match(/v(?:ersion)?[-_]?(\d+(?:\.\d+)*)/i);
        return match ? match[1] : '';
    }

    async function sha256Hex(buffer) {
        const hashBuffer = await window.crypto.subtle.digest('SHA-256', buffer);
        return Array.from(new Uint8Array(hashBuffer))
            .map(byte => byte.toString(16).padStart(2, '0'))
            .join('');
    }

    function parseHourlyCreditsToRaw(hourlyCredits) {
        const text = String(hourlyCredits ?? '').trim();
        if (!text) {
            throw new Error('Price is required');
        }

        const normalizedText = text.endsWith('.') ? text.slice(0, -1) : text;
        if (!/^(?:\d+|\d*\.\d+)$/.test(normalizedText)) {
            throw new Error('Price must be a non-negative number');
        }

        const [wholeRaw, fractionRaw = ''] = normalizedText.split('.');
        if (fractionRaw.length > CREDIT_DECIMALS) {
            throw new Error(`Price supports up to ${CREDIT_DECIMALS} decimal places`);
        }

        const whole = wholeRaw || '0';
        const fraction = fractionRaw.padEnd(CREDIT_DECIMALS, '0') || '0';
        return BigInt(whole) * RAW_PER_CREDIT + BigInt(fraction);
    }

    function convertHourlyCreditsToRawPerSecond(hourlyCredits) {
        const rawPerHour = parseHourlyCreditsToRaw(hourlyCredits);
        const base = rawPerHour / SECONDS_PER_HOUR;
        const remainder = rawPerHour % SECONDS_PER_HOUR;
        return remainder * 2n >= SECONDS_PER_HOUR ? base + 1n : base;
    }

    function formatRawPricePerHour(rawPricePerSecond) {
        try {
            const rawPerSecond = typeof rawPricePerSecond === 'bigint'
                ? rawPricePerSecond
                : BigInt(rawPricePerSecond ?? 0);
            return roundDecimalString(formatRawCredits(rawPerSecond * SECONDS_PER_HOUR), DISPLAY_PRICE_DECIMALS);
        } catch {
            return '0';
        }
    }

    function formatRawCredits(rawAmount) {
        const normalized = typeof rawAmount === 'bigint' ? rawAmount : BigInt(rawAmount ?? 0);
        const negative = normalized < 0n;
        const value = negative ? -normalized : normalized;
        const whole = value / RAW_PER_CREDIT;
        const fraction = (value % RAW_PER_CREDIT).toString().padStart(CREDIT_DECIMALS, '0');
        const formatted = trimTrailingZeros(`${whole.toString()}.${fraction}`);
        return negative && formatted !== '0' ? `-${formatted}` : formatted;
    }

    function roundDecimalString(value, maxFractionDigits = DISPLAY_PRICE_DECIMALS) {
        if (value === null || value === undefined) return '0';

        const text = String(value).trim();
        if (!text) return '0';

        const negative = text.startsWith('-');
        const unsigned = negative ? text.slice(1) : text;
        if (!/^\d+(?:\.\d+)?$/.test(unsigned)) {
            return '0';
        }

        const safeDigits = Math.max(0, Number(maxFractionDigits) || 0);
        const [integerPartRaw, fractionPartRaw = ''] = unsigned.split('.');
        const integerPart = integerPartRaw || '0';

        if (safeDigits === 0) {
            let roundedInteger = BigInt(integerPart);
            if ((fractionPartRaw[0] || '0') >= '5') {
                roundedInteger += 1n;
            }
            const normalized = roundedInteger.toString();
            return negative && normalized !== '0' ? `-${normalized}` : normalized;
        }

        const paddedFraction = fractionPartRaw.padEnd(safeDigits + 1, '0');
        const keptFraction = paddedFraction.slice(0, safeDigits);
        const roundingDigit = paddedFraction[safeDigits] || '0';
        const scale = 10n ** BigInt(safeDigits);

        let scaledValue = BigInt(integerPart) * scale + BigInt(keptFraction || '0');
        if (roundingDigit >= '5') {
            scaledValue += 1n;
        }

        const roundedInteger = scaledValue / scale;
        const roundedFraction = (scaledValue % scale).toString().padStart(safeDigits, '0');
        const normalized = trimTrailingZeros(`${roundedInteger.toString()}.${roundedFraction}`);
        return negative && normalized !== '0' ? `-${normalized}` : normalized;
    }

    function trimTrailingZeros(value) {
        if (value === null || value === undefined) return '0';
        const text = String(value).trim();
        if (!text) return '0';
        if (!text.includes('.')) return text;
        return text.replace(/(\.\d*?[1-9])0+$/, '$1').replace(/\.0+$/, '').replace(/\.$/, '');
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"'`]/g, ch => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;'
        })[ch]);
    }

    function escapeAttr(value) {
        return escapeHtml(value).replace(/"/g, '&quot;');
    }
})();
