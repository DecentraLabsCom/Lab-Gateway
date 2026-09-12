/* Pure resource-value helpers shared by the Lab Publisher bootstrap. */
(function (global) {
    'use strict';

    const CREDIT_DECIMALS = 7;
    const RAW_PER_CREDIT = 10n ** BigInt(CREDIT_DECIMALS);
    const SECONDS_PER_UNIT = Object.freeze({
        minute: 60n,
        hour: 3600n,
        day: 86400n,
        week: 604800n,
        month: 2592000n,
    });
    const DISPLAY_PRICE_DECIMALS = 3;
    const WEEKDAY_OPTIONS = [
        { value: 'MONDAY', label: 'Mon' },
        { value: 'TUESDAY', label: 'Tue' },
        { value: 'WEDNESDAY', label: 'Wed' },
        { value: 'THURSDAY', label: 'Thu' },
        { value: 'FRIDAY', label: 'Fri' },
        { value: 'SATURDAY', label: 'Sat' },
        { value: 'SUNDAY', label: 'Sun' },
    ];
    const DEFAULT_TIMEZONES = [
        'UTC',
        'Europe/Madrid',
        'Europe/London',
        'Europe/Paris',
        'Europe/Berlin',
        'Europe/Rome',
        'Europe/Amsterdam',
        'America/New_York',
        'America/Chicago',
        'America/Denver',
        'America/Los_Angeles',
        'America/Mexico_City',
        'America/Bogota',
        'America/Sao_Paulo',
        'America/Argentina/Buenos_Aires',
        'Africa/Johannesburg',
        'Asia/Tokyo',
        'Asia/Seoul',
        'Asia/Shanghai',
        'Asia/Singapore',
        'Asia/Kolkata',
        'Australia/Sydney',
        'Pacific/Auckland',
    ];

    const CLASSIFICATION_SCHEMES = {
        FORD: 'OECD-FORD',
        ISCED_F: 'ISCED-F',
    };
    const CLASSIFICATION_SCHEME_VERSIONS = {
        'OECD-FORD': 'Frascati Manual 2015',
        'ISCED-F': 'ISCED-F 2013',
    };
    const FORD_FIELDS_GROUPED = {
        '1 Natural Sciences': [
            { code: '1.1', label: 'Mathematics' },
            { code: '1.2', label: 'Computer and information sciences' },
            { code: '1.3', label: 'Physical sciences' },
            { code: '1.4', label: 'Chemical sciences' },
            { code: '1.5', label: 'Earth and related environmental sciences' },
            { code: '1.6', label: 'Biological sciences' },
            { code: '1.7', label: 'Other natural sciences' },
        ],
        '2 Engineering and Technology': [
            { code: '2.1', label: 'Civil engineering' },
            { code: '2.2', label: 'Electrical engineering, electronic engineering, information engineering' },
            { code: '2.3', label: 'Mechanical engineering' },
            { code: '2.4', label: 'Chemical engineering' },
            { code: '2.5', label: 'Materials engineering' },
            { code: '2.6', label: 'Medical engineering' },
            { code: '2.7', label: 'Environmental engineering' },
            { code: '2.8', label: 'Environmental biotechnology' },
            { code: '2.9', label: 'Industrial biotechnology' },
            { code: '2.10', label: 'Nano-technology' },
            { code: '2.11', label: 'Other engineering and technologies' },
        ],
        '3 Medical and Health Sciences': [
            { code: '3.1', label: 'Basic medicine' },
            { code: '3.2', label: 'Clinical medicine' },
            { code: '3.3', label: 'Health sciences' },
            { code: '3.4', label: 'Medical biotechnology' },
            { code: '3.5', label: 'Other medical sciences' },
        ],
        '4 Agricultural and Veterinary Sciences': [
            { code: '4.1', label: 'Agriculture, forestry, and fisheries' },
            { code: '4.2', label: 'Animal and dairy science' },
            { code: '4.3', label: 'Veterinary science' },
            { code: '4.4', label: 'Agricultural biotechnology' },
            { code: '4.5', label: 'Other agricultural sciences' },
        ],
        '5 Social Sciences': [
            { code: '5.1', label: 'Psychology' },
            { code: '5.2', label: 'Economics and business' },
            { code: '5.3', label: 'Educational sciences' },
            { code: '5.4', label: 'Sociology' },
            { code: '5.5', label: 'Law' },
            { code: '5.6', label: 'Political science' },
            { code: '5.7', label: 'Social and economic geography' },
            { code: '5.8', label: 'Media and communications' },
            { code: '5.9', label: 'Other social sciences' },
        ],
        '6 Humanities and the Arts': [
            { code: '6.1', label: 'History and archaeology' },
            { code: '6.2', label: 'Languages and literature' },
            { code: '6.3', label: 'Philosophy, ethics and religion' },
            { code: '6.4', label: 'Arts' },
            { code: '6.5', label: 'Other humanities' },
        ],
    };
    const FORD_FIELDS = Object.values(FORD_FIELDS_GROUPED).flat();
    const ISCED_F_FIELDS = [
        { code: '05', label: 'Natural sciences, mathematics and statistics' },
        { code: '051', label: 'Biological and related sciences' },
        { code: '052', label: 'Environment' },
        { code: '053', label: 'Physical sciences' },
        { code: '054', label: 'Mathematics and statistics' },
        { code: '061', label: 'Information and Communication Technologies (ICTs)' },
        { code: '071', label: 'Engineering and engineering trades' },
        { code: '072', label: 'Manufacturing and processing' },
        { code: '073', label: 'Architecture and construction' },
        { code: '081', label: 'Agriculture' },
        { code: '082', label: 'Forestry' },
        { code: '083', label: 'Fisheries' },
        { code: '084', label: 'Veterinary' },
        { code: '091', label: 'Health' },
        { code: '092', label: 'Welfare' },
        { code: '031', label: 'Social and behavioural sciences' },
        { code: '032', label: 'Journalism and information' },
        { code: '041', label: 'Business and administration' },
        { code: '042', label: 'Law' },
        { code: '011', label: 'Education' },
        { code: '021', label: 'Arts' },
        { code: '022', label: 'Humanities except languages' },
        { code: '023', label: 'Languages' },
    ];
    const FORD_TO_ISCED_F_SUGGESTIONS = {
        '1.1': ['054'], '1.2': ['061'], '1.3': ['053'], '1.4': ['053', '071'], '1.5': ['052', '053'], '1.6': ['051'], '1.7': ['05'],
        '2.1': ['073', '071'], '2.2': ['071', '061'], '2.3': ['071'], '2.4': ['071', '072'], '2.5': ['071', '072'], '2.6': ['091', '071'], '2.7': ['071', '052'], '2.8': ['051', '071'], '2.9': ['072', '071'], '2.10': ['071', '053'], '2.11': ['071'],
        '3.1': ['091'], '3.2': ['091'], '3.3': ['091', '092'], '3.4': ['091', '051'], '3.5': ['091'],
        '4.1': ['081', '082', '083'], '4.2': ['081'], '4.3': ['084'], '4.4': ['081', '051'], '4.5': ['081'],
        '5.1': ['031'], '5.2': ['041', '031'], '5.3': ['011'], '5.4': ['031'], '5.5': ['042'], '5.6': ['031'], '5.7': ['031', '052'], '5.8': ['032'], '5.9': ['031'],
        '6.1': ['022'], '6.2': ['023'], '6.3': ['022'], '6.4': ['021'], '6.5': ['022'],
    };
    const FORD_BY_CODE = new Map(FORD_FIELDS.map(field => [field.code, field]));
    const ISCED_BY_CODE = new Map(ISCED_F_FIELDS.map(field => [field.code, field]));

    function normalizeConnectionUsers(connection) {
        const rawUsers = Array.isArray(connection?.users) ? connection.users : [];
        return rawUsers
            .map(user => {
                if (typeof user === 'string') return user.trim();
                if (user && typeof user === 'object') return String(user.username || user.name || '').trim();
                return '';
            })
            .filter(Boolean);
    }

    function resolveConnectionAccessKey(connection) {
        return connection?.selector || (connection?.id ? `guac:id:${connection.id}` : '');
    }

    function formatConnectionUsers(connection) {
        const users = normalizeConnectionUsers(connection);
        return users.length ? ` - ${users.join(', ')}` : '';
    }

    function resolveSupportedTimezones() {
        if (typeof Intl !== 'undefined' && typeof Intl.supportedValuesOf === 'function') {
            try {
                const values = Intl.supportedValuesOf('timeZone');
                if (Array.isArray(values) && values.length > 0) return values;
            } catch {
                // Fall through to defaults.
            }
        }
        return DEFAULT_TIMEZONES;
    }

    function resolveBrowserTimezone() {
        if (typeof Intl !== 'undefined' && typeof Intl.DateTimeFormat === 'function') {
            try {
                const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
                if (timezone && typeof timezone === 'string') return timezone;
            } catch {
                // Fall through to UTC.
            }
        }
        return 'UTC';
    }

    function parseHourlyCreditsToRaw(hourlyCredits) {
        const text = String(hourlyCredits ?? '').trim();
        if (!text) {
            throw new Error('Price is required');
        }

        const normalizedText = text.endsWith('.') ? text.slice(0, -1) : text;
        if (!/^(?:\d+|\d*\.\d+)$/.test(normalizedText)) {
            throw new Error('Price must be a non-negative number');
        }

        const [wholeRaw, fractionRaw = ''] = normalizedText.split('.');
        if (fractionRaw.length > CREDIT_DECIMALS) {
            throw new Error(`Price supports up to ${CREDIT_DECIMALS} decimal places`);
        }

        const whole = wholeRaw || '0';
        const fraction = fractionRaw.padEnd(CREDIT_DECIMALS, '0') || '0';
        return BigInt(whole) * RAW_PER_CREDIT + BigInt(fraction);
    }

    function normalizePricingUnit(unit) {
        const normalized = String(unit || 'hour').trim().toLowerCase();
        return Object.prototype.hasOwnProperty.call(SECONDS_PER_UNIT, normalized) ? normalized : 'hour';
    }

    function convertDisplayCreditsToRawPerSecond(displayCredits, unit = 'hour') {
        const rawPerUnit = parseHourlyCreditsToRaw(displayCredits);
        const seconds = SECONDS_PER_UNIT[normalizePricingUnit(unit)];
        if (rawPerUnit === 0n) return 0n;
        const base = rawPerUnit / seconds;
        const remainder = rawPerUnit % seconds;
        return remainder * 2n >= seconds ? base + 1n : base;
    }

    function formatRawPriceForUnit(rawPricePerSecond, unit = 'hour') {
        try {
            const rawPerSecond = typeof rawPricePerSecond === 'bigint'
                ? rawPricePerSecond
                : BigInt(rawPricePerSecond ?? 0);
            const seconds = SECONDS_PER_UNIT[normalizePricingUnit(unit)];
            return roundDecimalString(formatRawCredits(rawPerSecond * seconds), DISPLAY_PRICE_DECIMALS);
        } catch {
            return '0';
        }
    }

    function resolveLabPriceUnit(lab) {
        return normalizePricingUnit(
            lab?.pricing?.displayUnit
            || lab?.metadata?.pricing?.displayUnit
            || lab?.priceUnit
            || 'hour'
        );
    }

    function formatRawCredits(rawAmount) {
        const normalized = typeof rawAmount === 'bigint' ? rawAmount : BigInt(rawAmount ?? 0);
        const negative = normalized < 0n;
        const value = negative ? -normalized : normalized;
        const whole = value / RAW_PER_CREDIT;
        const fraction = (value % RAW_PER_CREDIT).toString().padStart(CREDIT_DECIMALS, '0');
        const formatted = trimTrailingZeros(`${whole.toString()}.${fraction}`);
        return negative && formatted !== '0' ? `-${formatted}` : formatted;
    }

    function roundDecimalString(value, maxFractionDigits = DISPLAY_PRICE_DECIMALS) {
        if (value === null || value === undefined) return '0';

        const text = String(value).trim();
        if (!text) return '0';

        const negative = text.startsWith('-');
        const unsigned = negative ? text.slice(1) : text;
        if (!/^\d+(?:\.\d+)?$/.test(unsigned)) {
            return '0';
        }

        const safeDigits = Math.max(0, Number(maxFractionDigits) || 0);
        const [integerPartRaw, fractionPartRaw = ''] = unsigned.split('.');
        const integerPart = integerPartRaw || '0';

        if (safeDigits === 0) {
            let roundedInteger = BigInt(integerPart);
            if ((fractionPartRaw[0] || '0') >= '5') {
                roundedInteger += 1n;
            }
            const normalized = roundedInteger.toString();
            return negative && normalized !== '0' ? `-${normalized}` : normalized;
        }

        const paddedFraction = fractionPartRaw.padEnd(safeDigits + 1, '0');
        const keptFraction = paddedFraction.slice(0, safeDigits);
        const roundingDigit = paddedFraction[safeDigits] || '0';
        const scale = 10n ** BigInt(safeDigits);

        let scaledValue = BigInt(integerPart) * scale + BigInt(keptFraction || '0');
        if (roundingDigit >= '5') {
            scaledValue += 1n;
        }

        const roundedInteger = scaledValue / scale;
        const roundedFraction = (scaledValue % scale).toString().padStart(safeDigits, '0');
        const normalized = trimTrailingZeros(`${roundedInteger.toString()}.${roundedFraction}`);
        return negative && normalized !== '0' ? `-${normalized}` : normalized;
    }

    function trimTrailingZeros(value) {
        if (value === null || value === undefined) return '0';
        const text = String(value).trim();
        if (!text) return '0';
        if (!text.includes('.')) return text;
        return text.replace(/(\.\d*?[1-9])0+$/, '$1').replace(/\.0+$/, '').replace(/\.$/, '');
    }

    async function fetchJson(url, options, request = global.fetch) {
        const res = await request(url, { credentials: 'include', ...(options || {}) });
        const rawBody = await res.text().catch(() => '');
        let body = {};
        if (rawBody) {
            try {
                body = JSON.parse(rawBody);
            } catch {
                body = { error: rawBody.trim() };
            }
        }
        if (!res.ok) {
            throw new Error(body.error || body.detail || `HTTP ${res.status}`);
        }
        return body;
    }

    function assertLabMutationSuccess(result, action) {
        if (result?.success !== true) {
            throw new Error(result?.error || `${action} failed`);
        }

        // Metadata-only updates and duplicate publications are successful
        // idempotent outcomes without a new transaction receipt.
        if (result.action === 'metadataOnly' || result.status === 'offchain_updated'
            || result.action === 'existingLab' || result.status === 'already_exists') {
            return result;
        }

        const status = String(result.status || '').trim().toLowerCase();
        const receiptSucceeded = ['0x1', '1', 'ok', 'success', 'succeeded', 'confirmed'].includes(status);
        if (!result.transactionHash || !receiptSucceeded) {
            throw new Error(`${action} transaction did not confirm on-chain`);
        }
        return result;
    }

    function getFordField(code) {
        return FORD_BY_CODE.get(String(code || '').trim()) || null;
    }

    function getIscedField(code) {
        return ISCED_BY_CODE.get(String(code || '').trim()) || null;
    }

    function normalizeClassificationEntries(value) {
        return (Array.isArray(value) ? value : [])
            .map(entry => {
                const scheme = String(entry?.scheme || '').trim();
                const code = String(entry?.code || '').trim();
                const field = scheme === CLASSIFICATION_SCHEMES.FORD
                    ? getFordField(code)
                    : scheme === CLASSIFICATION_SCHEMES.ISCED_F
                        ? getIscedField(code)
                        : null;
                if (!field) return null;
                return {
                    scheme,
                    schemeVersion: CLASSIFICATION_SCHEME_VERSIONS[scheme],
                    code: field.code,
                    label: field.label,
                };
            })
            .filter(Boolean);
    }

    function buildClassificationEntries({ fordCodes, iscedCodes = [], educationalProgramLinked = false }) {
        const seen = new Set();
        const add = (scheme, code) => {
            const field = scheme === CLASSIFICATION_SCHEMES.FORD ? getFordField(code) : getIscedField(code);
            if (!field) return null;
            const key = `${scheme}:${field.code}`;
            if (seen.has(key)) return null;
            seen.add(key);
            return {
                scheme,
                schemeVersion: CLASSIFICATION_SCHEME_VERSIONS[scheme],
                code: field.code,
                label: field.label,
            };
        };
        return [
            ...(Array.isArray(fordCodes) ? fordCodes : [fordCodes]).map(code => add(CLASSIFICATION_SCHEMES.FORD, code)),
            ...(educationalProgramLinked ? (Array.isArray(iscedCodes) ? iscedCodes : [iscedCodes]).map(code => add(CLASSIFICATION_SCHEMES.ISCED_F, code)) : []),
        ].filter(Boolean);
    }

    function getSuggestedIscedCodes(fordCodes) {
        const seen = new Set();
        (Array.isArray(fordCodes) ? fordCodes : [fordCodes]).forEach(code => {
            (FORD_TO_ISCED_F_SUGGESTIONS[String(code || '').trim()] || []).forEach(iscedCode => seen.add(iscedCode));
        });
        return [...seen];
    }

    function normalizeMaxConcurrentUsers(value, isFmu) {
        const parsed = Math.trunc(Number(value));
        const minimum = isFmu ? 2 : 1;
        return Number.isFinite(parsed) && parsed >= minimum ? parsed : minimum;
    }

    function sanitizeAvailableHours(start, end) {
        const safeStart = sanitizeTime(start);
        const safeEnd = sanitizeTime(end);
        return safeStart && safeEnd ? { start: safeStart, end: safeEnd } : {};
    }

    function sanitizeTime(value) {
        const text = String(value || '').trim();
        if (!/^\d{1,2}:\d{2}$/.test(text)) return '';
        const [hours, minutes] = text.split(':').map(Number);
        if (hours > 23 || minutes > 59) return '';
        return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
    }

    function sanitizeUnavailableWindows(windows) {
        return (Array.isArray(windows) ? windows : [])
            .map(window => {
                const startUnix = Number(window?.startUnix || 0);
                const endUnix = Number(window?.endUnix || 0);
                const reason = String(window?.reason || '').trim();
                if (!Number.isFinite(startUnix) || !Number.isFinite(endUnix) || startUnix <= 0 || endUnix <= 0) return null;
                if (!reason || startUnix >= endUnix) return null;
                return {
                    startUnix: Math.floor(startUnix),
                    endUnix: Math.floor(endUnix),
                    reason,
                };
            })
            .filter(Boolean);
    }

    function sanitizeTermsOfUse(terms) {
        const result = {};
        if (terms.url) result.url = terms.url;
        if (terms.version) result.version = terms.version;
        const effectiveDate = normalizeTermsEffectiveDate(terms.effectiveDate);
        if (effectiveDate !== null) result.effectiveDate = effectiveDate;
        if (terms.sha256) result.sha256 = terms.sha256.toLowerCase();
        return result;
    }

    function normalizeTermsEffectiveDate(value) {
        const text = String(value || '').trim();
        if (!text) return null;
        if (/^\d+$/.test(text)) {
            const epoch = Number(text);
            return Number.isSafeInteger(epoch) && epoch > 0 ? epoch : null;
        }
        const parsed = /^\d{4}-\d{2}-\d{2}$/.test(text)
            ? new Date(`${text}T00:00:00Z`)
            : new Date(text);
        return Number.isFinite(parsed.getTime()) ? Math.floor(parsed.getTime() / 1000) : null;
    }

    function normalizePeriodUnit(unit) {
        const normalized = String(unit || 'day').trim().toLowerCase().replace(/s$/, '');
        return ['day', 'week', 'month'].includes(normalized) ? normalized : 'day';
    }

    function expandAllowedDurations(range) {
        if (!range || !Number.isFinite(Number(range.min)) || !Number.isFinite(Number(range.max))) return [];
        const unit = normalizePeriodUnit(range.unit);
        const min = Math.trunc(Number(range.min));
        const max = Math.trunc(Number(range.max));
        if (min <= 0 || max < min) return [];
        return Array.from({ length: max - min + 1 }, (_, index) => ({ unit, value: min + index }));
    }

    function buildPeriodRules(range) {
        if (!range) return null;
        const daysPerUnit = { day: 1, week: 7, month: 30 };
        const unit = normalizePeriodUnit(range.unit);
        return {
            startGranularity: 'day',
            allowCustomDateRange: true,
            minDurationDays: Number(range.min) * daysPerUnit[unit],
            maxDurationDays: Number(range.max) * daysPerUnit[unit],
        };
    }

    function deriveAllowedPeriodRange(value) {
        const durations = (Array.isArray(value) ? value : [])
            .map(item => ({
                unit: normalizePeriodUnit(item?.unit),
                value: Number(item?.value),
            }))
            .filter(item => Number.isFinite(item.value) && item.value > 0);
        if (!durations.length) return null;
        const unit = durations[0].unit;
        const matching = durations.filter(item => item.unit === unit);
        const values = matching.map(item => item.value);
        return {
            unit,
            min: Math.min(...values),
            max: Math.max(...values),
        };
    }

    function resolveLabDisplayName(lab) {
        const candidates = [
            lab?.name,
            lab?.labName,
            lab?.metadataName,
            lab?.metadata?.name,
            lab?.metadata?.labName,
        ];
        const name = candidates.find(candidate => typeof candidate === 'string' && candidate.trim());
        return name || `Lab #${String(lab?.labId ?? '').trim()}`;
    }

    function optionalAttribute(traitType, value) {
        return value === null || value === undefined || value === ''
            ? []
            : [{ trait_type: traitType, value }];
    }

    function optionalNumberAttribute(traitType, value) {
        if (value === null || value === undefined || value === '') return [];
        const parsed = Number(value);
        return Number.isFinite(parsed) ? [{ trait_type: traitType, value: parsed }] : [];
    }

    function metadataAttributes(value) {
        return Array.isArray(value) ? value.filter(item => item && typeof item === 'object') : [];
    }

    function normalizeTraitType(value) {
        return String(value || '').trim().toLowerCase().replace(/[\s_-]+/g, '');
    }

    function normalizeArray(value) {
        if (Array.isArray(value)) return value.map(item => String(item ?? '').trim()).filter(Boolean);
        const text = String(value ?? '').trim();
        return text ? [text] : [];
    }

    function splitCsv(value) {
        return String(value || '').split(',').map(v => v.trim()).filter(Boolean);
    }

    function mergeMediaUrls(...values) {
        const urls = [];
        values.forEach(value => {
            normalizeArray(value).forEach(url => {
                if (!urls.includes(url)) urls.push(url);
            });
        });
        return urls;
    }

    function dateInputToUnix(value) {
        if (!value) return null;
        const parsed = new Date(`${value}T00:00:00`);
        return Number.isFinite(parsed.getTime()) ? Math.floor(parsed.getTime() / 1000) : null;
    }

    function unixToDateInput(value) {
        const timestamp = Number(value);
        if (!Number.isFinite(timestamp) || timestamp <= 0) return '';
        return new Date(timestamp * 1000).toISOString().slice(0, 10);
    }

    function guessVersionFromUrl(url) {
        const filename = String(url || '').split('/').pop() || '';
        const match = filename.match(/v(?:ersion)?[-_]?(\d+(?:\.\d+)*)/i);
        return match ? match[1] : '';
    }
    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"'`]/g, ch => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;'
        })[ch]);
    }
    function escapeAttr(value) {
        return escapeHtml(value).replace(/"/g, '&quot;');
    }

    global.LabPublisherValues = Object.freeze({
        CREDIT_DECIMALS,
        RAW_PER_CREDIT,
        escapeHtml,
        escapeAttr,
        SECONDS_PER_UNIT,
        DISPLAY_PRICE_DECIMALS,
        WEEKDAY_OPTIONS,
        DEFAULT_TIMEZONES,
        normalizeConnectionUsers,
        resolveConnectionAccessKey,
        formatConnectionUsers,
        resolveSupportedTimezones,
        resolveBrowserTimezone,
        parseHourlyCreditsToRaw,
        normalizePricingUnit,
        convertDisplayCreditsToRawPerSecond,
        formatRawPriceForUnit,
        resolveLabPriceUnit,
        formatRawCredits,
        roundDecimalString,
        trimTrailingZeros,
        fetchJson,
        assertLabMutationSuccess,
        CLASSIFICATION_SCHEMES,
        CLASSIFICATION_SCHEME_VERSIONS,
        FORD_FIELDS_GROUPED,
        FORD_FIELDS,
        ISCED_F_FIELDS,
        getFordField,
        getIscedField,
        normalizeClassificationEntries,
        buildClassificationEntries,
        getSuggestedIscedCodes,
        normalizeMaxConcurrentUsers,
        sanitizeAvailableHours,
        sanitizeTime,
        sanitizeUnavailableWindows,
        sanitizeTermsOfUse,
        normalizeTermsEffectiveDate,
        normalizePeriodUnit,
        expandAllowedDurations,
        buildPeriodRules,
        deriveAllowedPeriodRange,
        resolveLabDisplayName,
        optionalAttribute,
        optionalNumberAttribute,
        metadataAttributes,
        normalizeTraitType,
        normalizeArray,
        splitCsv,
        mergeMediaUrls,
        dateInputToUnix,
        unixToDateInput,
        guessVersionFromUrl,
    });
}(window));
