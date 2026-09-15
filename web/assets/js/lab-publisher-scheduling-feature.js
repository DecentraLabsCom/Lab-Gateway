(function (global) {
    'use strict';

    function createController({
        documentImpl = global.document,
        normalizePricingUnit = value => value,
        normalizePeriodUnit = value => value,
        resolveSupportedTimezones = () => [],
        resolveBrowserTimezone = () => '',
    } = {}) {
        let bound = false;
        const $ = id => documentImpl?.getElementById?.(id);

        function getDerivedBookingMode() {
            return normalizePricingUnit($('labPriceUnit')?.value || 'hour') === 'hour'
                ? 'slot'
                : 'calendar-period';
        }

        function populateAllowedPeriodUnitOptions(priceUnit = normalizePricingUnit($('labPriceUnit')?.value || 'hour')) {
            const unitSelect = $('labAllowedPeriodUnit');
            if (!unitSelect) return;

            const orderedUnits = [
                { value: 'day', label: 'days' },
                { value: 'week', label: 'weeks' },
                { value: 'month', label: '30-day months' },
            ];
            const minimumUnit = priceUnit === 'month' ? 'month' : priceUnit === 'week' ? 'week' : 'day';
            const minimumIndex = orderedUnits.findIndex(unit => unit.value === minimumUnit);
            const previous = normalizePeriodUnit(unitSelect.value);
            const options = orderedUnits.slice(Math.max(0, minimumIndex));

            unitSelect.innerHTML = '';
            options.forEach(unit => {
                const option = documentImpl.createElement('option');
                option.value = unit.value;
                option.textContent = unit.label;
                unitSelect.appendChild(option);
            });
            unitSelect.value = options.some(unit => unit.value === previous) ? previous : options[0].value;
        }

        function normalizeAllowedPeriodRange(preferredRange = {}) {
            const minInput = $('labAllowedPeriodMin');
            const maxInput = $('labAllowedPeriodMax');
            const unit = normalizePeriodUnit($('labAllowedPeriodUnit')?.value || 'day');
            if (!minInput || !maxInput) return;

            const maxByUnit = { day: 90, week: 12, month: 3 };
            const unitMax = maxByUnit[unit] || 90;
            const rawMin = Math.trunc(Number(preferredRange.min ?? minInput.value ?? 1));
            const rawMax = Math.trunc(Number(preferredRange.max ?? maxInput.value ?? rawMin));
            const normalizedMin = Math.min(Math.max(Number.isFinite(rawMin) ? rawMin : 1, 1), unitMax);
            const normalizedMax = Math.min(Math.max(Number.isFinite(rawMax) ? rawMax : normalizedMin, normalizedMin), unitMax);

            [minInput, maxInput].forEach(input => {
                input.min = '1';
                input.max = String(unitMax);
                input.step = '1';
            });
            minInput.value = String(normalizedMin);
            maxInput.min = String(normalizedMin);
            maxInput.value = String(normalizedMax);
        }

        function syncBookingModeFields() {
            const priceUnit = normalizePricingUnit($('labPriceUnit')?.value || 'hour');
            const mode = getDerivedBookingMode();
            if ($('labBookingMode')) $('labBookingMode').value = mode;
            populateAllowedPeriodUnitOptions(priceUnit);
            normalizeAllowedPeriodRange();
            documentImpl.querySelectorAll?.('.scheduling-grid').forEach(grid => {
                grid.classList.toggle('calendar-period-mode', mode === 'calendar-period');
            });
            documentImpl.querySelectorAll?.('.booking-slot-field').forEach(field => {
                field.classList.toggle('is-hidden', mode !== 'slot');
            });
            documentImpl.querySelectorAll?.('.booking-period-field').forEach(field => {
                field.classList.toggle('is-hidden', mode !== 'calendar-period');
            });
        }

        function populateTimezoneOptions() {
            const select = $('labTimezone');
            if (!select) return;
            const options = resolveSupportedTimezones();
            const browserTimezone = resolveBrowserTimezone();
            select.innerHTML = '<option value="">Select timezone</option>';
            options.forEach(timezone => {
                const option = documentImpl.createElement('option');
                option.value = timezone;
                option.textContent = timezone;
                select.appendChild(option);
            });
            select.value = options.includes(browserTimezone) ? browserTimezone : 'Europe/Madrid';
        }

        function getSelectedAllowedPeriodRange() {
            normalizeAllowedPeriodRange();
            const min = Number($('labAllowedPeriodMin')?.value || 0);
            const max = Number($('labAllowedPeriodMax')?.value || 0);
            const unit = normalizePeriodUnit($('labAllowedPeriodUnit')?.value || 'day');
            return Number.isFinite(min) && Number.isFinite(max) && min > 0 && max >= min
                ? { unit, min, max }
                : null;
        }

        function setAllowedPeriodRangeControls(range) {
            const minInput = $('labAllowedPeriodMin');
            const maxInput = $('labAllowedPeriodMax');
            const unitSelect = $('labAllowedPeriodUnit');
            if (!minInput || !maxInput || !unitSelect || !range) return;

            unitSelect.value = normalizePeriodUnit(range.unit);
            normalizeAllowedPeriodRange({ min: range.min, max: range.max });
        }

        function bind() {
            if (bound) return;
            bound = true;
            $('labPriceUnit')?.addEventListener('change', syncBookingModeFields);
            $('labAllowedPeriodUnit')?.addEventListener('change', () => normalizeAllowedPeriodRange());
        }

        function initialize() {
            bind();
            populateTimezoneOptions();
            normalizeAllowedPeriodRange();
            syncBookingModeFields();
        }

        function reset() {
            populateTimezoneOptions();
            normalizeAllowedPeriodRange();
            syncBookingModeFields();
        }

        return {
            bind,
            initialize,
            reset,
            getDerivedBookingMode,
            getSelectedAllowedPeriodRange,
            normalizeAllowedPeriodRange,
            populateAllowedPeriodUnitOptions,
            populateTimezoneOptions,
            setAllowedPeriodRangeControls,
            syncBookingModeFields,
        };
    }

    global.LabPublisherSchedulingFeature = { createController };
})(window);
