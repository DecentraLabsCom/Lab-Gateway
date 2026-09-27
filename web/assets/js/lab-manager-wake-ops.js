(function (root) {
    'use strict';

    const EVIDENCE_SECONDS = 7 * 24 * 60 * 60;

    function createController({
        fields = {},
        fetchImpl,
        callbacks = {},
        documentImpl = root.document,
        logger = console,
    } = {}) {
        if (typeof fetchImpl !== 'function') throw new Error('LabManagerWakeOps requires fetchImpl');

        const { showToast = () => {} } = callbacks;
        let activeHost = '';
        let currentData = {};

        function hostUrl(host, suffix = '') {
            return `/ops/api/wake-ops/${encodeURIComponent(host)}${suffix}`;
        }

        function setOpen(open) {
            if (!fields.modal) return;
            fields.modal.hidden = !open;
            fields.modal.classList?.toggle?.('show', open);
        }

        function formatEvidence(evidence = {}) {
            const validDays = Math.round((Number(evidence.validForSeconds || EVIDENCE_SECONDS)) / 86400);
            if (evidence.state === 'verified') {
                const age = Number.isFinite(Number(evidence.ageSeconds))
                    ? ` hace ${Math.max(0, Math.round(Number(evidence.ageSeconds) / 3600))} h`
                    : '';
                return `WoL verificado${age}. La evidencia es válida ${validDays} días.`;
            }
            if (evidence.state === 'expired') return 'La evidencia WoL anterior ha caducado; ejecuta Wake o espera a la próxima prueba.';
            if (evidence.state === 'failed') return `El último intento de WoL falló${evidence.message ? `: ${evidence.message}` : '.'}`;
            return 'No hay evidencia WoL verificada recientemente.';
        }

        function render(data = {}) {
            currentData = data;
            const schedule = data.schedule || {};
            const evidence = data.evidence || {};
            if (fields.host) fields.host.textContent = data.host || activeHost;
            if (fields.enabled) fields.enabled.checked = schedule.enabled !== false;
            if (fields.day) fields.day.value = String(schedule.dayOfWeek ?? 6);
            const hour = String(schedule.hour ?? 8).padStart(2, '0');
            const minute = String(schedule.minute ?? 0).padStart(2, '0');
            if (fields.time) fields.time.value = `${hour}:${minute}`;
            if (fields.hour) fields.hour.value = hour;
            if (fields.minute) fields.minute.value = minute;
            if (fields.timezone) {
                const timezone = String(schedule.timezone || '');
                const hasOption = Array.from(fields.timezone.options || []).some(option => option.value === timezone);
                if (timezone && !hasOption && fields.timezone.appendChild && documentImpl?.createElement) {
                    const option = documentImpl.createElement('option');
                    option.value = timezone;
                    option.textContent = timezone;
                    fields.timezone.appendChild(option);
                }
                fields.timezone.value = timezone;
            }
            if (fields.status) {
                const lastRun = schedule.lastStatus
                    ? ` Última prueba programada: ${schedule.lastStatus}${schedule.lastMessage ? ` (${schedule.lastMessage})` : ''}.`
                    : '';
                fields.status.textContent = `${formatEvidence(evidence)}${lastRun}`;
            }
            return data;
        }

        async function requestJson(url, options) {
            const response = await fetchImpl(url, options);
            let body = {};
            try { body = await response.json(); } catch (_err) { /* handled below */ }
            if (!response.ok) {
                throw new Error(body?.error || `HTTP ${response.status}`);
            }
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
            if (fields.status) fields.status.textContent = 'Cargando configuración de Wake Ops…';
            try {
                return await load(host);
            } catch (err) {
                logger.error(err);
                if (fields.status) fields.status.textContent = `No se pudo cargar Wake Ops: ${err.message}`;
                showToast(`Wake Ops failed for ${host}: ${err.message}`, 'error');
                return null;
            }
        }

        function close() {
            activeHost = '';
            setOpen(false);
        }

        function readSchedule() {
            const timeValue = fields.time?.value || '';
            const [timeHour, timeMinute] = timeValue.includes(':')
                ? timeValue.split(':')
                : [undefined, undefined];
            return {
                enabled: Boolean(fields.enabled?.checked),
                dayOfWeek: Number(fields.day?.value ?? 6),
                hour: Number(timeHour ?? fields.hour?.value ?? 8),
                minute: Number(timeMinute ?? fields.minute?.value ?? 0),
                timezone: fields.timezone?.value || undefined,
            };
        }

        async function save() {
            if (!activeHost) return false;
            try {
                const body = await requestJson(hostUrl(activeHost), {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(readSchedule()),
                });
                render({
                    ...currentData,
                    host: activeHost,
                    schedule: body.schedule || readSchedule(),
                });
                showToast(`Wake Ops schedule saved for ${activeHost}`, 'success');
                return true;
            } catch (err) {
                logger.error(err);
                showToast(`Wake Ops save failed for ${activeHost}: ${err.message}`, 'error');
                return false;
            }
        }

        async function manualWake() {
            if (!activeHost) return false;
            if (fields.wakeButton) fields.wakeButton.disabled = true;
            if (fields.status) fields.status.textContent = `Enviando Wake a ${activeHost}…`;
            try {
                const result = await requestJson(hostUrl(activeHost, '/wake'), { method: 'POST' });
                if (!result.success) throw new Error(result.message || 'Wake failed');
                showToast(`Wake manual completado para ${activeHost}`, 'success');
                await load(activeHost);
                return true;
            } catch (err) {
                logger.error(err);
                showToast(`Wake manual failed for ${activeHost}: ${err.message}`, 'error');
                if (fields.status) fields.status.textContent = `Wake manual no completado: ${err.message}`;
                return false;
            } finally {
                if (fields.wakeButton) fields.wakeButton.disabled = false;
            }
        }

        return Object.freeze({ close, load, manualWake, open, render, save });
    }

    root.LabManagerWakeOps = Object.freeze({ createController });
})(window);
