(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', () => {
        const scopeEl = document.getElementById('lmIncomeScope');
        const statusEl = document.getElementById('lmIncomeStatus');
        const rowsEl = document.getElementById('lmIncomeRows');
        const refreshButton = document.getElementById('lmIncomeRefreshBtn');
        if (!scopeEl || !statusEl || !rowsEl || !refreshButton) return;

        const metrics = {
            confirmedReservations: { element: document.getElementById('lmIncomeConfirmed'), count: true },
            potentialProviderShare: { element: document.getElementById('lmIncomePotential') },
            accrued: { element: document.getElementById('lmIncomeAccrued') },
            unbatched: { element: document.getElementById('lmIncomeUnbatched') },
            queued: { element: document.getElementById('lmIncomeQueued') },
            inProcess: { element: document.getElementById('lmIncomeInProcess') },
            paid: { element: document.getElementById('lmIncomePaid') }
        };
        const amountFields = [
            ['potentialProviderShare', 'potentialProviderShareRaw'],
            ['accrued', 'accruedRaw'],
            ['unbatched', 'unbatchedRaw'],
            ['queued', 'queuedRaw'],
            ['inProcess', 'inProcessRaw'],
            ['paid', 'paidRaw']
        ];
        let requestInFlight = null;

        function rawAmount(row, field, rawField) {
            const raw = String(row?.[rawField] ?? '');
            if (/^\d+$/.test(raw)) return BigInt(raw);
            const display = String(row?.[field] ?? '0');
            const match = display.match(/^(\d+)(?:\.(\d{0,7}))?$/);
            if (!match) return 0n;
            return BigInt(match[1]) * 10000000n + BigInt((match[2] || '').padEnd(7, '0') || '0');
        }

        function formatCredits(raw) {
            return `${raw / 10000000n}.${(raw % 10000000n).toString().padStart(7, '0')}`;
        }

        function setEmptyRows(message) {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.colSpan = 9;
            cell.textContent = message;
            row.appendChild(cell);
            rowsEl.replaceChildren(row);
        }

        function render(report) {
            const rows = Array.isArray(report.rows) ? report.rows : [];
            const gatewayId = String(report.gatewayId || 'This Gateway');
            const departmentName = String(report.departmentName || '').trim();
            scopeEl.textContent = departmentName
                ? `Department / group: ${departmentName} · Gateway: ${gatewayId}`
                : `Gateway: ${gatewayId}`;

            const totals = Object.fromEntries(amountFields.map(([field]) => [field, 0n]));
            let confirmed = 0n;
            rows.forEach(row => {
                confirmed += /^\d+$/.test(String(row.confirmedReservations ?? ''))
                    ? BigInt(String(row.confirmedReservations))
                    : 0n;
                amountFields.forEach(([field, rawField]) => {
                    totals[field] += rawAmount(row, field, rawField);
                });
            });

            Object.entries(metrics).forEach(([field, metric]) => {
                if (!metric.element) return;
                metric.element.textContent = metric.count ? confirmed.toString() : formatCredits(totals[field]);
            });

            if (!rows.length) {
                setEmptyRows('No income events have been indexed for this Gateway yet.');
            } else {
                const bodyRows = rows.map(row => {
                    const tr = document.createElement('tr');
                    const values = [
                        row.labId ? `Lab #${row.labId}` : 'Unknown lab',
                        String(row.confirmedReservations || 0),
                        ...amountFields.map(([field]) => String(row[field] || '0.0000000')),
                        String(row.invalidated || '0.0000000')
                    ];
                    values.forEach(value => {
                        const td = document.createElement('td');
                        td.textContent = value;
                        tr.appendChild(td);
                    });
                    return tr;
                });
                rowsEl.replaceChildren(...bodyRows);
            }

            const unresolved = Number(report.unresolvedBatchCount || 0);
            const mismatches = Number(report.scopeReferenceMismatchCount || 0);
            statusEl.textContent = `Amounts are service credits. Paid externally means a payment proof was recorded. Tracking starts at block ${report.trackingStartBlock || 'the recent lookback'}; first confirmation: ${report.firstObservedConfirmationBlock || 'none'}. ${unresolved} batch(es) need source reconciliation (${report.unresolvedBatchAmount || '0.0000000'} credits); ${mismatches} settlement scope reference(s) need review.`;
        }

        async function loadIncome() {
            if (requestInFlight) return requestInFlight;
            refreshButton.disabled = true;
            statusEl.textContent = 'Loading the read-only Gateway income report...';
            requestInFlight = (async () => {
                const response = await fetch('/lab-admin/billing/provider-income', {
                    method: 'GET',
                    credentials: 'same-origin',
                    cache: 'no-store',
                    headers: { Accept: 'application/json' }
                });
                const body = await response.json().catch(() => null);
                if (!response.ok) {
                    throw new Error(body?.error || `Income report request failed (HTTP ${response.status})`);
                }
                if (!body || body.success !== true) {
                    throw new Error(body?.error || 'Income report is unavailable');
                }
                render(body);
            })().catch(error => {
                scopeEl.textContent = 'Gateway scope unavailable';
                Object.values(metrics).forEach(metric => {
                    if (metric.element) metric.element.textContent = '--';
                });
                setEmptyRows('Income report unavailable.');
                statusEl.textContent = error.message || 'Income report unavailable';
            }).finally(() => {
                requestInFlight = null;
                refreshButton.disabled = false;
            });
            return requestInFlight;
        }

        refreshButton.addEventListener('click', loadIncome);
        document.addEventListener('lab-manager:tab-activated', event => {
            if (event.detail?.tab === 'income') loadIncome();
        });
    });
})();
