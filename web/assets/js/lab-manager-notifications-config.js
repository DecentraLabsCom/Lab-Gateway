(function (global) {
    function createController({
        fields,
        commonTimezones = [],
        browserTimezone = 'UTC',
        createOption = (label, value) => new Option(label, value),
    }) {
        function applyConfig(cfg = {}) {
            fields.enabled.checked = !!cfg.enabled;
            fields.driver.value = cfg.driver || 'NOOP';
            fields.from.value = cfg.from || '';
            fields.fromName.value = cfg.fromName || '';
            fields.defaultTo.value = (cfg.defaultTo || []).join(', ');
            setTimezone(cfg.timezone || browserTimezone);

            const smtp = cfg.smtp || {};
            fields.smtpHost.value = smtp.host || '';
            fields.smtpPort.value = smtp.port || '';
            fields.smtpUser.value = smtp.username || '';
            fields.smtpPass.value = '';
            fields.smtpStartTls.checked = smtp.startTls ?? true;
            if (fields.smtpPasswordHint) {
                fields.smtpPasswordHint.textContent = smtp.passwordConfigured
                    ? 'A password is stored. Leave blank to keep it.'
                    : 'No password is currently stored.';
            }

            const graph = cfg.graph || {};
            fields.graphTenant.value = graph.tenantId || '';
            fields.graphClientId.value = graph.clientId || '';
            fields.graphClientSecret.value = '';
            fields.graphFrom.value = graph.from || '';
            if (fields.graphClientSecretHint) {
                fields.graphClientSecretHint.textContent = graph.clientSecretConfigured
                    ? 'A client secret is stored. Leave blank to keep it.'
                    : 'No client secret is currently stored.';
            }
            toggleSections();
            updateDriverSummary();
        }

        function buildPayload() {
            const smtpPassword = fields.smtpPass.value.trim();
            const graphClientSecret = fields.graphClientSecret.value.trim();
            const payload = {
                enabled: fields.enabled.checked,
                driver: fields.driver.value,
                from: fields.from.value.trim(),
                fromName: fields.fromName.value.trim(),
                defaultTo: fields.defaultTo.value.split(',').map(value => value.trim()).filter(Boolean),
                timezone: fields.timezone.value,
                smtp: {
                    host: fields.smtpHost.value.trim(),
                    port: fields.smtpPort.value ? parseInt(fields.smtpPort.value, 10) : null,
                    username: fields.smtpUser.value.trim(),
                    startTls: fields.smtpStartTls.checked,
                },
                graph: {
                    tenantId: fields.graphTenant.value.trim(),
                    clientId: fields.graphClientId.value.trim(),
                    from: fields.graphFrom.value.trim(),
                },
            };
            if (smtpPassword) payload.smtp.password = smtpPassword;
            if (graphClientSecret) payload.graph.clientSecret = graphClientSecret;
            return payload;
        }

        function toggleSections() {
            const driver = fields.driver.value;
            if (fields.smtpSection) fields.smtpSection.style.display = driver === 'SMTP' ? 'block' : 'none';
            if (fields.graphSection) fields.graphSection.style.display = driver === 'GRAPH' ? 'block' : 'none';
            if (driver === 'NOOP') {
                fields.enabled.checked = false;
            }
        }

        function updateDriverSummary() {
            if (fields.driverSummary) {
                fields.driverSummary.textContent = fields.driver.value || 'NOOP';
            }
        }

        function populateTimezones() {
            fields.timezone.innerHTML = '';
            const primary = createOption(`Auto (browser: ${browserTimezone})`, browserTimezone);
            fields.timezone.appendChild(primary);
            const unique = Array.from(new Set([browserTimezone, ...commonTimezones])).sort();
            unique.forEach(timezone => {
                if (timezone === browserTimezone) return;
                fields.timezone.appendChild(createOption(timezone, timezone));
            });
        }

        function setTimezone(timezone) {
            if (!timezone) {
                fields.timezone.value = browserTimezone;
                return;
            }
            let found = false;
            for (const option of fields.timezone.options) {
                if (option.value === timezone) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                fields.timezone.appendChild(createOption(`${timezone} (config)`, timezone));
            }
            fields.timezone.value = timezone;
        }

        return {
            applyConfig,
            buildPayload,
            populateTimezones,
            setTimezone,
            toggleSections,
            updateDriverSummary,
        };
    }

    global.LabManagerNotificationsConfig = { createController };
})(window);
