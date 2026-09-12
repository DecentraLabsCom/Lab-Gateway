(function (root) {
    'use strict';

    function fallbackEscapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function createController({
        fields,
        fetchImpl,
        showToast,
        showOpsWarning,
        refreshPowerControllerStatuses = () => {},
        renderControllerCredentialOptions = () => {},
        escapeHtml = fallbackEscapeHtml,
        documentImpl = typeof document === 'undefined' ? null : document,
    }) {
        let powerCredentials = [];

        function updateFields() {
            const type = fields.type?.value || 'netio-http-basic';
            const isNetio = type === 'netio-http-basic';
            const isSnmpV1V2 = type === 'snmpv1' || type === 'snmpv2c';
            const isSnmpV3 = type === 'snmpv3';
            const authProtocol = fields.authProtocol?.value || 'NONE';
            const privProtocol = fields.privProtocol?.value || 'NONE';
            if (fields.usernameField) fields.usernameField.hidden = isSnmpV1V2;
            if (fields.passwordField) fields.passwordField.hidden = !isNetio;
            if (fields.communityField) fields.communityField.hidden = !isSnmpV1V2;
            if (fields.authProtocolField) fields.authProtocolField.hidden = !isSnmpV3;
            if (fields.authPasswordField) fields.authPasswordField.hidden = !isSnmpV3 || authProtocol === 'NONE';
            if (fields.privProtocolField) fields.privProtocolField.hidden = !isSnmpV3;
            if (fields.privPasswordField) fields.privPasswordField.hidden = !isSnmpV3 || privProtocol === 'NONE';
            if (fields.contextNameField) fields.contextNameField.hidden = !isSnmpV3;
        }

        function resetEditor() {
            if (fields.select) fields.select.value = '';
            if (fields.ref) {
                fields.ref.value = '';
                fields.ref.disabled = false;
            }
            if (fields.type) {
                fields.type.value = 'netio-http-basic';
                fields.type.disabled = false;
            }
            [
                fields.username,
                fields.password,
                fields.community,
                fields.authPassword,
                fields.privPassword,
                fields.contextName,
            ].forEach(field => {
                if (field) field.value = '';
            });
            if (fields.authProtocol) fields.authProtocol.value = 'NONE';
            if (fields.privProtocol) fields.privProtocol.value = 'NONE';
            updateFields();
            if (fields.editorHint) fields.editorHint.textContent = 'Configure a new provider-local credential.';
        }

        function populateForm(credential) {
            if (fields.ref) {
                fields.ref.value = credential.credentialRef || '';
                fields.ref.disabled = true;
            }
            if (fields.type) {
                fields.type.value = credential.type || 'netio-http-basic';
                fields.type.disabled = true;
            }
            [
                fields.username,
                fields.password,
                fields.community,
                fields.authPassword,
                fields.privPassword,
                fields.contextName,
            ].forEach(field => {
                if (field) field.value = '';
            });
            if (fields.authProtocol) fields.authProtocol.value = 'NONE';
            if (fields.privProtocol) fields.privProtocol.value = 'NONE';
            updateFields();
            if (fields.editorHint) fields.editorHint.textContent = 'Enter replacement secret values to rotate this credential. The current values are never loaded.';
        }

        function renderOptions() {
            if (!fields.select) return;
            const current = fields.select.value;
            fields.select.innerHTML = '<option value="">New credential</option>';
            powerCredentials.forEach(credential => {
                const option = documentImpl?.createElement('option') || { dataset: {} };
                option.value = credential.credentialRef || '';
                option.textContent = `${credential.credentialRef || 'unknown'} · ${credential.type || 'unknown'}`;
                fields.select.appendChild(option);
            });
            const selected = powerCredentials.some(item => String(item.credentialRef) === String(current)) ? current : '';
            fields.select.value = selected;
            if (selected) loadSelected();
            else resetEditor();
        }

        function loadSelected() {
            const reference = fields.select?.value || '';
            const credential = powerCredentials.find(item => String(item.credentialRef || '') === String(reference));
            if (credential) populateForm(credential);
            else resetEditor();
        }

        function renderList() {
            if (!fields.list) return;
            if (!powerCredentials.length) {
                fields.list.innerHTML = '<div class="empty">No energy credentials are configured.</div>';
                return;
            }
            fields.list.innerHTML = powerCredentials.map(credential => `
            <div class="power-controller-row power-credential-row">
                <div>
                    <strong>${escapeHtml(credential.credentialRef || 'unknown')}</strong>
                    <div class="host-meta">Type: ${escapeHtml(credential.type || 'unknown')} · Secret values hidden</div>
                </div>
                <button class="mini-btn" type="button" data-power-credential-ref="${escapeHtml(credential.credentialRef || '')}">Rotate</button>
            </div>
        `).join('');
        }

        function handleActions(event) {
            const button = event.target?.closest?.('[data-power-credential-ref]');
            const reference = button?.dataset?.powerCredentialRef;
            if (!reference || !fields.select) return;
            fields.select.value = reference;
            loadSelected();
        }

        function readForm() {
            const credentialRef = (fields.ref?.value || '').trim().toLowerCase();
            const type = (fields.type?.value || '').trim().toLowerCase();
            if (!credentialRef) throw new Error('Credential reference is required');
            if (!/^[a-z0-9][a-z0-9._:-]{0,127}$/.test(credentialRef)) throw new Error('Credential reference contains invalid characters');
            if (!['netio-http-basic', 'snmpv1', 'snmpv2c', 'snmpv3'].includes(type)) throw new Error('Select a supported credential type');

            let credentials;
            if (type === 'netio-http-basic') {
                const username = (fields.username?.value || '').trim();
                const password = fields.password?.value || '';
                if (!username || !password) throw new Error('NETIO username and password are required');
                credentials = { username, password };
            } else if (type === 'snmpv1' || type === 'snmpv2c') {
                const community = fields.community?.value || '';
                if (!community) throw new Error('SNMP community is required');
                credentials = { version: type.slice(4), community };
            } else {
                const username = (fields.username?.value || '').trim();
                const authProtocol = fields.authProtocol?.value || 'NONE';
                const privProtocol = fields.privProtocol?.value || 'NONE';
                if (!username) throw new Error('SNMPv3 username is required');
                if (privProtocol !== 'NONE' && authProtocol === 'NONE') throw new Error('SNMPv3 privacy requires authentication');
                credentials = { version: 'v3', username, authProtocol, privProtocol };
                if (authProtocol !== 'NONE') {
                    const authPassword = fields.authPassword?.value || '';
                    if (!authPassword) throw new Error('SNMPv3 authentication password is required');
                    credentials.authPassword = authPassword;
                }
                if (privProtocol !== 'NONE') {
                    const privPassword = fields.privPassword?.value || '';
                    if (!privPassword) throw new Error('SNMPv3 privacy password is required');
                    credentials.privPassword = privPassword;
                }
                const contextName = (fields.contextName?.value || '').trim();
                if (contextName) credentials.contextName = contextName;
            }
            return {
                credentialRef,
                type,
                credentials,
                overwrite: Boolean(fields.select?.value),
            };
        }

        async function load(options = {}) {
            if (fields.status) {
                fields.status.textContent = 'Loading...';
                fields.status.className = 'pill soft';
            }
            try {
                const response = await fetchImpl('/ops/api/power/credentials', options);
                if (response.status === 403) {
                    showOpsWarning();
                    return;
                }
                if (response.status === 401) {
                    if (!options.skipAuthPrompt) showToast('Lab Manager session required to load energy credentials', 'error');
                    return;
                }
                const body = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
                powerCredentials = Array.isArray(body.credentials) ? body.credentials : [];
                renderList();
                renderOptions();
                renderControllerCredentialOptions(powerCredentials);
                if (fields.status) {
                    fields.status.textContent = `${powerCredentials.length} credential${powerCredentials.length === 1 ? '' : 's'}`;
                    fields.status.className = 'pill good';
                }
                if (fields.hint) fields.hint.textContent = powerCredentials.length
                    ? 'Secret values are write-only. Select a reference to rotate it.'
                    : 'No energy credentials are configured.';
            } catch (error) {
                console.warn('Unable to load power credentials', error);
                powerCredentials = [];
                renderList();
                renderOptions();
                renderControllerCredentialOptions(powerCredentials);
                if (fields.status) {
                    fields.status.textContent = 'Unavailable';
                    fields.status.className = 'pill bad';
                }
                if (fields.hint) fields.hint.textContent = 'Energy credentials could not be loaded.';
            }
        }

        async function save() {
            let credential;
            try {
                credential = readForm();
            } catch (error) {
                showToast(`Energy credential is invalid: ${error.message}`, 'error');
                return;
            }
            if (fields.saveButton) fields.saveButton.disabled = true;
            try {
                const response = await fetchImpl('/ops/api/power/credentials', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(credential),
                });
                const body = await response.json().catch(() => ({}));
                if (response.status === 403) {
                    showOpsWarning();
                    return;
                }
                if (response.status === 401) throw new Error('Lab Manager session required');
                if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
                showToast(`${credential.overwrite ? 'Energy credential rotated' : 'Energy credential saved'}: ${credential.credentialRef}`, 'success');
                await load({ skipAuthPrompt: true });
                refreshPowerControllerStatuses({ forceRefresh: true, skipAuthPrompt: true });
                if (fields.select) fields.select.value = credential.credentialRef;
                loadSelected();
            } catch (error) {
                showToast(`Energy credential save failed: ${error.message}`, 'error');
            } finally {
                if (fields.saveButton) fields.saveButton.disabled = false;
            }
        }

        function initialize() {
            fields.select?.addEventListener('change', loadSelected);
            fields.type?.addEventListener('change', updateFields);
            fields.authProtocol?.addEventListener('change', updateFields);
            fields.privProtocol?.addEventListener('change', updateFields);
            fields.saveButton?.addEventListener('click', save);
            fields.list?.addEventListener('click', handleActions);
            updateFields();
        }

        return Object.freeze({
            getCredentials: () => powerCredentials,
            handleActions,
            initialize,
            load,
            loadSelected,
            populateForm,
            readForm,
            renderList,
            renderOptions,
            resetEditor,
            save,
            updateFields,
        });
    }

    root.LabManagerPowerCredentials = Object.freeze({ createController });
})(window);
