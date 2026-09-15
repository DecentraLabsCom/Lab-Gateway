(function (global) {
    'use strict';

    function createController({
        documentImpl = global.document,
        RESOURCE_TYPES = { LAB: 'lab', FMU: 'fmu' },
        syncResourceTypeFields = () => {},
        validate = () => {},
        ensureContentId = () => '',
        getContentState = () => ({}),
        getMediaState = () => ({ imageMode: 'link', docMode: 'link' }),
        getUploadedAssets = () => ({ images: [], docs: [] }),
        getAvailabilityState = () => ({}),
        getPricingState = () => ({}),
        resolvePayloadRawPrice = () => '0',
        getBookingMode = () => 'slot',
        getAllowedPeriodRange = () => null,
        getTermsState = () => ({}),
        getModelVariables = () => [],
        buildClassificationEntries = () => [],
        sanitizeUnavailableWindows = value => value,
        expandAllowedDurations = () => [],
        buildPeriodRules = () => null,
        sanitizeTermsOfUse = value => value,
        sanitizeAvailableHours = (start, end) => ({ start, end }),
        normalizeMaxConcurrentUsers = value => value,
        dateInputToUnix = value => value,
        splitCsv = value => String(value || '').split(',').map(item => item.trim()).filter(Boolean),
        buildMetadataPayload = value => value,
    } = {}) {
        const $ = id => documentImpl?.getElementById?.(id);

        function buildLabPayload() {
            syncResourceTypeFields();
            const setupMode = $('labSetupMode')?.value || '';
            const isFmu = $('labResourceType')?.value === '1';
            if (isFmu && !$('labFmuFileName')?.value?.trim()) {
                throw new Error('FMU File Name is required');
            }
            const payload = {
                setupMode,
                listImmediately: $('labListImmediately')?.value === 'true',
                price: resolvePayloadRawPrice(),
                accessURI: $('labAccessURI')?.value?.trim() || '',
                accessKey: $('labAccessKey')?.value?.trim() || '',
                resourceType: Number($('labResourceType')?.value),
                creatorPucHash: $('labCreatorPucHash')?.value?.trim() || '',
            };
            if (setupMode === 'quick') {
                payload.metadataUrl = $('labMetadataUrl')?.value?.trim() || '';
            } else {
                payload.metadata = buildMetadata();
            }
            return payload;
        }

        function buildMetadata() {
            syncResourceTypeFields();
            validate();
            const availability = getAvailabilityState();
            const media = getMediaState();
            const uploadedAssets = media.imageMode === 'link' && media.docMode === 'link'
                ? { images: [], docs: [] }
                : getUploadedAssets();
            const content = getContentState({
                imageMode: media.imageMode,
                docMode: media.docMode,
                uploadedImages: media.imageMode === 'link' ? [] : uploadedAssets.images,
                uploadedDocs: media.docMode === 'link' ? [] : uploadedAssets.docs,
            });
            const classification = buildClassificationEntries({
                fordCodes: availability.selectedCategories,
                iscedCodes: availability.selectedIscedCodes,
                educationalProgramLinked: availability.educationalProgramLinked,
            });
            const resourceType = $('labResourceType')?.value === '1' ? RESOURCE_TYPES.FMU : RESOURCE_TYPES.LAB;
            const bookingMode = getBookingMode();
            const timeSlots = splitCsv($('labTimeSlots')?.value).map(Number).filter(Number.isFinite);
            const allowedDurationRange = bookingMode === 'calendar-period'
                ? getAllowedPeriodRange()
                : null;
            const allowedDurations = bookingMode === 'calendar-period'
                ? expandAllowedDurations(allowedDurationRange)
                : timeSlots.map(slot => ({ unit: 'minute', value: slot }));
            const periodRules = bookingMode === 'calendar-period'
                ? buildPeriodRules(allowedDurationRange)
                : null;
            return buildMetadataPayload({
                contentId: ensureContentId(),
                name: content.name,
                description: content.description,
                imageUrls: content.imageUrls,
                docs: content.docs,
                demoEnabled: content.demoEnabled,
                classification,
                educationalProgramLinked: availability.educationalProgramLinked,
                keywords: content.keywords,
                resourceType,
                fmuFileName: $('labFmuFileName')?.value?.trim() || '',
                unavailableWindows: sanitizeUnavailableWindows(availability.unavailableWindows),
                bookingMode,
                timeSlots,
                allowedDurationRange,
                allowedDurations,
                periodRules,
                pricing: getPricingState(),
                termsOfUse: sanitizeTermsOfUse(getTermsState()),
                opens: dateInputToUnix($('labOpens')?.value),
                closes: dateInputToUnix($('labCloses')?.value),
                availableDays: availability.availableDays,
                availableHours: sanitizeAvailableHours(
                    $('labAvailableHoursStart')?.value,
                    $('labAvailableHoursEnd')?.value
                ),
                maxConcurrentUsers: normalizeMaxConcurrentUsers(
                    $('labMaxConcurrentUsers')?.value,
                    resourceType === RESOURCE_TYPES.FMU
                ),
                timezone: $('labTimezone')?.value?.trim() || '',
                fmiVersion: $('labFmiVersion')?.value?.trim() || '',
                simulationType: $('labSimulationType')?.value?.trim() || '',
                modelVariables: getModelVariables(),
                defaultStartTime: $('labDefaultStartTime')?.value,
                defaultStopTime: $('labDefaultStopTime')?.value,
                defaultStepSize: $('labDefaultStepSize')?.value,
            });
        }

        return { buildLabPayload, buildMetadata };
    }

    global.LabPublisherPayloadFeature = { createController };
})(window);
