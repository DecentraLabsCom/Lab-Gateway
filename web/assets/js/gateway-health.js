document.addEventListener('DOMContentLoaded', () => {
    const statusIndicator = document.querySelector('.status-indicator');
    const statusText = statusIndicator?.querySelector('.status-text');
    const topGrid = document.getElementById('topGrid');
    const serviceGrid = document.getElementById('serviceGrid');
    const infraSection = document.getElementById('infraSection');

    loadHealth();

    function loadHealth() {
        setChecking();
        fetch('/gateway/health')
            .then(res => res.text())
            .then(text => {
                let data = {};
                try {
                    data = text ? JSON.parse(text) : {};
                } catch (e) {
                    data = { parseError: e.message };
                }
                render(data);
            })
            .catch(err => {
                console.error(err);
                setStatus('System Unavailable', 'offline');
                if (serviceGrid) serviceGrid.innerHTML = '<div class="health-row">Cannot load gateway health</div>';
            });
    }

    function setChecking() {
        setStatus('Checking Status...', 'checking');
        if (topGrid) topGrid.innerHTML = '';
        if (serviceGrid) serviceGrid.innerHTML = '';
        if (infraSection) infraSection.innerHTML = '';
    }

    function setStatus(text, cls) {
        if (statusIndicator && statusText) {
            statusIndicator.className = `status-indicator ${cls}`;
            statusText.textContent = text;
        }
    }

    function render(data) {
        const statusVal = (data.status || '').toString().toUpperCase();
        if (statusVal === 'UP') setStatus('System Online', 'online');
        else if (statusVal === 'PARTIAL') setStatus('Partial', 'partial');
        else setStatus('System Unavailable', 'offline');

        const liteMode = data.lite === true || (data.mode || '').toLowerCase() === 'lite';
        renderTop(data, liteMode);
        renderServices(data.services || {}, liteMode);
        renderInfra(data.infra || {});
    }

    function renderTop(data, liteMode) {
        if (!topGrid) return;
        topGrid.innerHTML = '';
        const blockchainItem = liteMode
            ? { label: 'Lite auth trust', ok: data.services?.lite_auth?.ok, na: false }
            : { label: 'Blockchain services', ok: data.services?.blockchain?.ok, na: false };
        const items = [
            blockchainItem,
            { label: 'Labs access', ok: data.services?.guacamole?.ok && data.services?.guacamole_api?.ok && data.services?.guacd?.ok && data.services?.guacamole_schema?.ok && data.services?.mysql?.ok },
            { label: 'Ops worker', ok: data.services?.ops?.ok },
            { label: 'MySQL (gateway)', ok: data.services?.mysql?.ok },
            { label: 'Cert validity', ok: (data.infra?.cert?.days_remaining || 0) > 0 }
        ];
        if (data.services?.fmu_runner?.enabled === true) {
            items.push({ label: 'FMU runner', ok: data.services.fmu_runner.ok });
        }
        if (data.services?.aas?.enabled === true) {
            items.push({ label: 'AAS server', ok: data.services.aas.ok });
        }
        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'health-row';
            div.innerHTML = `<span>${item.label}</span><span class="tag ${item.ok ? 'ok' : 'bad'}">${item.ok ? 'OK' : 'Issue'}</span>`;
            topGrid.appendChild(div);
        });
    }

    function renderServices(services, liteMode) {
        if (!serviceGrid) return;
        serviceGrid.innerHTML = '';

        if (liteMode) {
            // Lite mode: show lite_auth card instead of blockchain
            const liteAuthVal = services.lite_auth || {};
            const liteAuthCard = document.createElement('div');
            liteAuthCard.className = 'health-card service-column';
            const liteAuthOk = liteAuthVal.ok === true;
            const liteAuthTag = summaryTag(liteAuthOk, liteAuthOk ? 'OK' : 'issue');
            liteAuthCard.innerHTML = `
                <div class="health-row">
                    <strong>Lite auth trust</strong>
                    <span class="tag ${liteAuthTag.cls}">${liteAuthTag.text}</span>
                </div>
            `;
            const liteGrid = document.createElement('div');
            liteGrid.className = 'keyval';
            const liteFields = [
                ['External issuer', boolTag(liteAuthVal.external_issuer)],
                ['Issuer URL valid', boolTag(liteAuthVal.issuer_url_valid)],
                ['Issuer DNS', boolTag(liteAuthVal.issuer_host_dns_ok)],
                ['Local public key', boolTag(liteAuthVal.local_public_key_present)],
                ['Local key valid', boolTag(liteAuthVal.local_public_key_valid)],
                ['Remote public key', boolTag(liteAuthVal.remote_public_key_ok)]
            ];
            liteFields.forEach(([k, v]) => {
                const key = document.createElement('div');
                key.className = 'key';
                key.textContent = k;
                const valEl = document.createElement('div');
                valEl.className = 'val';
                valEl.appendChild(v);
                liteGrid.appendChild(key);
                liteGrid.appendChild(valEl);
            });
            if (liteAuthVal.remote_public_key_status && liteAuthVal.remote_public_key_status !== 'not_applicable') {
                const noteKey = document.createElement('div');
                noteKey.className = 'key';
                noteKey.textContent = 'Status';
                const noteVal = document.createElement('div');
                noteVal.className = 'val';
                noteVal.textContent = liteAuthVal.remote_public_key_status;
                liteGrid.appendChild(noteKey);
                liteGrid.appendChild(noteVal);
            }
            liteAuthCard.appendChild(liteGrid);

            // Blockchain card: shown as N/A in Lite mode
            const blockchainCard = document.createElement('div');
            blockchainCard.className = 'health-card service-column';
            blockchainCard.innerHTML = `
                <div class="health-row">
                    <strong>Blockchain services</strong>
                    <span class="tag ok">N/A</span>
                </div>
                <div class="keyval">
                    <div class="key" style="grid-column:1/-1;color:var(--muted,#888)">Not required in Lite mode</div>
                </div>
            `;
            serviceGrid.appendChild(liteAuthCard);
            serviceGrid.appendChild(blockchainCard);
        } else {
            // Full mode: show blockchain card with all sub-checks
            const blockchainVal = services.blockchain || {};
            const blockchainCard = document.createElement('div');
            blockchainCard.className = 'health-card service-column';
            const blockchainOk = blockchainVal.ok === true;
            const blockchainTag = summaryTag(blockchainOk, blockchainVal.status);
            blockchainCard.innerHTML = `
                <div class="health-row">
                    <strong>Blockchain services</strong>
                    <span class="tag ${blockchainTag.cls}">${blockchainTag.text}</span>
                </div>
            `;
            if (blockchainVal.details) {
                const d = blockchainVal.details;
                const grid = document.createElement('div');
                grid.className = 'keyval';
                const fields = [
                    ['RPC', boolTag(d.rpc_up)],
                    ['Marketplace key', boolTag(d.marketplace_key_cached)],
                    ['Private key', boolTag(d.private_key_present)],
                    ['DB', boolTag(d.database_up)],
                    ['Wallet configured', boolTag(d.wallet_configured)],
                    ['Billing configured', boolTag(d.billing_configured ?? d.treasury_configured)],
                    ['Provider registered', boolTag(d.provider_registered)],
                    ['Invite token', boolTag(d.invite_token_configured)],
                    ['Event listener', boolTag(d.event_listener_enabled)],
                    ['SAML validation', boolTag(d.saml_validation_ready)],
                    ['JWT validation', jwtTag(d.jwt_validation)],
                    ['Version', textTag(d.version)]
                ];
                fields.forEach(([k, v]) => {
                    const key = document.createElement('div');
                    key.className = 'key';
                    key.textContent = k;
                    const valEl = document.createElement('div');
                    valEl.className = 'val';
                    valEl.appendChild(v);
                    grid.appendChild(key);
                    grid.appendChild(valEl);
                });
                blockchainCard.appendChild(grid);
            }
            serviceGrid.appendChild(blockchainCard);
        }

        const otherCard = document.createElement('div');
        otherCard.className = 'health-card service-column';
        const otherServices = [
            { key: 'guacamole', label: 'Guacamole' },
            { key: 'guacamole_api', label: 'Guacamole API' },
            { key: 'guacd', label: 'Guacd' },
            { key: 'guacamole_schema', label: 'Guacamole schema' },
            { key: 'ops', label: 'Ops worker' },
            { key: 'mysql', label: 'MySQL (gateway reachability)' }
        ];
        const otherOk = otherServices.every(svc => (services[svc.key] || {}).ok === true);
        const otherPending = otherServices.some(svc => (services[svc.key] || {}).ok === undefined);
        const otherTag = summaryTag(otherOk, otherPending ? undefined : 'issue');
        const otherHeader = document.createElement('div');
        otherHeader.className = 'health-row';
        otherHeader.innerHTML = `
            <strong>Gateway services</strong>
            <span class="tag ${otherTag.cls}">${otherTag.text}</span>
        `;
        otherCard.appendChild(otherHeader);
        otherServices.forEach(svc => {
            const val = services[svc.key] || {};
            const ok = val.ok === true;
            const status = val.status !== undefined ? val.status : (ok ? 'OK' : 'unknown');
            const row = document.createElement('div');
            row.className = 'health-row';
            row.innerHTML = `
                <span>${svc.label}</span>
                <span class="tag ${ok ? 'ok' : 'bad'}">${ok ? 'OK' : `Issue (${status})`}</span>
            `;
            otherCard.appendChild(row);
        });
        serviceGrid.appendChild(otherCard);

        // FMU runner card (only shown when FMU runner is enabled)
        const fmuRunner = services.fmu_runner || {};
        if (fmuRunner.enabled === true) {
            const fmuCard = document.createElement('div');
            fmuCard.className = 'health-card service-column';
            const fmuOk = fmuRunner.ok === true;
            const fmuTag = summaryTag(fmuOk, fmuRunner.status);
            fmuCard.innerHTML = `
                <div class="health-row">
                    <strong>FMU runner</strong>
                    <span class="tag ${fmuTag.cls}">${fmuTag.text}</span>
                </div>
            `;
            const d = fmuRunner.details || {};
            const fmuGrid = document.createElement('div');
            fmuGrid.className = 'keyval';
            const fmuFields = [
                ['Status', textTag(d.status)],
                ['Backend mode', textTag(d.backendMode)],
                ['FMU count', textTag(d.fmuCount !== undefined ? String(d.fmuCount) : undefined)]
            ];
            if (d.checks && typeof d.checks === 'object') {
                Object.keys(d.checks).forEach(k => fmuFields.push([k, boolTag(d.checks[k])]));
            }
            fmuFields.forEach(([k, v]) => {
                const key = document.createElement('div');
                key.className = 'key';
                key.textContent = k;
                const valEl = document.createElement('div');
                valEl.className = 'val';
                valEl.appendChild(v);
                fmuGrid.appendChild(key);
                fmuGrid.appendChild(valEl);
            });
            fmuCard.appendChild(fmuGrid);
            serviceGrid.appendChild(fmuCard);
        }

        // AAS server card (only shown when AAS is enabled)
        const aas = services.aas || {};
        if (aas.enabled === true) {
            const aasCard = document.createElement('div');
            aasCard.className = 'health-card service-column';
            const aasOk = aas.ok === true;
            const aasTag = summaryTag(aasOk, aas.status);
            aasCard.innerHTML = `
                <div class="health-row">
                    <strong>AAS server (BaSyx)</strong>
                    <span class="tag ${aasTag.cls}">${aasTag.text}</span>
                </div>
            `;
            const aasGrid = document.createElement('div');
            aasGrid.className = 'keyval';
            const aasReachableKey = document.createElement('div');
            aasReachableKey.className = 'key';
            aasReachableKey.textContent = 'Reachable';
            const aasReachableVal = document.createElement('div');
            aasReachableVal.className = 'val';
            aasReachableVal.appendChild(boolTag(aas.ok));
            aasGrid.appendChild(aasReachableKey);
            aasGrid.appendChild(aasReachableVal);
            if (aas.status !== undefined) {
                const aasStatusKey = document.createElement('div');
                aasStatusKey.className = 'key';
                aasStatusKey.textContent = 'HTTP status';
                const aasStatusVal = document.createElement('div');
                aasStatusVal.className = 'val';
                aasStatusVal.appendChild(textTag(String(aas.status)));
                aasGrid.appendChild(aasStatusKey);
                aasGrid.appendChild(aasStatusVal);
            }
            aasCard.appendChild(aasGrid);
            serviceGrid.appendChild(aasCard);
        }
    }

    function renderInfra(infra) {
        if (!infraSection) return;
        const dns = infra.dns || {};
        const cert = infra.cert || {};
        const env = infra.env || {};
        infraSection.innerHTML = `
            <div class="section-title">DNS</div>
            <div class="keyval">
                ${Object.keys(dns).map(k => `
                    <div class="key">${k}</div>
                    <div class="val">${formatBool(dns[k])}</div>
                `).join('')}
            </div>
            <div class="section-title">Certificates</div>
            <div class="keyval">
                <div class="key">Days remaining</div><div class="val">${cert.days_remaining ?? 'n/a'}</div>
                <div class="key">Fullchain present</div><div class="val">${formatBool(cert.fullchain_present)}</div>
                <div class="key">Privkey present</div><div class="val">${formatBool(cert.privkey_present)}</div>
            </div>
            <div class="section-title">Static/Env</div>
            <div class="keyval">
                <div class="key">Static root</div><div class="val">${formatBool(infra.static_root_ok)}</div>
                ${Object.keys(env).map(k => `
                    <div class="key">${k}</div><div class="val">${formatBool(env[k])}</div>
                `).join('')}
            </div>
        `;
    }

    function formatBool(val) {
        if (val === true) return 'yes';
        if (val === false) return 'no';
        return 'n/a';
    }

    function boolTag(value) {
        if (value === true) return createTag('OK', 'ok');
        if (value === false) return createTag('Issue', 'bad');
        return createTag('Pending', 'bad');
    }

    function textTag(value) {
        const text = value && value !== '' ? value : 'Pending';
        const cls = value && value !== '' ? 'ok' : 'bad';
        return createTag(text, cls);
    }

    function jwtTag(value) {
        if (value === true) return createTag('OK', 'ok');
        if (value === false) return createTag('Issue', 'bad');
        if (typeof value === 'string') {
            const normalized = value.trim().toLowerCase();
            if (normalized === 'ready' || normalized === 'ok') {
                return createTag('OK', 'ok');
            }
            if (normalized !== '') {
                return createTag('Issue', 'bad');
            }
        }
        return createTag('Pending', 'bad');
    }

    function createTag(text, cls) {
        const tag = document.createElement('span');
        tag.className = `tag ${cls}`;
        tag.textContent = text;
        return tag;
    }

    function summaryTag(ok, status) {
        if (ok) {
            return { cls: 'ok', text: 'OK' };
        }
        if (status === undefined || status === null || status === '') {
            return { cls: 'bad', text: 'Pending' };
        }
        if (typeof status === 'number') {
            if (status >= 500) return { cls: 'bad', text: 'Error' };
            if (status >= 400) return { cls: 'bad', text: 'Issue' };
        }
        const statusText = status.toString().toUpperCase();
        if (statusText === 'DEGRADED' || statusText === 'PARTIAL') {
            return { cls: 'bad', text: 'Issue' };
        }
        if (statusText === 'DOWN' || statusText === 'FAIL' || statusText === 'ERROR') {
            return { cls: 'bad', text: 'Error' };
        }
        return { cls: 'bad', text: 'Issue' };
    }
});
