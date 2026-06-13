(function () {
    const state = {
        status: null,
        hosts: [],
        guacamole: [],
        fmus: [],
        uploadedImages: [],
        uploadedDocs: [],
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

        if (!refresh || !submit) return;

        refresh.addEventListener('click', loadPublisherData);
        submit.addEventListener('click', publishLab);
        resourceType.addEventListener('change', renderResourceOptions);
        resourceSelect.addEventListener('change', applySelectedResource);
        setupMode.addEventListener('change', syncSetupMode);
        images.addEventListener('change', () => uploadAssets(images.files, 'images'));
        docs.addEventListener('change', () => uploadAssets(docs.files, 'docs'));

        syncSetupMode();
        loadPublisherData();
    });

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
                : `${resource.name || 'Connection'} #${resource.id} ${resource.hostname ? '- ' + resource.hostname : ''}`;
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
            if (!$('labName').value) $('labName').value = (fmu?.fileName || '').replace(/\.fmu$/i, '');
            preview.textContent = `FMU: ${fmu?.relativePath || fmu?.fileName || 'selected'}`;
            $('labMaxConcurrentUsers').value = Math.max(2, Number($('labMaxConcurrentUsers').value) || 2);
            return;
        }

        const conn = uniqueGuacamole()[Number(index)];
        $('labAccessURI').value = state.status?.recommendedRemoteAccessURI || `${window.location.origin}/guacamole`;
        $('labAccessKey').value = conn?.id ? String(conn.id) : (conn?.name || '');
        if (!$('labName').value) $('labName').value = conn?.name || '';
        preview.textContent = `Guacamole: ${conn?.name || 'Connection'} (${conn?.hostname || 'no host'})`;
        $('labMaxConcurrentUsers').value = 1;
    }

    function syncSetupMode() {
        const quick = $('labSetupMode').value === 'quick';
        $('fullMetadataPanel').style.display = quick ? 'none' : '';
        $('quickMetadataField').style.display = quick ? '' : 'none';
    }

    async function uploadAssets(files, kind) {
        const list = Array.from(files || []);
        if (!list.length) return;
        const contentId = ensureContentId();
        for (const file of list) {
            const form = new FormData();
            form.append('contentId', contentId);
            form.append('kind', kind);
            form.append('file', file);
            const result = await fetchJson('/lab-admin/assets', { method: 'POST', body: form });
            if (kind === 'images') state.uploadedImages.push(result.url);
            else state.uploadedDocs.push(result.url);
        }
        renderAssets();
    }

    async function publishLab() {
        try {
            const setupMode = $('labSetupMode').value;
            const payload = {
                setupMode,
                listImmediately: $('labListImmediately').value === 'true',
                price: $('labPrice').value || '0',
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
        const imageUrls = [...state.uploadedImages];
        const docs = [...state.uploadedDocs];
        const days = splitCsv($('labAvailableDays').value).map(v => v.toUpperCase());
        const [startHour, endHour] = ($('labAvailableHours').value || '09:00-17:00').split('-').map(v => (v || '').trim());
        const attributes = [
            { trait_type: 'category', value: splitCsv($('labCategory').value) },
            { trait_type: 'keywords', value: splitCsv($('labKeywords').value) },
            { trait_type: 'timeSlots', value: splitCsv($('labTimeSlots').value).map(Number).filter(Number.isFinite) },
            { trait_type: 'docs', value: docs },
            { trait_type: 'additionalImages', value: imageUrls.slice(1) },
            { trait_type: 'availableDays', value: days },
            { trait_type: 'availableHours', value: { start: startHour || '09:00', end: endHour || '17:00' } },
            { trait_type: 'timezone', value: $('labTimezone').value.trim() || 'UTC' },
            { trait_type: 'maxConcurrentUsers', value: Number($('labMaxConcurrentUsers').value) || 1 },
        ];
        return {
            contentId: ensureContentId(),
            name: $('labName').value.trim(),
            description: $('labDescription').value.trim(),
            image: imageUrls[0] || '',
            attributes,
        };
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
            ...state.uploadedImages.map(url => ({ label: 'Image', url })),
            ...state.uploadedDocs.map(url => ({ label: 'Doc', url })),
        ];
        target.innerHTML = entries.length
            ? entries.map(entry => `<div class="asset-row"><span>${escapeHtml(entry.label)}</span><a href="${escapeAttr(entry.url)}" target="_blank" rel="noopener">${escapeHtml(entry.url)}</a></div>`).join('')
            : '';
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
                <div class="item-meta">${escapeHtml(lab.price || '0')}</div>
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

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"'`]/g, ch => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;'
        })[ch]);
    }

    function escapeAttr(value) {
        return escapeHtml(value).replace(/"/g, '&quot;');
    }
})();
