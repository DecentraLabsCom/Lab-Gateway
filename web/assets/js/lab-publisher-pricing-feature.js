(function (global) {
    'use strict';

    function createController({
        documentImpl = global.document,
        normalizePricingUnit = value => value,
        convertDisplayCreditsToRawPerSecond = () => 0n,
    } = {}) {
        const original = {
            rawPrice: null,
            displayPrice: null,
            priceUnit: null,
        };
        const $ = id => documentImpl?.getElementById?.(id);

        function getState() {
            const displayAmount = $('labPrice')?.value?.trim() || '';
            const displayUnit = normalizePricingUnit($('labPriceUnit')?.value || 'hour');
            return {
                displayAmount,
                displayUnit,
                rawPricePerSecond: convertDisplayCreditsToRawPerSecond(displayAmount || '0', displayUnit).toString(),
                roundingMode: 'nearest-per-second',
                billingMode: 'linear-duration',
            };
        }

        function hydrate(pricing = {}) {
            if ('displayAmount' in pricing && $('labPrice')) {
                $('labPrice').value = pricing.displayAmount ?? '';
            }
            if ('displayUnit' in pricing && $('labPriceUnit')) {
                $('labPriceUnit').value = normalizePricingUnit(pricing.displayUnit);
            }
        }

        function reset() {
            hydrate({ displayAmount: '0', displayUnit: 'hour' });
            original.rawPrice = null;
            original.displayPrice = null;
            original.priceUnit = null;
        }

        function captureOriginalEditPrice(lab) {
            original.rawPrice = String(lab?.price ?? '0');
            original.displayPrice = String($('labPrice')?.value ?? '').trim();
            original.priceUnit = normalizePricingUnit($('labPriceUnit')?.value || 'hour');
        }

        function resolvePayloadRawPrice() {
            const state = getState();
            const priceUnchangedDuringEdit = original.rawPrice !== null
                && state.displayAmount === String(original.displayPrice ?? '').trim()
                && state.displayUnit === original.priceUnit;
            return priceUnchangedDuringEdit ? original.rawPrice : state.rawPricePerSecond;
        }

        return {
            captureOriginalEditPrice,
            getState,
            hydrate,
            reset,
            resolvePayloadRawPrice,
        };
    }

    global.LabPublisherPricingFeature = { createController };
})(window);
