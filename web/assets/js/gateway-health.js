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
            { label: 'Labs access', ok: data.services?.guacamole?.ok && data.services?.guacamole_api?.ok && data.services?.mysql?.ok },
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
        const svcList = [
            { key: 'blockchain', label: 'Blockchain services' },
            { key: 'guacamole', label: 'Guacamole' },
            { key: 'guacamole_api', label: 'Guacamole API' },
            { key: 'ops', label: 'Ops worker' },
            { key: 'mysql', label: 'MySQL (gateway reachability)' }
        ];
        svcList.forEach(svc => {
            const val = services[svc.key] || {};
            const card = document.createElement('div');
            card.className = 'health-card';
            const ok = val.ok === true;
            const status = val.status !== undefined ? val.status : (ok ? 'OK' : 'unknown');
            card.innerHTML = `
                <div class="health-row">
                    <strong>${svc.label}</strong>
                    <span class="tag ${ok ? 'ok' : 'bad'}">${ok ? 'OK' : `Issue (${status})`}</span>
                </div>
            `;
            if (svc.key === 'blockchain' && val.details) {
                const d = val.details;
                const grid = document.createElement('div');
                grid.className = 'keyval';
                const fields = [
                    ['RPC', formatBool(d.rpc_up)],
                    ['Marketplace key', formatBool(d.marketplace_key_cached)],
                    ['Private key', formatBool(d.private_key_present)],
                    ['DB', formatBool(d.database_up)],
                    ['Wallet configured', formatBool(d.wallet_configured)],
                    ['Treasury configured', formatBool(d.treasury_configured)],
                    ['Invite token', formatBool(d.invite_token_configured)],
                    ['Event listener', formatBool(d.event_listener_enabled)],
                    ['SAML validation', formatBool(d.saml_validation_ready)],
                    ['JWT validation', d.jwt_validation || 'n/a'],
                    ['Version', d.version || 'n/a']
                ];
                fields.forEach(([k,v]) => {
                    const key = document.createElement('div');
                    key.className = 'key';
                    key.textContent = k;
                    const valEl = document.createElement('div');
                    valEl.className = 'val';
                    valEl.textContent = v;
                    grid.appendChild(key);
                    grid.appendChild(valEl);
                });
                card.appendChild(grid);
            }
            serviceGrid.appendChild(card);
        });
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
});
