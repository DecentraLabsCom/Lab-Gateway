(function (root) {
    'use strict';

    function requireModule(module, name) {
        if (!module) throw new Error(`${name} must load before the reservations feature`);
        return module;
    }

    function createController({
        documentImpl = root.document,
        fetchImpl,
        normalizePagination,
        escapeHtml,
        htmlEscape,
        formatDate,
        formatBool,
        showToast,
        getManagedLabs = () => [],
        resolveLabDisplayName = lab => `Lab #${lab?.labId ?? ''}`,
        confirmImpl = message => root.confirm?.(message),
        dateTimeFormatCtor = root.Intl?.DateTimeFormat,
        dateCtor = root.Date,
        now = () => Date.now(),
        logger = console,
    }) {
        const reservationValuesModule = requireModule(root.LabManagerReservationValues, 'LabManagerReservationValues');
        const reservationRenderersModule = requireModule(root.LabManagerReservationRenderers, 'LabManagerReservationRenderers');
        const timelineModule = requireModule(root.LabManagerTimeline, 'LabManagerTimeline');
        const actionableReservationsModule = requireModule(root.LabManagerActionableReservations, 'LabManagerActionableReservations');
        const $ = selector => documentImpl?.querySelector?.(selector) || null;

        const timelineInput = $('#timelineReservationId');
        const timelineButton = $('#loadTimelineBtn');
        const timelineResult = $('#timelineResult');
        const reservationList = $('#upcomingReservationsList');
        const reservationStatus = $('#upcomingReservationsStatus');
        const reservationValuesController = reservationValuesModule.createController({
            dateTimeFormatCtor,
            dateCtor,
            formatDate,
            now,
        });
        const reservationRenderersController = reservationRenderersModule.createController({
            escapeHtml,
            htmlEscape,
            formatDate,
            formatBool,
            formatReservationDate: reservationValuesController.formatReservationDate,
            formatRange: reservationValuesController.formatRange,
            isReservationWindowEnded: reservationValuesController.isReservationWindowEnded,
            normalizeReservationStatus: reservationValuesController.normalizeReservationStatus,
            cancellationButtonLabel: reservationValuesController.cancellationButtonLabel,
            shortAddress: reservationValuesController.shortAddress,
            resolveReservationLabDisplayName,
        });

        function resolveReservationLabDisplayName(reservation) {
            const directName = [reservation?.labName, reservation?.name]
                .find(candidate => typeof candidate === 'string' && candidate.trim());
            if (directName) return directName.trim();
            const managedLab = getManagedLabs()
                .find(lab => String(lab?.labId ?? '') === String(reservation?.labId ?? ''));
            return resolveLabDisplayName(managedLab || reservation);
        }

        const timelineController = timelineModule.createController({
            timelineInput,
            timelineBtn: timelineButton,
            timelineResult,
            fetchImpl,
            normalizePagination,
            renderTimelineMarkup: (...args) => reservationRenderersController.renderTimelineMarkup(...args),
            showToast,
            logger,
        });
        const actionableReservationsController = actionableReservationsModule.createController({
            listEl: reservationList,
            statusEl: reservationStatus,
            fetchImpl,
            renderMarkup: (...args) => reservationRenderersController.renderUpcomingReservationsMarkup(...args),
            escapeHtml,
            normalizeReservationStatus: reservationValuesController.normalizeReservationStatus,
            cancellationButtonLabel: reservationValuesController.cancellationButtonLabel,
            showToast,
            confirmImpl,
            logger,
        });

        function initialize() {
            timelineController.bind();
            actionableReservationsController.bind();
        }

        return Object.freeze({
            getManagedLabs,
            hasReservationList: () => Boolean(reservationList),
            initialize,
            loadActionableReservations: actionableReservationsController.load,
            resolveReservationLabDisplayName,
            timelineButton,
        });
    }

    root.LabManagerReservationsFeature = Object.freeze({ createController });
})(window);
