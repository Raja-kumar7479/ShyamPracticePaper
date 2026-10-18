(function () {
    'use strict';

    var state = {
        descriptionId: null,
        test: null,
        sections: [],
        images: { statement_image: null, input_image: null, example_image: null, schema_image_path: null }
    };

    function el(id) { return document.getElementById(id); }

    function message(text, kind) {
        var box = el('codingMessage');
        if (!box) return;
        box.className = 'alert alert-' + (kind || 'info');
        box.textContent = text;
        box.classList.remove('is-hidden');
        if (kind === 'success') {
            setTimeout(function () { box.classList.add('is-hidden'); }, 4000);
        }
    }

    function send(url, method, body) {
        return fetch(url, {
            method: method || 'GET',
            headers: { 'Content-Type': 'application/json' },
            body: body ? JSON.stringify(body) : undefined
        }).then(function (res) {
            return res.json().catch(function () { return {}; })
                .then(function (data) { return { ok: res.ok, data: data }; });
        });
    }

    function ask(opts) {
        return window.adminConfirm ? window.adminConfirm(opts) : Promise.resolve(window.confirm(opts.title));
    }

    var picked = {};
    var shown = [];

    function paintPicked() {
        var ids = shown.filter(function (id) { return picked[id]; });
        if (el('cdpSelectedCount')) el('cdpSelectedCount').textContent = ids.length + ' selected';
        var btn = el('cdpDeleteSelected');
        if (btn) {
            btn.disabled = ids.length === 0;
            btn.innerHTML = '<i class="fas fa-trash me-1"></i>Delete selected' + (ids.length ? ' (' + ids.length + ')' : '');
        }
        var all = el('cdpSelectAll');
        if (all) {
            all.checked = shown.length > 0 && ids.length === shown.length;
            all.indeterminate = ids.length > 0 && ids.length < shown.length;
            all.disabled = shown.length === 0;
        }
        return ids;
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : text;
        return div.innerHTML;
    }

    function currentSectionType() {
        var select = el('cdpTargetSection');
        if (!select || !select.value) return '';
        var found = state.sections.filter(function (s) { return String(s.id) === String(select.value); })[0];
        return found ? found.section_type : '';
    }

    window.codingPanelOpen = function (description) {
        state.descriptionId = description.id;
        var container = el('codingManagementContainer');
        container.classList.remove('is-hidden');
        container.style.display = '';
        el('codingManagementHeader').innerHTML =
            '<i class="fas fa-code me-1"></i> Coding Questions &mdash; ' +
            escapeHtml(description.subject_title || description.test_key);
        loadPanel();
        container.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    window.codingPanelClose = function () {
        var container = el('codingManagementContainer');
        if (container) {
            container.classList.add('is-hidden');
            container.style.display = 'none';
        }
    };

    function loadPanel() {
        send('/api/coding-panel/' + state.descriptionId).then(function (r) {
            if (!r.ok || !r.data.success) {
                message((r.data && r.data.message) || 'Could not open the coding editor.', 'danger');
                return;
            }
            state.test = r.data.test;
            state.sections = r.data.sections || [];
            renderSections();
            renderTestLanguages();
        }).catch(function () { message('Network error. Please try again.', 'danger'); });
    }

    function testLanguages() {
        var raw = (state.test && state.test.allowed_languages) || '';
        return raw.split(',').map(function (l) { return l.trim(); }).filter(Boolean);
    }

    function applyTestLanguageLimit() {
        var allowed = testLanguages();
        document.querySelectorAll('#cdpLangs input').forEach(function (b) {
            var permitted = !allowed.length || allowed.indexOf(b.value) !== -1;
            b.disabled = !permitted;
            if (!permitted) b.checked = false;
            var chip = b.closest('.cdp-chip');
            if (chip) chip.style.opacity = permitted ? '' : '.45';
        });
    }

    function renderTestLanguages() {
        var allowed = testLanguages();
        document.querySelectorAll('#cdpTestLangs input').forEach(function (b) {
            b.checked = allowed.indexOf(b.value) !== -1;
        });
        var note = el('cdpTestLangsNote');
        if (note) note.textContent = allowed.length ? 'Editor shows: ' + allowed.join(', ') : 'All languages allowed';
        applyTestLanguageLimit();
    }

    var saveLangsBtn = el('cdpSaveTestLangs');
    if (saveLangsBtn) {
        saveLangsBtn.addEventListener('click', function () {
            var langs = Array.prototype.map.call(
                document.querySelectorAll('#cdpTestLangs input:checked'), function (b) { return b.value; });
            saveLangsBtn.disabled = true;
            send('/api/coding-panel/' + state.descriptionId + '/languages', 'PUT', { languages: langs })
                .then(function (r) {
                    saveLangsBtn.disabled = false;
                    if (!r.ok || !r.data.success) {
                        message((r.data && r.data.message) || 'Could not save the languages.', 'danger');
                        return;
                    }
                    if (state.test) state.test.allowed_languages = langs.join(',');
                    renderTestLanguages();
                    message(langs.length ? 'Languages saved: ' + langs.join(', ') : 'All languages allowed.', 'success');
                })
                .catch(function () { saveLangsBtn.disabled = false; message('Network error. Please try again.', 'danger'); });
        });
    }

    function renderSections() {
        var body = document.querySelector('#cdpSectionsTable tbody');
        if (!body) return;
        if (!state.sections.length) {
            body.innerHTML = '<tr><td colspan="6" class="text-center text-muted">' +
                'No sections yet. Add one above to start.</td></tr>';
        } else {
            body.innerHTML = state.sections.map(function (s, i) {
                return '<tr>' +
                    '<td>' + (i + 1) + '</td>' +
                    '<td><span class="cdp-pill cdp-pill--' + s.section_type + '">' +
                        s.section_type.toUpperCase() + '</span></td>' +
                    '<td>' + escapeHtml(s.title) + '</td>' +
                    '<td>' + s.duration_min + ' min</td>' +
                    '<td>' + s.question_count + '</td>' +
                    '<td class="text-end"><button type="button" class="btn btn-sm btn-outline-danger" ' +
                        'data-del-section="' + s.id + '"><i class="fas fa-trash"></i></button></td>' +
                    '</tr>';
            }).join('');
        }

        ['cdpTargetSection', 'cdpViewSection'].forEach(function (id) {
            var select = el(id);
            if (!select) return;
            var previous = select.value;
            select.innerHTML = state.sections.length
                ? state.sections.map(function (s) {
                    return '<option value="' + s.id + '">' + escapeHtml(s.title) +
                           ' (' + s.section_type + ')</option>';
                  }).join('')
                : '<option value="">-- no sections yet --</option>';
            if (previous) select.value = previous;
        });

        applySectionType();
        renderQuestions();
    }

    var typePick = el('cdpTypePick');
    if (typePick) {
        typePick.addEventListener('change', function () {
            typePick.querySelectorAll('.cdp-type').forEach(function (label) {
                label.classList.toggle('is-active', label.querySelector('input').checked);
            });
        });
    }

    var addSectionBtn = el('cdpAddSectionBtn');
    if (addSectionBtn) {
        addSectionBtn.addEventListener('click', function () {
            var picked = document.querySelector('input[name="cdpSectionType"]:checked');
            addSectionBtn.disabled = true;
            send('/api/coding-panel/' + state.descriptionId + '/sections', 'POST', {
                title: el('cdpSecTitle').value,
                section_type: picked ? picked.value : '',
                duration_min: el('cdpSecDuration').value
            }).then(function (r) {
                if (r.ok && r.data.success) {
                    state.sections = r.data.sections || [];
                    el('cdpSecTitle').value = '';
                    renderSections();
                    message('Section added.', 'success');
                } else {
                    message(r.data.message || 'Could not add the section.', 'danger');
                }
            }).catch(function () { message('Network error. Please try again.', 'danger'); })
              .finally(function () { addSectionBtn.disabled = false; });
        });
    }

    var sectionsTable = el('cdpSectionsTable');
    if (sectionsTable) {
        sectionsTable.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-del-section]');
            if (!btn) return;
            var sid = btn.getAttribute('data-del-section');
            var sec = state.sections.filter(function (x) { return String(x.id) === String(sid); })[0] || {};
            ask({
                tone: 'danger',
                title: 'Delete the section "' + (sec.title || 'this section') + '"?',
                message: 'The section and every question inside it (test cases, starter code, images) will be removed.',
                note: 'This cannot be undone.',
                confirmText: 'Delete section'
            }).then(function (ok) {
                if (!ok) return;
                send('/api/coding-panel/sections/' + sid, 'DELETE')
                    .then(function (r) {
                        if (r.ok && r.data.success) { loadPanel(); message(r.data.message || 'Section deleted.', r.data.message && r.data.message.indexOf('unpublished') > -1 ? 'warning' : 'success'); }
                        else { message((r.data && r.data.message) || 'Could not delete.', 'danger'); }
                    }).catch(function () { message('Network error. Please try again.', 'danger'); });
            });
        });
    }

    function currentSectionId() {
        var sel = el('cdpTargetSection');
        return sel ? sel.value : '';
    }

    function applyBulkBox(type) {
        var box = el('cdpBulkBox');
        if (!box) return;
        var sid = currentSectionId();
        var show = type === 'coding' && sid;
        box.classList.toggle('is-hidden', !show);
        if (!show) return;
        var base = '/api/coding-panel/sections/' + sid + '/bulk/template';
        var csv = el('cdpBulkCsvTpl'), xlsx = el('cdpBulkXlsxTpl');
        if (csv) csv.setAttribute('href', base);
        if (xlsx) xlsx.setAttribute('href', base + '?fmt=xlsx');
    }

    function syncCompareUI() {
        var sel = el('cdpCompareMode');
        if (!sel) return;
        var mode = sel.value;
        var box = el('cdpFloatTolBox');
        if (box) box.style.display = mode === 'float' ? '' : 'none';
        var hint = el('cdpCompareHint');
        if (hint) hint.textContent = mode === 'float'
            ? 'Numbers are compared within the tolerance; other text must match.'
            : mode === 'unordered'
            ? 'Output lines may come back in any order.'
            : 'Output is matched exactly (whitespace-trimmed).';
    }
    if (el('cdpCompareMode')) el('cdpCompareMode').addEventListener('change', syncCompareUI);

    function applySectionType() {
        var type = currentSectionType();
        var editor = el('cdpEditor');
        var hint = el('cdpEditorHint');
        applyBulkBox(type);
        if (!editor) return;

        if (!type) {
            editor.classList.add('is-hidden');
            if (hint) hint.textContent = 'Create a section first, then choose it here.';
            return;
        }
        editor.classList.remove('is-hidden');
        if (hint) {
            hint.textContent = type === 'coding'
                ? 'Coding section: write the problem, then add the test cases that grade it.'
                : type === 'sql'
                ? 'SQL section: give the sandbox schema and the solution query.'
                : 'Web section: give the starter files and the checks that grade the page.';
        }
        document.querySelectorAll('.cdp-only').forEach(function (node) {
            var applies = node.getAttribute('data-only').split(' ');
            node.classList.toggle('is-hidden', applies.indexOf(type) === -1);
        });
        if (type === 'coding' && !document.querySelectorAll('#cdpTestcases .cdp-row').length) {
            addRow('cdpTestcaseTpl', 'cdpTestcases');
        }
        if (type === 'web' && !document.querySelectorAll('#cdpAssertions .cdp-row').length) {
            addRow('cdpAssertionTpl', 'cdpAssertions');
        }
    }

    ['cdpTargetSection', 'cdpViewSection'].forEach(function (id) {
        var select = el(id);
        if (!select) return;
        select.addEventListener('change', function () {
            if (id === 'cdpTargetSection') { resetEditor(); applySectionType(); }
            else renderQuestions();
        });
    });

    var cdpBulkFile = el('cdpBulkFile');
    if (cdpBulkFile) {
        cdpBulkFile.addEventListener('change', function () {
            var file = cdpBulkFile.files && cdpBulkFile.files[0];
            var out = el('cdpBulkResult');
            var sid = currentSectionId();
            if (!file || !sid) { cdpBulkFile.value = ''; return; }
            var data = new FormData();
            data.append('file', file);
            if (out) out.innerHTML = '<div class="alert alert-info py-2 mb-0">Checking the file...</div>';
            fetch('/api/coding-panel/sections/' + sid + '/bulk/upload', { method: 'POST', body: data })
                .then(function (res) { return res.json().catch(function () { return {}; }); })
                .then(function (json) {
                    if (json && json.success) {
                        var skipped = (json.skipped || []).map(function (t) { return '<li>' + escapeHtml(t) + '</li>'; }).join('');
                        if (out) out.innerHTML = '<div class="alert ' + (json.imported ? 'alert-success' : 'alert-info') + ' py-2 mb-0">' +
                            escapeHtml(json.message || ('Imported ' + json.imported + ' question(s).')) +
                            (skipped ? '<ul class="mb-0 mt-1 small">' + skipped + '</ul>' : '') + '</div>';
                        loadPanel();
                    } else {
                        var items = (json.errors || []).map(function (e) {
                            return '<li>' + escapeHtml(e) + '</li>';
                        }).join('');
                        if (out) out.innerHTML = '<div class="alert alert-danger py-2 mb-0">' +
                            escapeHtml((json && json.message) || 'Upload failed.') +
                            (items ? '<ul class="mb-0 mt-1">' + items + '</ul>' : '') + '</div>';
                    }
                })
                .catch(function () {
                    if (out) out.innerHTML = '<div class="alert alert-danger py-2 mb-0">Network error. Please try again.</div>';
                })
                .finally(function () { cdpBulkFile.value = ''; });
        });
    }

    document.querySelectorAll('#codingManagementContainer .cdp-modes').forEach(function (bar) {
        bar.addEventListener('click', function (e) {
            var btn = e.target.closest('.cdp-mode');
            if (!btn) return;
            var part = bar.closest('.cdp-part');
            bar.querySelectorAll('.cdp-mode').forEach(function (b) {
                b.classList.toggle('is-active', b === btn);
            });
            var mode = btn.getAttribute('data-mode');
            part.querySelectorAll('.cdp-body').forEach(function (body) {
                body.classList.toggle('is-hidden', body.getAttribute('data-mode') !== mode);
            });
        });
    });

    function showMode(partName, mode) {
        var part = document.querySelector('#codingManagementContainer .cdp-part[data-part="' + partName + '"]');
        if (!part) return;
        var btn = part.querySelector('.cdp-mode[data-mode="' + mode + '"]');
        if (btn) btn.click();
    }

    function renderPreview(slot) {
        var box = document.querySelector('#codingManagementContainer .cdp-preview[data-slot="' + slot + '"]');
        if (!box) return;
        box.innerHTML = '';
        if (!state.images[slot]) return;
        var img = document.createElement('img');
        img.src = state.images[slot];
        var remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn btn-sm btn-outline-danger';
        remove.innerHTML = '<i class="fas fa-trash"></i> Remove';
        remove.addEventListener('click', function () {
            state.images[slot] = null;
            renderPreview(slot);
        });
        box.appendChild(img);
        box.appendChild(remove);
    }

    var crop = { slot: null, image: null, ops: [], tool: 'crop', sel: null, drag: null, modal: null };

    function openCropper(slot, file) {
        var reader = new FileReader();
        reader.onload = function (ev) {
            var img = new Image();
            img.onload = function () {
                crop.slot = slot;
                crop.image = img;
                crop.ops = [];
                crop.sel = null;
                drawCanvas();
                if (!crop.modal) crop.modal = new bootstrap.Modal(el('cdpCropModal'));
                crop.modal.show();
            };
            img.src = ev.target.result;
        };
        reader.readAsDataURL(file);
    }

    function renderToCanvas(canvas) {
        var work = document.createElement('canvas');
        work.width = crop.image.width;
        work.height = crop.image.height;
        work.getContext('2d').drawImage(crop.image, 0, 0);

        crop.ops.forEach(function (op) {
            var ctx = work.getContext('2d');
            if (op.type === 'hide') {
                ctx.fillStyle = '#fff';
                ctx.fillRect(op.x, op.y, op.w, op.h);
            } else if (op.type === 'crop') {
                var next = document.createElement('canvas');
                next.width = Math.max(1, Math.round(op.w));
                next.height = Math.max(1, Math.round(op.h));
                next.getContext('2d').drawImage(work, op.x, op.y, op.w, op.h,
                                                0, 0, next.width, next.height);
                work = next;
            } else if (op.type === 'rotate') {
                var rot = document.createElement('canvas');
                rot.width = work.height;
                rot.height = work.width;
                var rctx = rot.getContext('2d');
                rctx.translate(rot.width / 2, rot.height / 2);
                rctx.rotate(Math.PI / 2);
                rctx.drawImage(work, -work.width / 2, -work.height / 2);
                work = rot;
            }
        });

        canvas.width = work.width;
        canvas.height = work.height;
        canvas.getContext('2d').drawImage(work, 0, 0);
        return work;
    }

    function drawCanvas() {
        var canvas = el('cdpCanvas');
        if (!canvas || !crop.image) return;
        renderToCanvas(canvas);
        if (crop.sel) {
            var ctx = canvas.getContext('2d');
            ctx.save();
            ctx.strokeStyle = crop.tool === 'hide' ? '#d32f2f' : '#2e7d32';
            ctx.lineWidth = Math.max(2, canvas.width / 400);
            ctx.setLineDash([8, 6]);
            ctx.strokeRect(crop.sel.x, crop.sel.y, crop.sel.w, crop.sel.h);
            ctx.restore();
        }
    }

    function canvasPoint(e) {
        var canvas = el('cdpCanvas');
        var rect = canvas.getBoundingClientRect();
        return {
            x: (e.clientX - rect.left) * (canvas.width / rect.width),
            y: (e.clientY - rect.top) * (canvas.height / rect.height)
        };
    }

    function applySelection() {
        if (!crop.sel || crop.sel.w < 3 || crop.sel.h < 3) { crop.sel = null; drawCanvas(); return; }
        crop.ops.push({ type: crop.tool, x: crop.sel.x, y: crop.sel.y, w: crop.sel.w, h: crop.sel.h });
        crop.sel = null;
        drawCanvas();
    }

    var canvasEl = el('cdpCanvas');
    if (canvasEl) {
        canvasEl.addEventListener('pointerdown', function (e) {
            if (e.button !== undefined && e.button !== 0) return;
            crop.drag = canvasPoint(e);
            crop.drag.id = e.pointerId;
            crop.sel = { x: crop.drag.x, y: crop.drag.y, w: 0, h: 0 };
            try { canvasEl.setPointerCapture(e.pointerId); } catch (err) {}
            e.preventDefault();
        });
        canvasEl.addEventListener('pointermove', function (e) {
            if (!crop.drag || e.pointerId !== crop.drag.id) return;
            var p = canvasPoint(e);
            crop.sel = {
                x: Math.max(0, Math.min(crop.drag.x, p.x)), y: Math.max(0, Math.min(crop.drag.y, p.y)),
                w: Math.abs(p.x - crop.drag.x), h: Math.abs(p.y - crop.drag.y)
            };
            drawCanvas();
        });
        var endCrop = function (e) {
            if (!crop.drag || e.pointerId !== crop.drag.id) return;
            try { canvasEl.releasePointerCapture(crop.drag.id); } catch (err) {}
            crop.drag = null;
            applySelection();
        };
        canvasEl.addEventListener('pointerup', endCrop);
        canvasEl.addEventListener('pointercancel', endCrop);
    }

    var cropTools = el('cdpCropTools');
    if (cropTools) {
        cropTools.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-tool]');
            if (!btn) return;
            crop.tool = btn.getAttribute('data-tool');
            cropTools.querySelectorAll('[data-tool]').forEach(function (b) {
                b.classList.toggle('active', b === btn);
            });
            drawCanvas();
        });
    }

    if (el('cdpApplyTool')) {
        el('cdpApplyTool').addEventListener('click', function () {
            if (!crop.sel || crop.sel.w < 3 || crop.sel.h < 3) {
                message('Drag on the image - the chosen tool is applied when you let go.', 'warning');
                return;
            }
            applySelection();
        });
    }
    if (el('cdpRotate')) {
        el('cdpRotate').addEventListener('click', function () {
            crop.ops.push({ type: 'rotate' });
            crop.sel = null;
            drawCanvas();
        });
    }
    if (el('cdpUndo')) {
        el('cdpUndo').addEventListener('click', function () {
            if (!crop.ops.length) { message('Nothing to undo.', 'info'); return; }
            crop.ops.pop();
            crop.sel = null;
            drawCanvas();
        });
    }
    if (el('cdpResetImg')) {
        el('cdpResetImg').addEventListener('click', function () {
            crop.ops = [];
            crop.sel = null;
            drawCanvas();
        });
    }

    if (el('cdpCropSave')) {
        el('cdpCropSave').addEventListener('click', function () {
            var canvas = document.createElement('canvas');
            renderToCanvas(canvas);
            var slot = crop.slot;
            var button = el('cdpCropSave');
            button.disabled = true;
            canvas.toBlob(function (blob) {
                var data = new FormData();
                data.append('image', blob, slot + '.png');
                data.append('slot', slot);
                fetch('/api/coding-panel/image', { method: 'POST', body: data })
                    .then(function (res) { return res.json().catch(function () { return {}; }); })
                    .then(function (json) {
                        if (json && json.success) {
                            state.images[slot] = json.url;
                            renderPreview(slot);
                            if (crop.modal) crop.modal.hide();
                            message('Image added.', 'success');
                        } else {
                            message((json && json.message) || 'Upload failed.', 'danger');
                        }
                    })
                    .catch(function () { message('Upload failed. Please try again.', 'danger'); })
                    .finally(function () { button.disabled = false; });
            }, 'image/png');
        });
    }

    document.querySelectorAll('#codingManagementContainer .cdp-pick').forEach(function (input) {
        input.addEventListener('change', function () {
            var file = input.files && input.files[0];
            if (!file) return;
            openCropper(input.getAttribute('data-slot'), file);
            input.value = '';
        });
    });

    function wireTabs(tabsId, attribute, bodySelector) {
        var tabs = el(tabsId);
        if (!tabs) return;
        tabs.addEventListener('click', function (e) {
            var btn = e.target.closest('.cdp-tab');
            if (!btn) return;
            var key = btn.getAttribute(attribute);
            tabs.querySelectorAll('.cdp-tab').forEach(function (b) {
                b.classList.toggle('is-active', b === btn);
            });
            document.querySelectorAll(bodySelector).forEach(function (body) {
                body.classList.toggle('is-hidden', body.getAttribute(attribute) !== key);
            });
        });
    }
    wireTabs('cdpTplTabs', 'data-lang', '.cdp-tpl');
    wireTabs('cdpWebTabs', 'data-web', '.cdp-web');

    function addRow(templateId, hostId, fill) {
        var tpl = el(templateId), host = el(hostId);
        if (!tpl || !host) return null;
        var row = tpl.content.firstElementChild.cloneNode(true);
        row.querySelector('.cdp-row-del').addEventListener('click', function () { row.remove(); });
        host.appendChild(row);
        if (fill) fill(row);
        return row;
    }

    if (el('cdpAddTestcase')) {
        el('cdpAddTestcase').addEventListener('click', function () { addRow('cdpTestcaseTpl', 'cdpTestcases'); });
    }
    if (el('cdpAddAssertion')) {
        el('cdpAddAssertion').addEventListener('click', function () { addRow('cdpAssertionTpl', 'cdpAssertions'); });
    }

    function buildPayload(type) {
        var payload = {
            title: el('cdpTitle').value,
            difficulty: el('cdpDifficulty').value,
            marks: el('cdpMarks').value,
            statement_html: el('cdpStatement').value,
            input_spec: el('cdpInputSpec').value,
            example_html: el('cdpExample').value,
            statement_image: state.images.statement_image,
            input_image: state.images.input_image,
            example_image: state.images.example_image
        };
        if (type === 'coding') {
            payload.allowed_languages = Array.prototype.map.call(
                document.querySelectorAll('#cdpLangs input:checked'), function (b) { return b.value; });
            payload.output_spec = el('cdpOutputSpec').value;
            payload.time_limit_sec = el('cdpTimeLimit').value;
            payload.memory_limit = el('cdpMemory').value;
            payload.compare_mode = el('cdpCompareMode') ? el('cdpCompareMode').value : 'exact';
            payload.float_tolerance = el('cdpFloatTol') ? el('cdpFloatTol').value : '';
            payload.templates = {};
            document.querySelectorAll('.cdp-tpl').forEach(function (box) {
                if (box.value.trim()) payload.templates[box.getAttribute('data-lang')] = box.value;
            });
            payload.testcases = collectTestcases();
        } else if (type === 'sql') {
            payload.sandbox_schema_sql = el('cdpSandbox').value;
            payload.solution_query = el('cdpSolution').value;
            payload.ordered_comparison = el('cdpOrdered').checked;
            payload.schema_image_path = state.images.schema_image_path;
            payload.testcases = collectTestcases();
        } else if (type === 'web') {
            document.querySelectorAll('.cdp-web').forEach(function (box) {
                payload['starter_' + box.getAttribute('data-web')] = box.value;
            });
            payload.assertions = collectAssertions();
        }
        return payload;
    }

    function collectTestcases() {
        return Array.prototype.map.call(document.querySelectorAll('#cdpTestcases .cdp-row'), function (row) {
            return {
                input_text: row.querySelector('.cdp-tc-in').value,
                expected_output: row.querySelector('.cdp-tc-out').value,
                is_hidden: row.querySelector('.cdp-tc-hidden').checked
            };
        });
    }

    function collectAssertions() {
        return Array.prototype.map.call(document.querySelectorAll('#cdpAssertions .cdp-row'), function (row) {
            return {
                kind: row.querySelector('.cdp-as-kind').value,
                selector: row.querySelector('.cdp-as-sel').value,
                property_name: row.querySelector('.cdp-as-prop').value,
                expected_value: row.querySelector('.cdp-as-val').value,
                message: row.querySelector('.cdp-as-msg').value,
                is_hidden: row.querySelector('.cdp-as-hidden').checked
            };
        });
    }

    if (el('cdpSaveBtn')) {
        el('cdpSaveBtn').addEventListener('click', function () {
            var sectionId = el('cdpTargetSection').value;
            if (!sectionId) { message('Choose a section first.', 'warning'); return; }
            var type = currentSectionType();
            var editingId = el('cdpQuestionId').value;
            var button = el('cdpSaveBtn');
            if (editingId && !button.dataset.approved) {
                ask({
                    tone: 'primary',
                    title: 'Save changes to "' + (el('cdpTitle').value || 'this question') + '"?',
                    message: 'The stored question is replaced with what is in the editor now.',
                    confirmText: 'Save changes'
                }).then(function (ok) {
                    if (!ok) return;
                    button.dataset.approved = '1';
                    button.click();
                });
                return;
            }
            delete button.dataset.approved;
            button.disabled = true;
            var url = editingId
                ? '/api/coding-panel/questions/' + editingId
                : '/api/coding-panel/sections/' + sectionId + '/questions';
            send(url, editingId ? 'PUT' : 'POST', buildPayload(type))
                .then(function (r) {
                    if (r.ok && r.data.success) {
                        message(editingId ? 'Question updated.' : 'Question saved. It is listed under "Coding questions in section".', 'success');
                        resetEditor();
                        loadPanel();
                        if (el('cdpQuestionsList')) el('cdpQuestionsList').scrollIntoView({ behavior: 'smooth', block: 'center' });
                        if (window.jQuery && jQuery.fn.dataTable && jQuery.fn.dataTable.isDataTable('#testDescriptionsTable')) jQuery('#testDescriptionsTable').DataTable().ajax.reload(null, false);
                    } else {
                        message(r.data.message || 'Could not save the question.', 'danger');
                    }
                })
                .catch(function () { message('Network error. Please try again.', 'danger'); })
                .finally(function () { button.disabled = false; });
        });
    }

    function resetEditor() {
        el('cdpQuestionId').value = '';
        ['cdpTitle', 'cdpStatement', 'cdpInputSpec', 'cdpExample', 'cdpOutputSpec',
         'cdpSandbox', 'cdpSolution'].forEach(function (id) { if (el(id)) el(id).value = ''; });
        if (el('cdpMarks')) el('cdpMarks').value = 10;
        if (el('cdpDifficulty')) el('cdpDifficulty').value = 'Medium';
        if (el('cdpTimeLimit')) el('cdpTimeLimit').value = 10;
        if (el('cdpMemory')) el('cdpMemory').value = '512m';
        if (el('cdpCompareMode')) el('cdpCompareMode').value = 'exact';
        if (el('cdpFloatTol')) el('cdpFloatTol').value = '';
        syncCompareUI();
        if (el('cdpOrdered')) el('cdpOrdered').checked = false;
        document.querySelectorAll('#cdpLangs input').forEach(function (b) { b.checked = true; });
        applyTestLanguageLimit();
        document.querySelectorAll('.cdp-tpl, .cdp-web').forEach(function (b) { b.value = ''; });
        if (el('cdpTestcases')) el('cdpTestcases').innerHTML = '';
        if (el('cdpAssertions')) el('cdpAssertions').innerHTML = '';
        Object.keys(state.images).forEach(function (slot) {
            state.images[slot] = null;
            renderPreview(slot);
        });
        ['statement', 'input', 'example'].forEach(function (p) { showMode(p, 'text'); });
        el('cdpSaveLabel').textContent = 'Save question';
        el('cdpCancelEdit').classList.add('is-hidden');
        applySectionType();
    }

    if (el('cdpCancelEdit')) el('cdpCancelEdit').addEventListener('click', resetEditor);

    function renderQuestions() {
        var host = el('cdpQuestionsList');
        var select = el('cdpViewSection');
        if (!host || !select) return;
        if (!select.value) {
            host.innerHTML = '<p class="text-muted mb-0">No section selected.</p>';
            return;
        }
        send('/api/coding-panel/sections/' + select.value + '/questions').then(function (r) {
            if (!r.ok || !r.data.success) {
                host.innerHTML = '<p class="text-danger mb-0">Could not load the questions.</p>';
                return;
            }
            var questions = r.data.questions || [];
            shown = questions.map(function (q) { return String(q.id); });
            Object.keys(picked).forEach(function (id) { if (shown.indexOf(id) === -1) delete picked[id]; });
            paintPicked();
            if (!questions.length) {
                host.innerHTML = '<p class="text-muted mb-0">No questions in this section yet.</p>';
                return;
            }
            var type = (state.sections.filter(function (s) {
                return String(s.id) === String(select.value); })[0] || {}).section_type;
            host.innerHTML = questions.map(function (q, i) {
                var imgs = [];
                if (q.statement_image) imgs.push('question');
                if (q.input_image) imgs.push('input');
                if (q.example_image) imgs.push('example');
                var mode = imgs.length
                    ? '<span class="cdp-tag cdp-tag--img"><i class="fas fa-image"></i> ' + imgs.join(' + ') + ' image</span>'
                    : '<span class="cdp-tag"><i class="fas fa-keyboard"></i> typed</span>';
                var graded = type === 'web'
                    ? q.assertion_count + ' check' + (q.assertion_count === 1 ? '' : 's')
                    : q.testcase_count + ' test case' + (q.testcase_count === 1 ? '' : 's');
                var excerpt = plainText(q.statement_html).slice(0, 150);
                var langs = String(q.allowed_languages || '').split(',').filter(Boolean);
                return '<div class="cdp-q-wrap" data-q="' + q.id + '"><div class="cdp-q">' +
                    '<input type="checkbox" class="form-check-input cdp-q-check mt-2" data-id="' + q.id + '" aria-label="Select question ' + (i + 1) + '"' + (picked[String(q.id)] ? ' checked' : '') + '>' +
                    '<span class="cdp-q__num">' + (i + 1) + '</span>' +
                    '<div class="cdp-q__body"><strong>' + escapeHtml(q.title) + '</strong>' +
                        (excerpt ? '<div class="cdp-q__excerpt">' + escapeHtml(excerpt) + (plainText(q.statement_html).length > 150 ? '...' : '') + '</div>' : '') +
                        '<div class="cdp-q__meta">' +
                            '<span class="cdp-tag cdp-tag--' + String(q.difficulty || 'Medium').toLowerCase() + '">' +
                                escapeHtml(q.difficulty || 'Medium') + '</span>' +
                            '<span class="cdp-tag">' + q.marks + ' marks</span>' +
                            '<span class="cdp-tag">' + graded + '</span>' + mode +
                            (type === 'coding' && langs.length ? '<span class="cdp-tag"><i class="fas fa-code"></i> ' + escapeHtml(langs.join(', ')) + '</span>' : '') +
                        '</div></div>' +
                    '<div class="cdp-q__actions">' +
                        '<button type="button" class="btn btn-sm btn-outline-secondary" data-view-q="' + q.id + '">' +
                            '<i class="fas fa-eye me-1"></i>View</button> ' +
                        '<button type="button" class="btn btn-sm btn-outline-primary" data-edit-q="' + q.id + '">' +
                            '<i class="fas fa-pen me-1"></i>Edit</button> ' +
                        '<button type="button" class="btn btn-sm btn-outline-danger" data-del-q="' + q.id + '">' +
                            '<i class="fas fa-trash me-1"></i>Delete</button>' +
                    '</div></div><div class="cdp-q-detail is-hidden"></div></div>';
            }).join('');
        }).catch(function () {
            host.innerHTML = '<p class="text-danger mb-0">Could not load the questions.</p>';
        });
    }

    function plainText(html) {
        var d = document.createElement('div');
        d.innerHTML = String(html || '').replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/gi, '');
        return (d.textContent || '').replace(/\s+/g, ' ').trim();
    }

    function keepLines(html) {
        var d = document.createElement('div');
        d.innerHTML = String(html || '').replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/gi, '').replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|div|li|h[1-6])>/gi, '\n');
        return (d.textContent || '').replace(/\n{3,}/g, '\n\n').trim();
    }

    function detailBlock(label, value, mono) {
        if (!value) return '';
        return '<div class="cdp-d"><div class="cdp-d__label">' + label + '</div>' +
               '<pre class="cdp-d__value' + (mono ? ' cdp-mono' : '') + '">' + escapeHtml(value) + '</pre></div>';
    }

    function detailImage(label, url) {
        if (!url) return '';
        return '<div class="cdp-d"><div class="cdp-d__label">' + label + '</div>' +
               '<img class="cdp-d__img" src="' + escapeHtml(url) + '" alt="' + label + '"></div>';
    }

    function renderDetail(host, data) {
        var q = data.question || {};
        var html = '';
        html += detailBlock('Question', keepLines(q.statement_html));
        html += detailImage('Question image', q.statement_image);
        html += detailBlock('Input format', q.input_spec);
        html += detailImage('Input image', q.input_image);
        html += detailBlock('Example', keepLines(q.example_html), true);
        html += detailImage('Example image', q.example_image);
        html += detailBlock('Output format', q.output_spec);
        if (q.section_type === 'coding') {
            html += detailBlock('Limits', (q.time_limit_sec || 10) + ' sec per run · ' + (q.memory_limit || '512m') + ' memory · compare: ' + (q.compare_mode || 'exact'));
            var cases = data.testcases || [];
            if (cases.length) {
                html += '<div class="cdp-d"><div class="cdp-d__label">Test cases (' + cases.length + ')</div><div class="table-responsive"><table class="table table-sm table-bordered mb-0"><thead><tr><th>#</th><th>Input</th><th>Expected output</th><th>Shown to candidate</th></tr></thead><tbody>' +
                    cases.map(function (t, i) {
                        return '<tr><td>' + (i + 1) + '</td><td><pre class="cdp-mono mb-0">' + escapeHtml(t.input_text || '') + '</pre></td><td><pre class="cdp-mono mb-0">' + escapeHtml(t.expected_output || '') + '</pre></td><td>' + (t.is_hidden ? 'Hidden' : 'Visible') + '</td></tr>';
                    }).join('') + '</tbody></table></div></div>';
            }
            var allowed = q.allowed_languages || [];
            var saved = data.templates || {};
            var defaults = state.starterTemplates || {};
            allowed.forEach(function (lang) {
                var code = (saved[lang] || '').trim() ? saved[lang] : (defaults[lang] || '');
                html += detailBlock('Starter code - ' + lang + ((saved[lang] || '').trim() ? '' : ' (standard skeleton)'), code, true);
            });
        } else if (q.section_type === 'sql') {
            html += detailBlock('Sandbox schema', q.sandbox_schema_sql, true);
            html += detailBlock('Solution query', q.solution_query, true);
        } else if (q.section_type === 'web') {
            html += detailBlock('Starter HTML', q.starter_html, true);
            html += detailBlock('Starter CSS', q.starter_css, true);
            html += detailBlock('Starter JS', q.starter_js, true);
            var checks = data.assertions || [];
            if (checks.length) html += detailBlock('Checks', checks.map(function (a, i) { return (i + 1) + '. ' + (a.description || a.kind || ''); }).join('\n'));
        }
        host.innerHTML = html || '<p class="text-muted mb-0">Nothing more is stored for this question.</p>';
    }

    function loadStarterTemplates() {
        if (state.starterTemplates) return Promise.resolve(state.starterTemplates);
        return send('/api/coding-panel/starter-templates').then(function (r) {
            state.starterTemplates = (r.ok && r.data.success) ? (r.data.templates || {}) : {};
            return state.starterTemplates;
        }).catch(function () { state.starterTemplates = {}; return {}; });
    }

    function toggleDetail(id, button) {
        var wrap = document.querySelector('.cdp-q-wrap[data-q="' + id + '"]');
        if (!wrap) return;
        var host = wrap.querySelector('.cdp-q-detail');
        if (!host.classList.contains('is-hidden')) {
            host.classList.add('is-hidden');
            button.innerHTML = '<i class="fas fa-eye me-1"></i>View';
            return;
        }
        host.classList.remove('is-hidden');
        host.innerHTML = '<p class="text-muted mb-0">Loading...</p>';
        button.innerHTML = '<i class="fas fa-eye-slash me-1"></i>Hide';
        loadStarterTemplates().then(function () {
            return send('/api/coding-panel/questions/' + id);
        }).then(function (r) {
            if (!r.ok || !r.data.success) { host.innerHTML = '<p class="text-danger mb-0">Could not load this question.</p>'; return; }
            renderDetail(host, r.data);
        }).catch(function () { host.innerHTML = '<p class="text-danger mb-0">Could not load this question.</p>'; });
    }

    if (el('cdpFillStarter')) {
        el('cdpFillStarter').addEventListener('click', function () {
            loadStarterTemplates().then(function (defaults) {
                var boxes = Array.prototype.slice.call(document.querySelectorAll('.cdp-tpl'));
                var allowed = Array.prototype.slice.call(document.querySelectorAll('#cdpLangs input:checked')).map(function (b) { return b.value; });
                var targets = boxes.filter(function (b) { return allowed.indexOf(b.getAttribute('data-lang')) !== -1 && defaults[b.getAttribute('data-lang')]; });
                var filled = targets.filter(function (b) { return b.value.trim(); });
                var go = filled.length
                    ? ask({ tone: 'primary', title: 'Replace the starter code you already typed?', message: filled.length + ' language(s) already have starter code.', confirmText: 'Replace all', altText: 'Only fill empty ones' })
                    : Promise.resolve('alt');
                go.then(function (choice) {
                    if (!choice) return;
                    var n = 0;
                    targets.forEach(function (b) {
                        if (choice === 'alt' && b.value.trim()) return;
                        b.value = defaults[b.getAttribute('data-lang')];
                        n++;
                    });
                    message(n ? 'Starter code filled for ' + n + ' language(s). Edit it before saving if needed.' : 'Every allowed language already has starter code.', n ? 'success' : 'info');
                });
            });
        });
    }

    var questionsList = el('cdpQuestionsList');
    if (questionsList) {
        questionsList.addEventListener('click', function (e) {
            var view = e.target.closest('[data-view-q]');
            if (view) { toggleDetail(view.getAttribute('data-view-q'), view); return; }
            var edit = e.target.closest('[data-edit-q]');
            if (edit) { loadForEdit(edit.getAttribute('data-edit-q')); return; }
            var del = e.target.closest('[data-del-q]');
            if (!del) return;
            deleteCoding([del.getAttribute('data-del-q')]);
        });
        questionsList.addEventListener('change', function (e) {
            var box = e.target.closest('.cdp-q-check');
            if (!box) return;
            if (box.checked) picked[box.getAttribute('data-id')] = true; else delete picked[box.getAttribute('data-id')];
            paintPicked();
        });
    }

    if (el('cdpSelectAll')) {
        el('cdpSelectAll').addEventListener('change', function () {
            var on = this.checked;
            shown.forEach(function (id) { if (on) picked[id] = true; else delete picked[id]; });
            document.querySelectorAll('.cdp-q-check').forEach(function (b) { b.checked = on; });
            paintPicked();
        });
    }
    if (el('cdpDeleteSelected')) {
        el('cdpDeleteSelected').addEventListener('click', function () { deleteCoding(paintPicked()); });
    }

    function deleteCoding(ids) {
        if (!ids.length) return;
        var n = ids.length;
        ask({
            tone: 'danger',
            title: n === 1 ? 'Delete this coding question?' : 'Delete ' + n + ' selected coding questions?',
            message: 'Each question is removed with its test cases, starter code and images.',
            note: 'This cannot be undone.',
            confirmText: n === 1 ? 'Delete question' : 'Delete ' + n + ' questions'
        }).then(function (ok) {
            if (!ok) return;
            var done = 0, failed = [];
            var chain = Promise.resolve();
            ids.forEach(function (id) {
                chain = chain.then(function () {
                    return send('/api/coding-panel/questions/' + id, 'DELETE').then(function (r) {
                        if (r.ok && r.data.success) { done++; delete picked[id]; if (r.data.message && r.data.message.indexOf('unpublished') > -1) failed.push(r.data.message); }
                        else failed.push((r.data && r.data.message) || ('question ' + id));
                    }).catch(function () { failed.push('question ' + id + ' (network)'); });
                });
            });
            chain.then(function () {
                if (failed.length) message(done + ' deleted, ' + failed.length + ' could not be deleted: ' + failed.join('; '), 'danger');
                else message(done + ' question(s) deleted.', 'success');
                loadPanel();
            });
        });
    }

    function loadForEdit(questionId) {
        send('/api/coding-panel/questions/' + questionId).then(function (r) {
            if (!r.ok || !r.data.success) {
                message((r.data && r.data.message) || 'Could not open the question.', 'danger');
                return;
            }
            var q = r.data.question;
            el('cdpTargetSection').value = q.section_id;
            resetEditor();
            applySectionType();

            el('cdpQuestionId').value = q.id;
            el('cdpTitle').value = q.title || '';
            el('cdpDifficulty').value = q.difficulty || 'Medium';
            el('cdpMarks').value = q.marks || 10;
            el('cdpStatement').value = q.statement_html || '';
            el('cdpInputSpec').value = q.input_spec || '';
            el('cdpExample').value = q.example_html || '';

            [['statement', 'statement_image'], ['input', 'input_image'], ['example', 'example_image']]
                .forEach(function (pair) {
                    if (q[pair[1]]) {
                        state.images[pair[1]] = q[pair[1]];
                        renderPreview(pair[1]);
                        showMode(pair[0], 'image');
                    }
                });

            var type = q.section_type;
            if (type === 'coding') {
                el('cdpOutputSpec').value = q.output_spec || '';
                el('cdpTimeLimit').value = q.time_limit_sec || 10;
                el('cdpMemory').value = q.memory_limit || '512m';
                if (el('cdpCompareMode')) el('cdpCompareMode').value = q.compare_mode || 'exact';
                if (el('cdpFloatTol')) el('cdpFloatTol').value = (q.float_tolerance != null ? q.float_tolerance : '');
                syncCompareUI();
                var allowed = q.allowed_languages || [];
                document.querySelectorAll('#cdpLangs input').forEach(function (b) {
                    b.checked = allowed.indexOf(b.value) !== -1;
                });
                applyTestLanguageLimit();
                var templates = r.data.templates || {};
                document.querySelectorAll('.cdp-tpl').forEach(function (box) {
                    box.value = templates[box.getAttribute('data-lang')] || '';
                });
            } else if (type === 'sql') {
                el('cdpSandbox').value = q.sandbox_schema_sql || '';
                el('cdpSolution').value = q.solution_query || '';
                el('cdpOrdered').checked = !!q.ordered_comparison;
                if (q.schema_image_path) {
                    state.images.schema_image_path = q.schema_image_path;
                    renderPreview('schema_image_path');
                }
            } else if (type === 'web') {
                document.querySelectorAll('.cdp-web').forEach(function (box) {
                    box.value = q['starter_' + box.getAttribute('data-web')] || '';
                });
                if (el('cdpAssertions')) el('cdpAssertions').innerHTML = '';
                if (!(r.data.assertions || []).length) addRow('cdpAssertionTpl', 'cdpAssertions');
                (r.data.assertions || []).forEach(function (a) {
                    addRow('cdpAssertionTpl', 'cdpAssertions', function (row) {
                        row.querySelector('.cdp-as-kind').value = a.kind;
                        row.querySelector('.cdp-as-sel').value = a.selector || '';
                        row.querySelector('.cdp-as-prop').value = a.property_name || '';
                        row.querySelector('.cdp-as-val').value = a.expected_value || '';
                        row.querySelector('.cdp-as-msg').value = a.message || '';
                        row.querySelector('.cdp-as-hidden').checked = !!a.is_hidden;
                    });
                });
            }

            if (el('cdpTestcases')) el('cdpTestcases').innerHTML = '';
            (r.data.testcases || []).forEach(function (tc) {
                addRow('cdpTestcaseTpl', 'cdpTestcases', function (row) {
                    row.querySelector('.cdp-tc-in').value = tc.input_text || '';
                    row.querySelector('.cdp-tc-out').value = tc.expected_output || '';
                    row.querySelector('.cdp-tc-hidden').checked = !!tc.is_hidden;
                });
            });

            el('cdpSaveLabel').textContent = 'Update question';
            el('cdpCancelEdit').classList.remove('is-hidden');
            el('cdpEditor').scrollIntoView({ behavior: 'smooth', block: 'start' });
        }).catch(function () { message('Network error. Please try again.', 'danger'); });
    }
}());
