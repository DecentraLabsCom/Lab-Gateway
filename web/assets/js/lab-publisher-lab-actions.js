(function (global) {
    'use strict';

    function createController({
        listElement,
        getLabs = () => [],
        getEditingLabId = () => null,
        fetchJson,
        assertLabMutationSuccess,
        renderLabActionIcon,
        escapeHtml,
        escapeAttr,
        formatRawPriceForUnit,
        resolveLabPriceUnit,
        resolveLabDisplayName,
        confirmImpl = message => global.confirm(message),
        callbacks = {},
    } = {}) {
        const {
            onEdit = () => {},
            onClearEdit = () => {},
            onReload = async () => {},
            setStatus = () => {},
        } = callbacks;
        let bound = false;

        function render(labs = getLabs()) {
            const items = Array.isArray(labs) ? labs : [];
            if (!listElement) return;
            if (!items.length) {
                listElement.classList.add('empty');
                listElement.textContent = 'No labs published by this provider wallet yet.';
                return;
            }
            listElement.classList.remove('empty');
            listElement.innerHTML = items.map(lab => {
                const displayName = resolveLabDisplayName(lab);
                const priceUnit = resolveLabPriceUnit(lab);
                return `
            <div class="lab-row">
                <div>
                    <div class="item-title">${escapeHtml(displayName)} ${Number(lab.resourceType) === 1 ? 'FMU' : 'Remote'} ${lab.listed ? '<span class="pill good">Listed</span>' : '<span class="pill soft">Draft</span>'}</div>
                    <div class="item-meta">${escapeHtml(lab.accessKey || '')} - ${escapeHtml(lab.uri || '')}</div>
                </div>
                <div class="lab-row-side">
                    <div class="item-meta">${escapeHtml(formatRawPriceForUnit(lab.price || '0', priceUnit))} credits/${escapeHtml(priceUnit)}</div>
                    <div class="lab-actions">
                        <button class="mini-btn primary" type="button" data-lab-action="edit" data-lab-id="${escapeAttr(lab.labId)}" title="Edit ${escapeAttr(displayName)}" aria-label="Edit ${escapeAttr(displayName)}">
                            ${renderLabActionIcon('edit')}
                        </button>
                        <button class="mini-btn" type="button" data-lab-action="${lab.listed ? 'unlist' : 'list'}" data-lab-id="${escapeAttr(lab.labId)}" title="${lab.listed ? 'Unlist' : 'List'} ${escapeAttr(displayName)}" aria-label="${lab.listed ? 'Unlist' : 'List'} ${escapeAttr(displayName)}">
                            ${renderLabActionIcon(lab.listed ? 'unlist' : 'list')}
                        </button>
                        <button class="mini-btn danger" type="button" data-lab-action="delete" data-lab-id="${escapeAttr(lab.labId)}" title="Delete ${escapeAttr(displayName)} on-chain" aria-label="Delete ${escapeAttr(displayName)} on-chain">
                            ${renderLabActionIcon('delete')}
                        </button>
                    </div>
                </div>
            </div>
        `;
            }).join('');
        }

        async function toggleLabListing(lab, shouldList, button) {
            button.disabled = true;
            try {
                const result = await fetchJson(`/lab-admin/labs/${encodeURIComponent(lab.labId)}/${shouldList ? 'list' : 'unlist'}`, {
                    method: 'POST',
                });
                assertLabMutationSuccess(result, shouldList ? 'List' : 'Unlist');
                setStatus(`${shouldList ? 'Listed' : 'Unlisted'} ${resolveLabDisplayName(lab)}. Tx: ${result.transactionHash || 'pending'}`, false);
                await onReload();
            } catch (err) {
                setStatus(err.message || `${shouldList ? 'List' : 'Unlist'} failed`, true);
            } finally {
                button.disabled = false;
            }
        }

        async function deleteLab(lab, button) {
            if (!confirmImpl(`Delete ${resolveLabDisplayName(lab)} on-chain? This burns the lab token and cannot be undone. Use Unlist to stop new bookings while preserving the lab record.`)) return;
            button.disabled = true;
            try {
                const result = await fetchJson(`/lab-admin/labs/${encodeURIComponent(lab.labId)}`, { method: 'DELETE' });
                assertLabMutationSuccess(result, 'Delete');
                if (getEditingLabId() === String(lab.labId)) onClearEdit();
                setStatus(`Deleted ${resolveLabDisplayName(lab)} on-chain. Gateway content is hidden and retained according to its purge policy. Tx: ${result.transactionHash || 'pending'}`, false);
                await onReload();
            } catch (err) {
                setStatus(err.message || 'Delete failed', true);
            } finally {
                button.disabled = false;
            }
        }

        async function handleListClick(event) {
            const button = event?.target?.closest?.('button[data-lab-action][data-lab-id]');
            if (!button) return;
            const labId = button.dataset.labId;
            const action = button.dataset.labAction;
            const lab = (Array.isArray(getLabs()) ? getLabs() : [])
                .find(item => String(item.labId) === String(labId));
            if (!lab) return;

            if (action === 'edit') {
                await onEdit(lab);
                return;
            }
            if (action === 'delete') {
                await deleteLab(lab, button);
                return;
            }
            if (action === 'list' || action === 'unlist') {
                await toggleLabListing(lab, action === 'list', button);
            }
        }

        function bind() {
            if (bound || !listElement) return;
            bound = true;
            listElement.addEventListener('click', handleListClick);
        }

        return Object.freeze({ bind, render });
    }

    global.LabPublisherLabActions = Object.freeze({ createController });
}(window));
