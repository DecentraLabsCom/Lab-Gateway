(function (root) {
    'use strict';

    const FALLBACK_TIMEZONES = [
        'UTC', 'Europe/Madrid', 'Europe/London', 'Europe/Paris', 'Europe/Berlin',
        'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Asia/Tokyo',
    ];

    function createController({
        fields = {},
        fetchImpl,
        callbacks = {},
        documentImpl = root.document,
        confirmImpl = message => root.confirm?.(message),
        logger = console,
    } = {}) {
        if (typeof fetchImpl !== 'function') throw new Error('LabManagerShutdownOps requires fetchImpl');

        const { showToast = () => {} } = callbacks;
        let activeHost = '';
        let currentData = {};
        let manualShutdownInFlight = false;

        function hostUrl(host, suffix = '') {
            return `/ops/api/shutdown-ops/${encodeURIComponent(host)}${suffix}`;
        }

        function setOpen(open) {
            if (!fields.modal) return;
            fields.modal.hidden = !open;
            fields.modal.classList?.toggle?.('show', open);
        }

        function populateTimezones() {
            const select = fields.timezone;
            if (!select || !documentImpl?.createElement || typeof select.appendChild !== 'function') return;
            const current = String(select.value || '');
            select.innerHTML = '';
            let fallback = FALLBACK_TIMEZONES;
            if (typeof Intl !== 'undefined' && typeof Intl.supportedValuesOf === 'function') {
                try {
                    fallback = Intl.supportedValuesOf('timeZone');
                } catch (_err) {
                    fallback = FALLBACK_TIMEZONES;
                }
            }
            [...new Set(['', 'UTC', ...fallback])]
                .sort((left, right) => left.localeCompare(right))
                .forEach(value => {
                    const option = documentImpl.createElement('option');
                    option.value = value;
                    option.textContent = value || 'Use Lab Gateway timezone';
                    select.appendChild(option);
                });
            if (current) select.value = current;
        }

        function render(data = {}) {
            currentData = data;
            const schedule = data.schedule || {};
            if (fields.host) fields.host.textContent = data.host || activeHost;
            if (fields.afterReservationEnd) fields.afterReservationEnd.checked = schedule.afterReservationEnd === true;
            if (fields.weeklyEnabled) fields.weeklyEnabled.checked = schedule.weeklyEnabled === true;
            if (fields.day) fields.day.value = String(schedule.dayOfWeek ?? 6);
            const hour = String(schedule.hour ?? 23).padStart(2, '0');
            const minute = String(schedule.minute ?? 0).padStart(2, '0');
            if (fields.time) fields.time.value = `${hour}:${minute}`;
            if (fields.timezone) {
                const timezone = String(schedule.timezone || '');
                if (timezone && !Array.from(fields.timezone.options || []).some(option => option.value === timezone)) {
                    const option = documentImpl.createElement('option');
                    option.value = timezone;
                    option.textContent = timezone;
                    fields.timezone.appendChild(option);
                }
                fields.timezone.value = timezone;
            }
            if (fields.status) {
                const lastRun = schedule.lastStatus
                    ? ` Last weekly run: ${schedule.lastStatus}${schedule.lastMessage ? ` (${schedule.lastMessage})` : ''}.`
                    : '';
                fields.status.textContent = `Automatic shutdowns are sent immediately after the Gateway confirms the station is idle. Lab Station checks again and blocks shutdown if local use or active user sessions are detected.${lastRun}`;
            }
            return data;
        }

        async function requestJson(url, options) {
            const response = await fetchImpl(url, options);
            let body = {};
            try { body = await response.json(); } catch (_err) { /* handled below */ }
            if (!response.ok) throw new Error(body?.message || body?.error || `HTTP ${response.status}`);
            return body;
        }

        async function load(host = activeHost) {
            const data = await requestJson(hostUrl(host));
            return render(data);
        }

        async function open(host) {
            activeHost = host;
            setOpen(true);
            if (fields.host) fields.host.textContent = host;
            if (fields.status) fields.status.textContent = 'Loading Shutdown Ops configuration...';
            try {
                return await load(host);
            } catch (err) {
                logger.error(err);
                if (fields.status) fields.status.textContent = `Unable to load Shutdown Ops: ${err.message}`;
                showToast(`Shutdown Ops failed for ${host}: ${err.message}`, 'error');
                return null;
            }
        }

        function close() {
            activeHost = '';
            setOpen(false);
        }

        function readSchedule() {
            const [hour, minute] = String(fields.time?.value || '23:00').split(':');
            return {
                afterReservationEnd: Boolean(fields.afterReservationEnd?.checked),
                weeklyEnabled: Boolean(fields.weeklyEnabled?.checked),
                dayOfWeek: Number(fields.day?.value ?? 6),
                hour: Number(hour),
                minute: Number(minute),
                timezone: fields.timezone?.value || undefined,
            };
        }

        async function save() {
            if (!activeHost) return false;
            try {
                const schedule = readSchedule();
                const body = await requestJson(hostUrl(activeHost), {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(schedule),
                });
                render({ ...currentData, host: activeHost, schedule: body.schedule || schedule });
                showToast(`Shutdown Ops settings saved for ${activeHost}`, 'success');
                return true;
            } catch (err) {
                logger.error(err);
                showToast(`Shutdown Ops save failed for ${activeHost}: ${err.message}`, 'error');
                return false;
            }
        }

        async function manualShutdown() {
            if (!activeHost || manualShutdownInFlight) return false;
            const confirmed = confirmImpl(
                `Shut down ${activeHost} immediately? Lab Station will cancel if local use or active user sessions are detected.`,
            );
            if (confirmed === false) return false;

            manualShutdownInFlight = true;
            const button = fields.shutdownButton;
            const previousMarkup = button?.innerHTML || '<i class="fas fa-power-off"></i> Shut down station';
            if (button) {
                button.disabled = true;
                button.innerHTML = '<span class="wake-ops-spinner" aria-hidden="true"></span><span>Requesting shutdown...</span>';
                button.setAttribute?.('aria-busy', 'true');
            }
            if (fields.status) fields.status.textContent = `Requesting guarded shutdown for ${activeHost}...`;
            try {
                const result = await requestJson(hostUrl(activeHost, '/shutdown'), { method: 'POST' });
                const message = result.message || `Shutdown scheduled for ${activeHost}`;
                if (fields.status) fields.status.textContent = message;
                showToast(message, 'success');
                return true;
            } catch (err) {
                logger.error(err);
                if (fields.status) fields.status.textContent = `Shutdown was not scheduled: ${err.message}`;
                showToast(`Shutdown failed for ${activeHost}: ${err.message}`, 'error');
                return false;
            } finally {
                if (button) {
                    button.disabled = false;
                    button.innerHTML = previousMarkup;
                    button.removeAttribute?.('aria-busy');
                }
                manualShutdownInFlight = false;
            }
        }

        populateTimezones();
        return Object.freeze({ close, load, manualShutdown, open, render, save });
    }

    root.LabManagerShutdownOps = Object.freeze({ createController });
})(window);
