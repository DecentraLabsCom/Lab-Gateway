(function (root) {
    'use strict';

    function createController({
        escapeHtml,
        htmlEscape,
        formatDate,
        formatBool,
        formatReservationDate,
        formatRange,
        isReservationWindowEnded,
        normalizeReservationStatus,
        cancellationButtonLabel,
        shortAddress,
        resolveReservationLabDisplayName,
    } = {}) {
        const dependencies = {
            escapeHtml,
            htmlEscape,
            formatDate,
            formatBool,
            formatReservationDate,
            formatRange,
            isReservationWindowEnded,
            normalizeReservationStatus,
            cancellationButtonLabel,
            shortAddress,
            resolveReservationLabDisplayName,
        };
        Object.entries(dependencies).forEach(([name, dependency]) => {
            if (typeof dependency !== 'function') {
                throw new Error(`LabManagerReservationRenderers requires ${name}`);
            }
        });

        function renderUpcomingReservationsMarkup(reservations, hasMore = false) {
            const items = (Array.isArray(reservations) ? reservations : []).map(reservation => {
                const key = String(reservation.reservationKey || '');
                const status = String(reservation.statusLabel || 'UNKNOWN');
                const numericStatus = normalizeReservationStatus(reservation.status);
                const accessWindowEnded = isReservationWindowEnded(reservation);
                const displayedStatus = accessWindowEnded && !/access window ended/i.test(status)
                    ? `${status} · ACCESS WINDOW ENDED`
                    : status;
                const statusClass = accessWindowEnded
                    ? 'warn'
                    : numericStatus === 1 ? 'good' : numericStatus === 0 ? 'warn' : 'soft';
                const reasonOptions = Array.isArray(reservation.cancellationOptions)
                    ? reservation.cancellationOptions
                        .map(option => ({
                            code: Number(option.reasonCode),
                            label: String(option.label || `Reason ${option.reasonCode}`),
                            deadline: Number(option.deadline),
                            penalty: Number(option.reputationPenalty),
                        }))
                        .filter(option => Number.isInteger(option.code))
                    : [];
                const defaultReasonCode = reasonOptions[0]?.code;
                const actions = reservation.cancellable && reasonOptions.length
                    ? `<div class="reservation-item-actions">
                    <button type="button" class="mini-btn danger" data-action="cancel-reservation" data-reservation-key="${escapeHtml(key)}">
                        ${cancellationButtonLabel(numericStatus, defaultReasonCode)}
                    </button>
                    <select class="reservation-reason" aria-label="Cancellation reason" data-reservation-reason>
                        ${reasonOptions.map(option => {
                            const deadline = Number.isFinite(option.deadline)
                                ? `until ${formatReservationDate(option.deadline)}`
                                : 'deadline unavailable';
                            const penalty = Number.isFinite(option.penalty)
                                ? `${option.penalty} reputation`
                                : 'penalty unavailable';
                            return `<option value="${option.code}">Reason ${option.code}: ${escapeHtml(option.label)} · ${escapeHtml(penalty)} · ${escapeHtml(deadline)}</option>`;
                        }).join('')}
                    </select>
                </div>`
                    : `<div class="reservation-cancel-note">Cancellation unavailable for this status.</div>`;
                const renter = shortAddress(reservation.renter);
                const labLabel = resolveReservationLabDisplayName(reservation);
                const institution = reservation.institutionName || shortAddress(reservation.institutionAddress);
                return `<article class="reservation-item" data-reservation-key="${escapeHtml(key)}" data-reservation-status="${numericStatus ?? ''}">
                <div class="reservation-item-heading">
                    <span class="item-title">${escapeHtml(labLabel)}</span>
                    <span class="reservation-item-reference">Reservation: <code title="${escapeHtml(key)}">${escapeHtml(shortAddress(key, 12, 10))}</code></span>
                    <span class="pill ${statusClass}">${escapeHtml(displayedStatus)}</span>
                </div>
                <div class="reservation-item-schedule">
                    <span>${escapeHtml(formatReservationDate(reservation.start))} – ${escapeHtml(formatReservationDate(reservation.end))}</span>
                    ${actions}
                </div>
                <div class="reservation-item-meta">
                    <span>Price: ${escapeHtml(reservation.priceCredits || '0')} service credits</span>
                    <span>Provider share: ${escapeHtml(reservation.providerShareCredits || '0')} credits</span>
                    <span>Renter: (${escapeHtml(institution || 'Unknown')}) ${escapeHtml(renter)}</span>
                </div>
            </article>`;
            }).join('');
            const loadMore = hasMore
                ? '<div class="reservation-pagination"><button type="button" class="mini-btn primary" data-action="load-more-actionable">Load more</button></div>'
                : '';
            return `${items}${loadMore}`;
        }

        function renderTimelineMarkup(data) {
            const source = data || {};
            const summary = buildTimelineSummary(source);
            const phases = buildTimelinePhases(source.phases || {});
            const operations = buildTimelineOperations(source.operations || [], source.pagination);
            const heartbeat = buildTimelineHeartbeat(source.heartbeat, source.host);
            return summary + phases + operations + heartbeat;
        }

        function buildTimelineSummary(data) {
            const reservation = data.reservation || {};
            const host = data.host || {};
            const labId = host.labId || reservation.labId;
            const labName = host.labName || reservation.labName;
            const rows = [
                { label: 'Reservation', value: reservation.reservationId || 'n/a', mono: true },
                { label: 'Lab', value: resolveReservationLabDisplayName({ labId, labName }) || 'n/a' },
                { label: 'Host', value: host.name || 'n/a' },
                { label: 'Status', value: reservation.status || 'unknown' },
                { label: 'Schedule', value: formatRange(reservation.start, reservation.end) },
            ];
            return `
                <div class="timeline-summary">
                    ${rows.map(row => `
                        <div>
                            <div class="label">${row.label}</div>
                            <div class="value ${row.mono ? 'mono' : ''}">${htmlEscape(row.value)}</div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        function buildTimelinePhases(phases) {
            const config = [
                { key: 'wake', label: 'Wake' },
                { key: 'prepare', label: 'Prepare' },
                { key: 'schedulerEnd', label: 'Scheduler End' },
                { key: 'release', label: 'Release' },
                { key: 'power', label: 'Power' },
            ];
            const pills = config.map(item => {
                const phase = phases[item.key];
                if (!phase) {
                    return `<span class="pill soft">${item.label}: pending</span>`;
                }
                const cls = phase.success ? 'good' : 'bad';
                const title = buildPhaseTitle(phase);
                const status = phase.status || (phase.success ? 'ok' : 'error');
                return `<span class="pill ${cls}" title="${htmlEscape(title)}">${item.label}: ${htmlEscape(status)}</span>`;
            }).join('');
            return `
                <div class="timeline-phases">
                    <h3>Phases</h3>
                    <div class="pill-group">${pills}</div>
                </div>
            `;
        }

        function buildTimelineOperations(operations, pagination) {
            const steps = operations.length
                ? operations.map((op, idx) => renderTimelineStep(op, idx)).join('')
                : '<div class="timeline-step">No orchestration events captured yet.</div>';
            const paginationControls = buildTimelinePagination(pagination);
            return `
                <div class="timeline-steps">
                    <h3>Operation Log</h3>
                    ${steps}
                    ${paginationControls}
                </div>
            `;
        }

        function buildTimelinePagination(pagination) {
            if (!pagination) {
                return '';
            }
            const returned = pagination.returned || 0;
            const total = typeof pagination.total === 'number' ? pagination.total : returned;
            const start = returned ? pagination.offset + 1 : pagination.offset;
            const end = pagination.offset + returned;
            const summary = total
                ? `Showing ${start || 0}-${end} of ${total}`
                : `Showing ${returned} entr${returned === 1 ? 'y' : 'ies'}`;
            const button = pagination.hasMore
                ? '<button id="timelineLoadMoreBtn" class="mini-btn primary">Load more</button>'
                : '';
            return `
                <div class="timeline-pagination">
                    <div class="meta">${htmlEscape(summary)}</div>
                    ${button}
                </div>
            `;
        }

        function renderTimelineStep(op, idx) {
            const success = !!op.success;
            const status = op.status || (success ? 'success' : 'error');
            const metaParts = [formatDate(op.createdAt)];
            if (op.durationMs !== null && op.durationMs !== undefined) {
                metaParts.push(`${op.durationMs} ms`);
            }
            if (op.responseCode) {
                metaParts.push(`code ${op.responseCode}`);
            }
            const meta = metaParts.filter(Boolean).join(' · ');
            return `
                <div class="timeline-step ${success ? 'success' : 'error'}">
                    <div class="timeline-step-header">
                        <span>${htmlEscape(op.action || `Step ${idx + 1}`)}</span>
                        <span class="pill ${success ? 'good' : 'bad'}">${htmlEscape(status)}</span>
                    </div>
                    <div class="meta">${htmlEscape(meta)}</div>
                    ${op.message ? `<div class="message">${htmlEscape(op.message)}</div>` : ''}
                </div>
            `;
        }

        function buildTimelineHeartbeat(heartbeat, host) {
            if (!heartbeat) {
                const name = host?.name;
                const message = name ? `No heartbeat data for ${name} yet.` : 'No heartbeat data.';
                return `
                    <div class="timeline-heartbeat">
                        <h3>Heartbeat</h3>
                        <div class="muted-text">${htmlEscape(message)}</div>
                    </div>
                `;
            }
            return `
                <div class="timeline-heartbeat">
                    <h3>Heartbeat (${htmlEscape(formatDate(heartbeat.timestamp))})</h3>
                    <div class="pill-group">
                        ${renderHeartbeatPill('Ready', heartbeat.ready)}
                        ${renderHeartbeatPill('Local mode', heartbeat.localMode)}
                        ${renderHeartbeatPill('Local session', heartbeat.localSession)}
                    </div>
                    <div class="meta">Power: ${htmlEscape(renderPowerInfo(heartbeat.lastPower))}</div>
                    <div class="meta">Forced logoff: ${htmlEscape(renderLogoffInfo(heartbeat.lastForcedLogoff))}</div>
                </div>
            `;
        }

        function renderHeartbeatPill(label, value) {
            const state = formatBool(value);
            const cls = value === true ? 'good' : value === false ? 'soft' : 'soft';
            return `<span class="pill ${cls}">${label}: ${state}</span>`;
        }

        function renderPowerInfo(info) {
            if (!info || (!info.timestamp && !info.mode)) {
                return 'n/a';
            }
            const parts = [];
            if (info.mode) parts.push(info.mode);
            if (info.timestamp) parts.push(formatDate(info.timestamp));
            return parts.join(' @ ');
        }

        function renderLogoffInfo(info) {
            if (!info || (!info.timestamp && !info.user)) {
                return 'n/a';
            }
            const parts = [];
            if (info.user) parts.push(info.user);
            if (info.timestamp) parts.push(formatDate(info.timestamp));
            return parts.join(' · ');
        }

        function buildPhaseTitle(phase) {
            const parts = [];
            if (phase.createdAt) parts.push(formatDate(phase.createdAt));
            if (phase.message) parts.push(phase.message);
            return parts.join(' · ');
        }

        return Object.freeze({ renderTimelineMarkup, renderUpcomingReservationsMarkup });
    }

    root.LabManagerReservationRenderers = Object.freeze({ createController });
})(window);
