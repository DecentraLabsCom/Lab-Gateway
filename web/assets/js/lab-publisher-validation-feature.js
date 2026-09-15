(function (global) {
    'use strict';

    function createController({
        documentImpl = global.document,
        getContentState = () => ({}),
        getPricingState = () => ({}),
        getAvailabilityState = () => ({}),
        getBookingMode = () => 'slot',
        getAllowedPeriodRange = () => null,
        getFordField = () => null,
        expandAllowedDurations = () => [],
        splitCsv = value => String(value || '').split(',').map(item => item.trim()).filter(Boolean),
        dateInputToUnix = value => value ? Date.parse(`${value}T00:00:00Z`) / 1000 : 0,
    } = {}) {
        const $ = id => documentImpl?.getElementById?.(id);

        function validate() {
            const isFmu = $('labResourceType')?.value === '1';
            const content = getContentState();
            const pricing = getPricingState();
            const required = [
                ['Name', content.name],
                ['Description', content.description],
                ['Price', pricing.displayAmount],
                ['Access URI', $('labAccessURI')?.value?.trim() || ''],
                ['Timezone', $('labTimezone')?.value?.trim() || ''],
            ];
            const bookingMode = getBookingMode();
            if (bookingMode === 'slot') {
                required.push(
                    ['Daily Start Time', $('labAvailableHoursStart')?.value?.trim() || ''],
                    ['Daily End Time', $('labAvailableHoursEnd')?.value?.trim() || '']
                );
            }
            const missing = required.find(([, value]) => !value);
            if (missing) throw new Error(`${missing[0]} is required`);

            const availability = getAvailabilityState();
            if (!availability.selectedCategories?.some(code => getFordField(code))) {
                throw new Error('At least one valid OECD FORD field is required');
            }
            if (!availability.availableDays?.length) throw new Error('Select at least one available day');
            if (bookingMode === 'slot' && !splitCsv($('labTimeSlots')?.value).map(Number).some(Number.isFinite)) {
                throw new Error('Time Slots must include at least one duration in minutes');
            }
            if (bookingMode === 'calendar-period' && !expandAllowedDurations(getAllowedPeriodRange()).length) {
                throw new Error('Select a valid minimum and maximum period');
            }

            const opens = dateInputToUnix($('labOpens')?.value);
            const closes = dateInputToUnix($('labCloses')?.value);
            if (!opens) throw new Error('Opens is required');
            if (!closes) throw new Error('Closes is required');
            if (closes < opens) throw new Error('Closes must be after or equal to Opens');
            if (isFmu) {
                const fmuFileName = $('labFmuFileName')?.value?.trim() || '';
                if (!fmuFileName) throw new Error('FMU File Name is required');
                if (!/^[A-Za-z0-9._/-]+\.fmu$/i.test(fmuFileName)) {
                    throw new Error('FMU File Name must end with .fmu and contain only valid characters');
                }
            } else if (!/^guac:id:[1-9][0-9]*$/.test($('labAccessKey')?.value?.trim() || '')) {
                throw new Error('Connection ID is required');
            }
        }

        return { validate };
    }

    global.LabPublisherValidationFeature = { createController };
})(window);
