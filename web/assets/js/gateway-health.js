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

        renderTop(data);
        renderServices(data.services || {});
        renderInfra(data.infra || {});
    }

    function renderTop(data) {
        if (!topGrid) return;
        topGrid.innerHTML = '';
        const items = [
            { label: 'Blockchain services', ok: data.services?.blockchain?.ok },
            { label: 'Labs access', ok: data.services?.guacamole?.ok && data.services?.guacamole_api?.ok && data.services?.guacd?.ok && data.services?.guacamole_schema?.ok && data.services?.mysql?.ok },
            { label: 'Ops worker', ok: data.services?.ops?.ok },
            { label: 'MySQL (gateway)', ok: data.services?.mysql?.ok },
            { label: 'Cert validity', ok: (data.infra?.cert?.days_remaining || 0) > 0 }
        ];
        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'health-row';
            div.innerHTML = `<span>${item.label}</span><span class="tag ${item.ok ? 'ok' : 'bad'}">${item.ok ? 'OK' : 'Issue'}</span>`;
            topGrid.appendChild(div);
        });
    }

    function renderServices(services) {
        if (!serviceGrid) return;
        serviceGrid.innerHTML = '';
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
                ['Treasury configured', boolTag(d.treasury_configured)],
                ['Provider registered', boolTag(d.provider_registered)],
                ['Invite token', boolTag(d.invite_token_configured)],
                ['Event listener', boolTag(d.event_listener_enabled)],
                ['SAML validation', boolTag(d.saml_validation_ready)],
                ['JWT validation', textTag(d.jwt_validation)],
                ['Version', textTag(d.version)]
            ];
            fields.forEach(([k,v]) => {
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
