(function (root) {
    'use strict';

    const CHUNK_JSON = 0x4e4f534a;
    const BASE_UNIT_KEYS = ['kg', 'm', 's', 'A', 'K', 'mol', 'cd', 'rad'];
    const OUTPUT_TARGETS = [
        'position.x', 'position.y', 'position.z',
        'translation.x', 'translation.y', 'translation.z', 'translation',
        'rotation.x', 'rotation.y', 'rotation.z', 'rotation',
        'scale.x', 'scale.y', 'scale.z', 'scale', 'weights', 'visible', 'material.color',
    ];
    const INPUT_TARGETS = [
        'position.x', 'position.y', 'position.z',
        'translation.x', 'translation.y', 'translation.z',
        'rotation.x', 'rotation.y', 'rotation.z',
    ];

    function readGlb(file, FileReaderCtor = root.FileReader) {
        return new Promise((resolve, reject) => {
            if (!file || file.size < 20 || file.size > 52428800) {
                reject(new Error('Choose a GLB between 20 bytes and 50 MiB.'));
                return;
            }
            const reader = new FileReaderCtor();
            reader.onerror = () => reject(new Error('The GLB file could not be read.'));
            reader.onload = () => {
                try {
                    const bytes = new Uint8Array(reader.result);
                    const view = new DataView(reader.result);
                    if (view.getUint32(0, true) !== 0x46546c67 || view.getUint32(4, true) !== 2
                        || view.getUint32(8, true) !== bytes.byteLength) {
                        throw new Error('The file is not a valid glTF 2.0 binary (GLB).');
                    }
                    let offset = 12;
                    const chunks = [];
                    let json = null;
                    while (offset + 8 <= bytes.byteLength) {
                        const length = view.getUint32(offset, true);
                        const type = view.getUint32(offset + 4, true);
                        offset += 8;
                        if (length % 4 || offset + length > bytes.byteLength) {
                            throw new Error('The GLB contains an invalid chunk.');
                        }
                        const data = bytes.slice(offset, offset + length);
                        if (type === CHUNK_JSON) {
                            if (json) throw new Error('The GLB contains multiple JSON chunks.');
                            json = JSON.parse(new TextDecoder().decode(data).replace(/\u0000+\s*$/, '').trim());
                            chunks.push({ type, data: null });
                        } else {
                            chunks.push({ type, data });
                        }
                        offset += length;
                    }
                    if (offset !== bytes.byteLength || !json || !Array.isArray(json.nodes)) {
                        throw new Error('The GLB has no usable glTF node list.');
                    }
                    resolve({ json, chunks });
                } catch (error) {
                    reject(error instanceof Error ? error : new Error('The GLB could not be parsed.'));
                }
            };
            reader.readAsArrayBuffer(file);
        });
    }

    function writeGlb(parsed, originalFile, FileCtor = root.File) {
        const encoder = new TextEncoder();
        const text = encoder.encode(JSON.stringify(parsed.json));
        const jsonLength = (text.byteLength + 3) & ~3;
        const chunkBuffers = parsed.chunks.map((chunk) => {
            if (chunk.type !== CHUNK_JSON) return { type: chunk.type, data: chunk.data };
            const padded = new Uint8Array(jsonLength);
            padded.fill(0x20);
            padded.set(text);
            return { type: CHUNK_JSON, data: padded };
        });
        const totalLength = 12 + chunkBuffers.reduce((size, chunk) => size + 8 + chunk.data.byteLength, 0);
        const output = new Uint8Array(totalLength);
        const view = new DataView(output.buffer);
        view.setUint32(0, 0x46546c67, true);
        view.setUint32(4, 2, true);
        view.setUint32(8, totalLength, true);
        let offset = 12;
        for (const chunk of chunkBuffers) {
            view.setUint32(offset, chunk.data.byteLength, true);
            view.setUint32(offset + 4, chunk.type, true);
            output.set(chunk.data, offset + 8);
            offset += 8 + chunk.data.byteLength;
        }
        return new FileCtor([output], originalFile.name, {
            type: 'model/gltf-binary',
            lastModified: Date.now(),
        });
    }

    function tokens(value) {
        return String(value || '')
            .normalize('NFKD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .split(/[^a-z0-9]+/)
            .filter((token) => token.length > 1);
    }

    function suggestionScore(nodeName, variable) {
        const nodeTokens = new Set(tokens(nodeName));
        if (!nodeTokens.size) return 0;
        const enumNames = Array.isArray(variable.enumItems) ? variable.enumItems.map((item) => item?.name || item?.description) : [];
        const fields = [variable.name, variable.displayName, variable.description, variable.quantity, ...enumNames];
        let score = 0;
        for (const field of fields) {
            for (const token of new Set(tokens(field))) {
                if (nodeTokens.has(token)) score += field === variable.name ? 4 : 1;
            }
        }
        return score;
    }

    function numericVariable(variable) {
        return /^(real|float32|float64|int8|int16|int32|int64|uint8|uint16|uint32|uint64)$/i.test(String(variable.type || ''));
    }

    function unitScaleSuggestion(variable, target, metadata, metersPerSceneUnit) {
        const unitName = String(variable.unit || '').trim();
        const unit = (metadata.unitDefinitions || []).find((entry) => entry.name === unitName);
        const base = unit?.baseUnit;
        if (!base) return null;
        const isTranslation = /^(position|translation)\.[xyz]$/.test(target);
        const isRotation = /^rotation\.[xyz]$/.test(target);
        if (!isTranslation && !isRotation) return null;
        const expected = isTranslation ? 'm' : 'rad';
        if (BASE_UNIT_KEYS.some((key) => key !== expected && Number(base[key] || 0) !== 0)
            || Number(base[expected] || 0) !== 1
            || Number(base.offset || 0) !== 0) return null;
        const factor = Number(base.factor ?? 1);
        if (!Number.isFinite(factor) || factor === 0) return null;
        const scale = isTranslation ? factor / metersPerSceneUnit : factor;
        return Number.isFinite(scale) && scale !== 0 ? scale : null;
    }

    function element(tag, text, className, documentImpl) {
        const node = documentImpl.createElement(tag);
        if (text !== undefined) node.textContent = text;
        if (className) node.className = className;
        return node;
    }

    function createSelect(options, selected, documentImpl) {
        const select = element('select', undefined, '', documentImpl);
        for (const [value, label] of options) {
            const option = element('option', label, '', documentImpl);
            option.value = value;
            select.append(option);
        }
        if (selected !== undefined) select.value = selected;
        return select;
    }

    function variableLabel(variable) {
        const descriptor = [variable.displayName, variable.quantity, variable.displayUnit || variable.unit, variable.type]
            .map((value) => String(value || '').trim())
            .filter(Boolean)
            .join(' · ');
        const states = Array.isArray(variable.enumItems)
            ? variable.enumItems.slice(0, 8)
                .map((item) => `${item.name || item.description || item.value}=${item.value}`)
                .filter(Boolean)
                .join(', ')
            : '';
        return `${variable.causality}: ${variable.name}${descriptor ? ` — ${descriptor}` : ''}${states ? ` — states ${states}` : ''}`;
    }

    function createEditor({ panel, file, metadata, documentImpl = root.document, onApply }) {
        panel.replaceChildren();
        panel.hidden = false;
        const variables = Array.isArray(metadata?.modelVariables) ? metadata.modelVariables : [];
        if (!variables.length) {
            panel.append(element('p', 'This FMU has no declared input/output variables available for GLB bindings.', '', documentImpl));
            return;
        }
        let parsed;
        const intro = element('p', 'Connect FMI inputs and outputs to GLB nodes. Suggestions use names, quantities and units; every binding requires your review before it is written.', '', documentImpl);
        panel.append(intro);
        const sceneUnits = element('label', 'Metres per scene unit ', 'field', documentImpl);
        const metersInput = element('input', undefined, '', documentImpl);
        metersInput.type = 'number';
        metersInput.min = '0.000001';
        metersInput.max = '1000000';
        metersInput.step = 'any';
        metersInput.value = '1';
        metersInput.setAttribute('aria-label', 'Metres per scene unit');
        sceneUnits.append(metersInput);
        panel.append(sceneUnits);
        panel.append(element('small', 'Set this from the GLB scale before adding bindings; unit-based suggestions use it for translation axes.', 'muted-text', documentImpl));
        const content = element('div', undefined, 'fmi-glb-binding-editor', documentImpl);
        panel.append(content);
        const footer = element('div', undefined, 'actions inline-actions mt-3', documentImpl);
        const applyButton = element('button', 'Apply bindings to selected GLB', 'primary-btn', documentImpl);
        applyButton.type = 'button';
        applyButton.disabled = true;
        footer.append(applyButton);
        const status = element('small', 'Reading GLB nodes…', 'muted-text', documentImpl);
        footer.append(status);
        panel.append(footer);

        function render() {
            content.replaceChildren();
            const nodes = parsed.json.nodes;
            if (nodes.length > 3000) {
                status.textContent = 'This GLB has over 3,000 nodes. Reduce the scene before authoring bindings here.';
                applyButton.disabled = true;
                return;
            }
            const validVariables = variables.filter((variable) => typeof variable?.name === 'string'
                && ['input', 'output'].includes(variable.causality));
            const inputVariableNames = new Set(validVariables
                .filter((variable) => variable.causality === 'input')
                .map((variable) => variable.name));
            const outputDependencies = new Map(
                (Array.isArray(metadata.modelStructure?.outputs) ? metadata.modelStructure.outputs : [])
                    .filter((entry) => typeof entry?.name === 'string' && Array.isArray(entry.dependencyNames))
                    .map((entry) => [entry.name, entry.dependencyNames.filter((name) => inputVariableNames.has(name))]),
            );
            nodes.forEach((node, index) => {
                const bindings = Array.isArray(node.extras?.fmiBindings) ? node.extras.fmiBindings : [];
                const group = element('details', undefined, 'fmi-glb-binding-node', documentImpl);
                group.dataset.nodeIndex = String(index);
                group.open = bindings.length > 0;
                const summary = element('summary', `${index}: ${node.name || `Node ${index}`}`, '', documentImpl);
                group.append(summary);
                const rows = element('div', undefined, '', documentImpl);
                group.append(rows);
                const addBinding = (existing = null, suggested = false) => {
                    const row = element('div', undefined, 'fmi-glb-binding-row', documentImpl);
                    row.bindingTemplate = existing;
                    const existingVariable = variables.find((variable) => variable.name === existing?.variable);
                    const direction = createSelect([
                        ['', 'Select direction'], ['output', 'FMI output to scene'], ['input', 'FMI input from drag'],
                    ], existing?.causality || existingVariable?.causality || '', documentImpl);
                    const originalVariable = existing?.variable || '';
                    const variableSelect = createSelect([['', 'Select FMI variable']], '', documentImpl);
                    const dependencyHint = element('small', '', 'muted-text fmi-glb-dependency-hint', documentImpl);
                    dependencyHint.hidden = true;
                    const targetSelect = createSelect([['', 'Select scene target']], existing?.target || '', documentImpl);
                    const scaleInput = element('input', undefined, '', documentImpl);
                    scaleInput.type = 'number'; scaleInput.step = 'any'; scaleInput.placeholder = 'scale (default 1)';
                    const offsetInput = element('input', undefined, '', documentImpl);
                    offsetInput.type = 'number'; offsetInput.step = 'any'; offsetInput.placeholder = 'offset (default 0)';
                    const mapInput = element('input', undefined, '', documentImpl);
                    mapInput.type = 'text'; mapInput.placeholder = 'valueMap (visible booleans / color strings)';
                    mapInput.title = 'Exact String(FMI value) keys; for example {"0":false,"1":true} for visible.';
                    mapInput.value = existing?.valueMap ? JSON.stringify(existing.valueMap) : '';
                    const indicesInput = element('input', undefined, '', documentImpl);
                    indicesInput.type = 'text'; indicesInput.placeholder = 'FMI array indices, e.g. 0, 2';
                    indicesInput.value = Array.isArray(existing?.indices) ? existing.indices.join(', ') : '';
                    const indexInput = element('input', undefined, '', documentImpl);
                    indexInput.type = 'number'; indexInput.min = '0'; indexInput.step = '1';
                    indexInput.placeholder = 'Morph target index';
                    if (Number.isInteger(existing?.index)) indexInput.value = String(existing.index);
                    const remove = element('button', 'Remove', 'ghost-btn', documentImpl);
                    remove.type = 'button';

                    const refreshVariables = () => {
                        const causality = direction.value;
                        variableSelect.replaceChildren(element('option', 'Select FMI variable', '', documentImpl));
                        variableSelect.options[0].value = '';
                        const choices = validVariables
                            .filter((variable) => variable.causality === causality
                                && (causality !== 'input' || numericVariable(variable)))
                            .sort((left, right) => suggestionScore(node.name, right) - suggestionScore(node.name, left));
                        choices.forEach((variable, index) => {
                            const isSuggested = index === 0 && suggestionScore(node.name, variable) > 0;
                            const option = element('option', `${isSuggested ? 'Suggested: ' : ''}${variableLabel(variable)}`, '', documentImpl);
                            option.value = variable.name;
                            variableSelect.append(option);
                        });
                        if (originalVariable && choices.some((variable) => variable.name === originalVariable)) {
                            variableSelect.value = originalVariable;
                        } else if (suggested && choices.length && suggestionScore(node.name, choices[0]) > 0) {
                            variableSelect.value = choices[0].name;
                        }
                    };
                    const refreshTargets = () => {
                        const previousTarget = targetSelect.value || existing?.target || '';
                        const choices = direction.value === 'input' ? INPUT_TARGETS : OUTPUT_TARGETS;
                        targetSelect.replaceChildren(element('option', 'Select scene target', '', documentImpl));
                        targetSelect.options[0].value = '';
                        for (const target of choices) {
                            const option = element('option', target, '', documentImpl);
                            option.value = target;
                            targetSelect.append(option);
                        }
                        if (previousTarget && choices.includes(previousTarget)) targetSelect.value = previousTarget;
                        mapInput.hidden = !['visible', 'material.color'].includes(targetSelect.value);
                        indexInput.hidden = targetSelect.value !== 'weights';
                        const variable = validVariables.find((entry) => entry.name === variableSelect.value);
                        indicesInput.hidden = !Array.isArray(variable?.dimensions) || variable.dimensions.length === 0
                            || ['translation', 'rotation', 'scale'].includes(targetSelect.value);
                    };
                    const refreshDependencyHint = () => {
                        const dependencies = direction.value === 'output'
                            ? outputDependencies.get(variableSelect.value) || []
                            : [];
                        dependencyHint.hidden = dependencies.length === 0;
                        dependencyHint.textContent = dependencies.length
                            ? `FMI declares dependencies on: ${dependencies.join(', ')}. Review these inputs; this is only a suggestion.`
                            : '';
                    };
                    direction.addEventListener('change', () => { refreshVariables(); refreshTargets(); refreshDependencyHint(); suggestScale(); });
                    variableSelect.addEventListener('change', () => { refreshTargets(); refreshDependencyHint(); suggestScale(); });
                    targetSelect.addEventListener('change', () => { refreshTargets(); suggestScale(); });
                    function suggestScale() {
                        const variable = validVariables.find((entry) => entry.name === variableSelect.value);
                        const metersPerSceneUnit = Number(metersInput.value);
                        const scale = variable && Number.isFinite(metersPerSceneUnit) && metersPerSceneUnit > 0
                            ? unitScaleSuggestion(variable, targetSelect.value, metadata, metersPerSceneUnit)
                            : null;
                        if (scale !== null && (!scaleInput.value || scaleInput.dataset.unitSuggested === 'true')) {
                            scaleInput.value = String(scale);
                            scaleInput.dataset.unitSuggested = 'true';
                            scaleInput.title = 'Suggested using the FMI unit definition; review before applying.';
                        } else if (scale === null && scaleInput.dataset.unitSuggested === 'true') {
                            scaleInput.value = '';
                            delete scaleInput.dataset.unitSuggested;
                            scaleInput.removeAttribute('title');
                        }
                    }
                    scaleInput.addEventListener('input', () => {
                        delete scaleInput.dataset.unitSuggested;
                        scaleInput.removeAttribute('title');
                    });
                    refreshVariables();
                    refreshTargets();
                    refreshDependencyHint();
                    if (existing && Number.isFinite(Number(existing.scale))) scaleInput.value = String(existing.scale);
                    if (existing && Number.isFinite(Number(existing.offset))) offsetInput.value = String(existing.offset);
                    remove.addEventListener('click', () => row.remove());
                    row.append(direction, variableSelect, targetSelect, scaleInput, offsetInput, mapInput, indicesInput, indexInput, remove, dependencyHint);
                    rows.append(row);
                };

                bindings.forEach((binding) => addBinding(binding));
                const addButton = element('button', bindings.length ? 'Add binding' : 'Add FMI binding', 'ghost-btn', documentImpl);
                addButton.type = 'button';
                addButton.addEventListener('click', () => addBinding(null, true));
                group.append(addButton);
                content.append(group);
            });
            status.textContent = `${nodes.length} GLB nodes; ${validVariables.length} FMI inputs/outputs available${metadata.variablesTruncated ? ' (first 4,096 only)' : ''}.`;
            applyButton.disabled = false;
        }

        metersInput.addEventListener('input', () => {
            for (const row of content.querySelectorAll('.fmi-glb-binding-row')) {
                const [, variableSelect, targetSelect, scaleInput] = row.children;
                if (scaleInput.dataset.unitSuggested !== 'true') continue;
                const variable = variables.find((entry) => entry.name === variableSelect.value);
                const metersPerSceneUnit = Number(metersInput.value);
                const scale = variable && Number.isFinite(metersPerSceneUnit) && metersPerSceneUnit > 0
                    ? unitScaleSuggestion(variable, targetSelect.value, metadata, metersPerSceneUnit)
                    : null;
                if (scale === null) {
                    scaleInput.value = '';
                    delete scaleInput.dataset.unitSuggested;
                    scaleInput.removeAttribute('title');
                } else {
                    scaleInput.value = String(scale);
                }
            }
        });

        readGlb(file).then((result) => {
            parsed = result;
            render();
        }).catch((error) => {
            status.textContent = error.message;
            applyButton.disabled = true;
        });

        applyButton.addEventListener('click', () => {
            if (!parsed) return;
            try {
                const groupsByNodeIndex = new Map(Array.from(content.querySelectorAll('.fmi-glb-binding-node'), (group) => [
                    Number(group.dataset.nodeIndex), group,
                ]));
                for (let nodeIndex = 0; nodeIndex < parsed.json.nodes.length; nodeIndex += 1) {
                    const node = parsed.json.nodes[nodeIndex];
                    const rows = groupsByNodeIndex.get(nodeIndex);
                    if (!rows) continue;
                    const bindings = [];
                    for (const row of rows.querySelectorAll('.fmi-glb-binding-row')) {
                        const controls = Array.from(row.children);
                        const [direction, variable, target, scale, offset, valueMap, indices, index] = controls;
                        if (!direction.value || !variable.value || !target.value) continue;
                        const item = { ...(row.bindingTemplate || {}), variable: variable.value, target: target.value };
                        if (scale.value !== '' && Number.isFinite(Number(scale.value))) item.scale = Number(scale.value);
                        else delete item.scale;
                        if (offset.value !== '' && Number.isFinite(Number(offset.value))) item.offset = Number(offset.value);
                        else delete item.offset;
                        if (valueMap.value.trim() && ['visible', 'material.color'].includes(target.value)) {
                            const parsedMap = JSON.parse(valueMap.value);
                            const entries = parsedMap && typeof parsedMap === 'object' && !Array.isArray(parsedMap)
                                ? Object.entries(parsedMap)
                                : [];
                            const validMap = entries.length > 0 && entries.length <= 128
                                && entries.every(([key, mapped]) => key.length <= 128
                                    && (target.value === 'visible'
                                        ? typeof mapped === 'boolean'
                                        : target.value === 'material.color'
                                            && ((typeof mapped === 'string' && mapped.trim().length > 0)
                                                || (Number.isInteger(mapped) && mapped >= 0 && mapped <= 0xffffff))));
                            if (!validMap) throw new Error('valueMap must contain 1 to 128 short keys mapped to booleans for visible or colors for material.color.');
                            if (target.value === 'visible' && item.visibleWhenGreaterThanOrEqual != null) {
                                throw new Error('A visible valueMap cannot be combined with a numeric threshold.');
                            }
                            item.valueMap = parsedMap;
                        } else {
                            delete item.valueMap;
                        }
                        if (indices.value.trim()) {
                            const coordinates = indices.value.split(',').map((entry) => Number(entry.trim()));
                            if (coordinates.some((coordinate) => !Number.isSafeInteger(coordinate) || coordinate < 0)) {
                                throw new Error('FMI array indices must be non-negative integers separated by commas.');
                            }
                            if (['translation', 'rotation', 'scale'].includes(target.value)) {
                                delete item.indices;
                            } else {
                                const variableDescription = variables.find((entry) => entry.name === variable.value);
                                const dimensions = Array.isArray(variableDescription?.dimensions) ? variableDescription.dimensions : [];
                                if (dimensions.length && coordinates.length !== dimensions.length) {
                                    throw new Error(`FMI array indices require ${dimensions.length} coordinates for ${variable.value}.`);
                                }
                                for (let axis = 0; axis < dimensions.length; axis += 1) {
                                    const dimension = dimensions[axis];
                                    const dimensionVariable = variables.find((entry) => entry.name === dimension.variableName
                                        || (dimension.valueReference != null && String(entry.valueReference) === String(dimension.valueReference)));
                                    const limit = Number.isSafeInteger(dimension.start)
                                        ? dimension.start
                                        : (Number.isSafeInteger(dimensionVariable?.max) ? dimensionVariable.max : null);
                                    if (limit !== null && coordinates[axis] >= limit) {
                                        throw new Error(`FMI array index ${coordinates[axis]} is outside dimension ${axis} of ${variable.value}.`);
                                    }
                                }
                                item.indices = coordinates;
                            }
                        } else delete item.indices;
                        if (target.value === 'weights' && index.value !== '') {
                            const morphIndex = Number(index.value);
                            if (!Number.isSafeInteger(morphIndex) || morphIndex < 0) {
                                throw new Error('Morph target index must be a non-negative integer used with weights.');
                            }
                            item.index = morphIndex;
                        } else delete item.index;
                        bindings.push(item);
                    }
                    if (bindings.length) {
                        node.extras = { ...(node.extras || {}), fmiBindings: bindings };
                    } else if (node.extras) {
                        const { fmiBindings: _removed, ...remaining } = node.extras;
                        node.extras = remaining;
                    }
                }
                const updatedFile = writeGlb(parsed, file);
                onApply(updatedFile);
                status.textContent = 'Bindings written to the selected GLB file. Gateway validation runs when you sync the AAS.';
            } catch (error) {
                status.textContent = error instanceof SyntaxError
                    ? 'valueMap must be a JSON object.'
                    : (error.message || 'Bindings could not be written.');
            }
        });
    }

    root.LabManagerFmiGlbBindings = Object.freeze({ createEditor });
})(window);
