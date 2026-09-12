(function (global) {
    'use strict';

    const publisherValues = global.LabPublisherValues;
    if (!publisherValues) {
        throw new Error('LabPublisherValues must load before lab-publisher-metadata.js');
    }

    const optionalAttribute = publisherValues.optionalAttribute;
    const optionalNumberAttribute = publisherValues.optionalNumberAttribute;

    function buildMetadata({
        contentId,
        name,
        description,
        imageUrls = [],
        docs = [],
        demoEnabled = false,
        classification = [],
        educationalProgramLinked = false,
        keywords = [],
        resourceType,
        fmuFileName = '',
        unavailableWindows = [],
        priceUnit,
        rawPricePerSecond,
        bookingMode,
        timeSlots = [],
        allowedDurationRange = null,
        allowedDurations = [],
        periodRules = null,
        pricing,
        termsOfUse = {},
        opens,
        closes,
        availableDays = [],
        availableHours = {},
        maxConcurrentUsers,
        timezone = '',
        fmiVersion = '',
        simulationType = '',
        modelVariables = [],
        defaultStartTime,
        defaultStopTime,
        defaultStepSize,
    } = {}) {
        const images = Array.isArray(imageUrls) ? imageUrls : [];
        const variables = Array.isArray(modelVariables) ? modelVariables : [];
        const attributes = [
            { trait_type: 'classification', value: classification },
            { trait_type: 'classificationPrimaryScheme', value: 'OECD-FORD' },
            ...(educationalProgramLinked ? [{ trait_type: 'educationalProgramLinked', value: true }] : []),
            { trait_type: 'keywords', value: keywords },
            ...(bookingMode === 'slot' ? [{ trait_type: 'timeSlots', value: timeSlots }] : []),
            { trait_type: 'pricing', value: pricing },
            { trait_type: 'bookingMode', value: bookingMode },
            ...(allowedDurationRange ? [{ trait_type: 'allowedDurationRange', value: allowedDurationRange }] : []),
            { trait_type: 'allowedDurations', value: allowedDurations },
            ...(periodRules ? [{ trait_type: 'periodRules', value: periodRules }] : []),
            { trait_type: 'opens', value: opens },
            { trait_type: 'closes', value: closes },
            { trait_type: 'additionalImages', value: images.slice(1) },
            { trait_type: 'docs', value: Array.isArray(docs) ? docs : [] },
            { trait_type: 'availableDays', value: [...availableDays] },
            { trait_type: 'availableHours', value: availableHours },
            { trait_type: 'maxConcurrentUsers', value: maxConcurrentUsers },
            { trait_type: 'unavailableWindows', value: unavailableWindows },
            { trait_type: 'termsOfUse', value: termsOfUse },
            { trait_type: 'timezone', value: timezone },
            { trait_type: 'resourceType', value: resourceType },
            ...(resourceType === 'fmu' && fmuFileName ? [{ trait_type: 'fmuFileName', value: fmuFileName }] : []),
            ...optionalAttribute('fmiVersion', fmiVersion),
            ...optionalAttribute('simulationType', simulationType),
            ...optionalAttribute('modelVariables', variables.length ? variables : null),
            ...optionalNumberAttribute('defaultStartTime', defaultStartTime),
            ...optionalNumberAttribute('defaultStopTime', defaultStopTime),
            ...optionalNumberAttribute('defaultStepSize', defaultStepSize),
        ];
        return {
            contentId,
            name,
            description,
            image: images[0] || '',
            demoEnabled: demoEnabled === true,
            attributes,
        };
    }

    global.LabPublisherMetadata = Object.freeze({
        buildMetadata,
    });
}(window));
