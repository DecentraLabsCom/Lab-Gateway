import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const publisherPath = new URL('../../web/assets/js/lab-publisher.js', import.meta.url);
const publisherSource = fs.readFileSync(publisherPath, 'utf8');
const publishLabSource = publisherSource.match(
    /async function publishLab\(\) \{[\s\S]*?\r?\n    \}\r?\n\r?\n    function /
);

test('new lab publication sends a unique idempotency key', () => {
    assert.ok(publishLabSource, 'publishLab function should be present');
    assert.match(publishLabSource[0], /if \(!editing\)[\s\S]*?Idempotency-Key/);
    assert.match(publisherSource, /createIdempotencyKey[\s\S]*?randomUUID/);
});

test('publisher actions use the shared Lab Manager toast service', () => {
    assert.match(publisherSource, /const toastModule = window\.LabManagerToast;/);
    assert.match(publisherSource, /if \(!toastModule\) \{[\s\S]*LabManagerToast must load before lab-publisher\.js/);
    assert.match(publisherSource, /LabManagerToast[\s\S]*getDefaultController/);
    assert.match(publisherSource, /showToast\(\`\$\{editing \? 'Laboratory updated' : 'Laboratory published'/);
});
