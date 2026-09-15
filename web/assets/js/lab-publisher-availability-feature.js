(function (global) {
    'use strict';

    function createController({
        documentImpl = global.document,
        fordFieldsGrouped = {},
        iscedFields = [],
        getSuggestedIscedCodes = () => [],
        weekdayOptions = [],
        escapeHtml = value => String(value ?? ''),
        escapeAttr = value => String(value ?? ''),
        createClientId = () => `${Date.now()}-${Math.random()}`,
        dateCtor = Date,
        toDatetimeLocal = unixSeconds => {
            const timestamp = Number(unixSeconds);
            if (!Number.isFinite(timestamp) || timestamp <= 0) return '';
            const date = new dateCtor(timestamp * 1000);
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');
            return `${year}-${month}-${day}T${hours}:${minutes}`;
        },
    } = {}) {
        const state = {
            selectedCategories: [],
            selectedIscedCodes: [],
            iscedSelectionTouched: false,
            educationalProgramLinked: false,
            availableDays: ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY'],
            unavailableWindows: [],
        };
        let bound = false;
        const $ = id => documentImpl?.getElementById?.(id);

        function toggleCategoryMenu() {
            const select = $('labCategorySelect');
            const menu = $('labCategoryMenu');
            if (!select || !menu) return;
            const open = !menu.classList.contains('open');
            menu.classList.toggle('open', open);
            select.classList.toggle('open', open);
            select.setAttribute('aria-expanded', String(open));
            if (open) {
                renderCategoryChips();
                const rect = select.getBoundingClientRect();
                menu.style.left = `${rect.left}px`;
                menu.style.top = `${rect.bottom + 4}px`;
            }
        }

        function closeCategoryMenu() {
            const menu = $('labCategoryMenu');
            const select = $('labCategorySelect');
            menu?.classList.remove('open');
            select?.classList.remove('open');
            select?.setAttribute('aria-expanded', 'false');
        }

        function toggleCategory(category) {
            state.selectedCategories = state.selectedCategories.includes(category)
                ? state.selectedCategories.filter(item => item !== category)
                : [...state.selectedCategories, category];
            renderCategoryChips();
            renderIscedSuggestions();
        }

        function renderCategoryMenu() {
            const menu = $('labCategoryMenu');
            if (!menu) return;
            menu.innerHTML = Object.entries(fordFieldsGrouped).map(([groupName, categories]) => `
            <div class="multi-select-group">
                <div class="multi-select-group-title">${escapeHtml(groupName)}</div>
                ${categories.map(category => `
                    <label class="multi-select-option">
                        <input type="checkbox" value="${escapeAttr(category.code)}" autocomplete="off">
                        <span>${escapeHtml(category.label)}</span>
                        <small>${escapeHtml(category.code)}</small>
                    </label>
                `).join('')}
            </div>
        `).join('');
            menu.querySelectorAll('.multi-select-option').forEach(option => {
                option.addEventListener('click', event => event.stopPropagation());
            });
            menu.querySelectorAll('input[type="checkbox"]').forEach(input => {
                input.checked = false;
                input.addEventListener('click', event => event.stopPropagation());
                input.addEventListener('change', event => {
                    event.stopPropagation();
                    toggleCategory(input.value);
                });
            });
        }

        function renderCategoryChips() {
            const chips = $('labCategoryChips');
            const menu = $('labCategoryMenu');
            if (!chips) return;
            chips.innerHTML = state.selectedCategories.length
                ? state.selectedCategories.map(category => `
                <span class="chip">
                    ${escapeHtml(fordFieldsGrouped && Object.values(fordFieldsGrouped).flat().find(field => field.code === category)?.label || category)}
                    <button type="button" data-category="${escapeAttr(category)}" aria-label="Remove ${escapeAttr(category)}">&times;</button>
                </span>
            `).join('')
                : '<span class="placeholder">Select one or more OECD FORD fields...</span>';
            chips.querySelectorAll('button[data-category]').forEach(button => {
                button.addEventListener('click', event => {
                    event.stopPropagation();
                    toggleCategory(button.dataset.category);
                });
            });
            menu?.querySelectorAll('input[type="checkbox"]').forEach(input => {
                input.checked = state.selectedCategories.includes(input.value);
            });
        }

        function renderIscedSuggestions() {
            const linked = $('labEducationalProgramLinked');
            const target = $('labIscedSuggestions');
            if (!linked || !target) return;
            linked.checked = state.educationalProgramLinked;
            target.hidden = !state.educationalProgramLinked;
            if (!state.educationalProgramLinked) {
                target.innerHTML = '';
                return;
            }
            const suggested = getSuggestedIscedCodes(state.selectedCategories);
            const codes = suggested.length ? suggested : iscedFields.map(field => field.code);
            target.innerHTML = codes.map(code => {
                const field = iscedFields.find(item => item.code === code);
                if (!field) return '';
                const checked = state.selectedIscedCodes.includes(code);
                return `<button type="button" class="mini-btn ${checked ? 'primary' : ''}" data-isced-code="${escapeAttr(code)}">${escapeHtml(code)} ${escapeHtml(field.label)}</button>`;
            }).join('');
            target.querySelectorAll('button[data-isced-code]').forEach(button => {
                button.addEventListener('click', () => {
                    const code = button.dataset.iscedCode;
                    state.selectedIscedCodes = state.selectedIscedCodes.includes(code)
                        ? state.selectedIscedCodes.filter(item => item !== code)
                        : [...state.selectedIscedCodes, code];
                    state.iscedSelectionTouched = true;
                    renderIscedSuggestions();
                });
            });
        }

        function renderDayToggles() {
            const target = $('labAvailableDays');
            if (!target) return;
            target.innerHTML = weekdayOptions.map(day => `
            <button type="button" data-day="${day.value}" class="${state.availableDays.includes(day.value) ? 'active' : ''}">
                ${day.label}
            </button>
        `).join('');
            target.querySelectorAll('button[data-day]').forEach(button => {
                button.addEventListener('click', () => {
                    const day = button.dataset.day;
                    state.availableDays = state.availableDays.includes(day)
                        ? state.availableDays.filter(item => item !== day)
                        : [...state.availableDays, day];
                    renderDayToggles();
                });
            });
        }

        function addUnavailableWindow() {
            state.unavailableWindows.push({
                clientId: createClientId(),
                startUnix: null,
                endUnix: null,
                reason: '',
            });
            renderUnavailableWindows();
        }

        function updateUnavailableWindow(index, field, value) {
            const current = state.unavailableWindows[index];
            if (!current) return;
            if (field === 'startUnix' || field === 'endUnix') {
                current[field] = value ? Math.floor(new dateCtor(value).getTime() / 1000) : null;
                return;
            }
            current[field] = value;
        }

        function renderUnavailableWindows() {
            const target = $('labUnavailableWindows');
            if (!target) return;
            target.innerHTML = state.unavailableWindows.length
                ? state.unavailableWindows.map((window, index) => `
                <div class="unavailable-window" data-index="${index}">
                    <div class="form-grid">
                        <label class="field">
                            <span>Starts</span>
                            <input type="datetime-local" data-field="startUnix" value="${escapeAttr(toDatetimeLocal(window.startUnix))}">
                        </label>
                        <label class="field">
                            <span>Ends</span>
                            <input type="datetime-local" data-field="endUnix" value="${escapeAttr(toDatetimeLocal(window.endUnix))}">
                        </label>
                        <label class="field">
                            <span>Reason</span>
                            <input type="text" data-field="reason" placeholder="Reason (e.g., Maintenance, Calibration)" value="${escapeAttr(window.reason || '')}">
                        </label>
                        <label class="field action-field">
                            <span>Remove</span>
                            <button class="mini-btn danger" type="button" data-remove-window="${index}">
                                <i class="fas fa-trash"></i> Remove
                            </button>
                        </label>
                    </div>
                </div>
            `).join('')
                : '<div class="hint">No unavailable windows configured.</div>';

            target.querySelectorAll('.unavailable-window').forEach(row => {
                const index = Number(row.dataset.index);
                row.querySelectorAll('[data-field]').forEach(input => {
                    input.addEventListener('change', () => updateUnavailableWindow(index, input.dataset.field, input.value));
                    input.addEventListener('input', () => {
                        if (input.dataset.field === 'reason') updateUnavailableWindow(index, input.dataset.field, input.value);
                    });
                });
            });
            target.querySelectorAll('[data-remove-window]').forEach(button => {
                button.addEventListener('click', () => {
                    state.unavailableWindows.splice(Number(button.dataset.removeWindow), 1);
                    renderUnavailableWindows();
                });
            });
        }

        function bind() {
            if (bound) return;
            bound = true;
            const categorySelect = $('labCategorySelect');
            const categoryMenu = $('labCategoryMenu');
            const linked = $('labEducationalProgramLinked');
            const addWindowButton = $('labAddUnavailableWindow');
            categorySelect?.addEventListener('click', toggleCategoryMenu);
            categorySelect?.addEventListener('keydown', event => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    toggleCategoryMenu();
                }
                if (event.key === 'Escape') closeCategoryMenu();
            });
            linked?.addEventListener('change', () => {
                state.educationalProgramLinked = linked.checked;
                if (state.educationalProgramLinked) {
                    if (!state.selectedIscedCodes.length && !state.iscedSelectionTouched) {
                        state.selectedIscedCodes = getSuggestedIscedCodes(state.selectedCategories);
                    }
                } else {
                    state.selectedIscedCodes = [];
                }
                renderIscedSuggestions();
            });
            documentImpl?.addEventListener?.('click', event => {
                const menu = $('labCategoryMenu');
                if (categorySelect && menu && !categorySelect.contains(event.target) && !menu.contains(event.target)) {
                    closeCategoryMenu();
                }
            });
            categoryMenu?.addEventListener('click', event => event.stopPropagation());
            addWindowButton?.addEventListener('click', addUnavailableWindow);
        }

        function initialize() {
            bind();
            renderCategoryMenu();
            renderCategoryChips();
            renderIscedSuggestions();
            renderDayToggles();
            renderUnavailableWindows();
        }

        function hydrate({
            selectedCategories,
            selectedIscedCodes,
            iscedSelectionTouched,
            educationalProgramLinked,
            availableDays,
            unavailableWindows,
        } = {}) {
            if (Array.isArray(selectedCategories)) state.selectedCategories = [...selectedCategories];
            if (Array.isArray(selectedIscedCodes)) state.selectedIscedCodes = [...selectedIscedCodes];
            if (iscedSelectionTouched !== undefined) state.iscedSelectionTouched = Boolean(iscedSelectionTouched);
            if (educationalProgramLinked !== undefined) state.educationalProgramLinked = Boolean(educationalProgramLinked);
            if (Array.isArray(availableDays)) state.availableDays = [...availableDays];
            if (Array.isArray(unavailableWindows)) {
                state.unavailableWindows = unavailableWindows.map(window => ({ ...window, clientId: createClientId() }));
            }
            renderCategoryChips();
            renderIscedSuggestions();
            renderDayToggles();
            renderUnavailableWindows();
        }

        function reset() {
            state.selectedCategories = [];
            state.selectedIscedCodes = [];
            state.iscedSelectionTouched = false;
            state.educationalProgramLinked = false;
            state.availableDays = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY'];
            state.unavailableWindows = [];
            closeCategoryMenu();
            renderCategoryChips();
            renderIscedSuggestions();
            renderDayToggles();
            renderUnavailableWindows();
        }

        function getState() {
            return {
                selectedCategories: [...state.selectedCategories],
                selectedIscedCodes: [...state.selectedIscedCodes],
                iscedSelectionTouched: state.iscedSelectionTouched,
                educationalProgramLinked: state.educationalProgramLinked,
                availableDays: [...state.availableDays],
                unavailableWindows: state.unavailableWindows.map(window => ({ ...window })),
            };
        }

        return Object.freeze({
            getAvailableDays: () => [...state.availableDays],
            getSelectedCategories: () => [...state.selectedCategories],
            getSelectedIscedCodes: () => [...state.selectedIscedCodes],
            getState,
            getUnavailableWindows: () => state.unavailableWindows.map(window => ({ ...window })),
            hydrate,
            initialize,
            reset,
        });
    }

    global.LabPublisherAvailabilityFeature = Object.freeze({ createController });
}(window));
