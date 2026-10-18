/* Practice coding bank editor: type-or-image parts, testcases, templates,
 * Free/Paid tier, and a filterable list with one-click tier flips. */
(function () {
    'use strict';

    function el(id) { return document.getElementById(id); }

    function toast(message, ok) {
        if (window.adminToast) window.adminToast(escapeHtml(message), ok ? 'success' : 'danger');
        else alert(message);
    }
    function ask(opts) {
        return window.adminConfirm ? window.adminConfirm(opts) : Promise.resolve(window.confirm(opts.title));
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

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : text;
        return div.innerHTML;
    }

    var images = { statement_image: null, input_image: null, example_image: null };

    var tierBox = el('pcqTier');
    if (tierBox) {
        tierBox.addEventListener('change', function () {
            tierBox.querySelectorAll('.pcq-tier__opt').forEach(function (opt) {
                opt.classList.toggle('is-active', opt.querySelector('input').checked);
            });
        });
    }
    function currentTier() {
        var picked = document.querySelector('input[name="pcqTier"]:checked');
        return picked ? picked.value : 'free';
    }
    function setTier(paid) {
        var value = paid ? 'paid' : 'free';
        var radio = document.querySelector('input[name="pcqTier"][value="' + value + '"]');
        if (radio) { radio.checked = true; tierBox.dispatchEvent(new Event('change')); }
    }

    document.querySelectorAll('.cdp-modes').forEach(function (bar) {
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
        var part = document.querySelector('.cdp-part[data-part="' + partName + '"]');
        if (!part) return;
        var btn = part.querySelector('.cdp-mode[data-mode="' + mode + '"]');
        if (btn) btn.click();
    }

    function renderPreview(slot) {
        var box = document.querySelector('.cdp-preview[data-slot="' + slot + '"]');
        if (!box) return;
        box.innerHTML = '';
        if (!images[slot]) return;
        var img = document.createElement('img');
        img.src = images[slot];
        var remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn btn-sm btn-outline-danger';
        remove.innerHTML = '<i class="fas fa-trash"></i> Remove';
        remove.addEventListener('click', function () {
            images[slot] = null;
            renderPreview(slot);
        });
        box.appendChild(img);
        box.appendChild(remove);
    }

    document.querySelectorAll('.pcq-pick').forEach(function (input) {
        input.addEventListener('change', function () {
            var file = input.files && input.files[0];
            if (!file) return;
            var slot = input.getAttribute('data-slot');
            var data = new FormData();
            data.append('image', file);
            data.append('slot', slot);
            input.disabled = true;
            fetch('/api/practice-coding/image', { method: 'POST', body: data })
                .then(function (res) { return res.json().catch(function () { return {}; }); })
                .then(function (json) {
                    if (json && json.success) {
                        images[slot] = json.url;
                        renderPreview(slot);
                        toast('Image uploaded.', true);
                    } else {
                        toast((json && json.message) || 'Upload failed.', false);
                    }
                })
                .catch(function () { toast('Upload failed. Please try again.', false); })
                .finally(function () { input.disabled = false; input.value = ''; });
        });
    });

    var tabs = el('pcqTplTabs');
    if (tabs) {
        tabs.addEventListener('click', function (e) {
            var btn = e.target.closest('.cdp-tab');
            if (!btn) return;
            var lang = btn.getAttribute('data-lang');
            tabs.querySelectorAll('.cdp-tab').forEach(function (b) {
                b.classList.toggle('is-active', b === btn);
            });
            document.querySelectorAll('.pcq-tpl').forEach(function (box) {
                box.classList.toggle('is-hidden', box.getAttribute('data-lang') !== lang);
            });
        });
    }

    function addRow(fill) {
        var tpl = el('pcqTestcaseTpl');
        var host = el('pcqTestcases');
        var row = tpl.content.firstElementChild.cloneNode(true);
        row.querySelector('.pcq-row-del').addEventListener('click', function () { row.remove(); });
        host.appendChild(row);
        if (fill) fill(row);
        return row;
    }
    el('pcqAddTestcase').addEventListener('click', function () { addRow(); });
    addRow();

    function buildPayload() {
        return {
            title: el('pcqTitle').value,
            difficulty: el('pcqDifficulty').value,
            subject: el('pcqSubject').value,
            is_paid: currentTier() === 'paid',
            statement_html: el('pcqStatement').value,
            input_spec: el('pcqInputSpec').value,
            example_html: el('pcqExample').value,
            statement_image: images.statement_image,
            input_image: images.input_image,
            example_image: images.example_image,
            output_spec: el('pcqOutputSpec').value,
            companies: el('pcqCompanies') ? el('pcqCompanies').value.split(/[,;]/).map(function (c) { return c.trim(); }).filter(Boolean) : [],
            position: el('pcqPosition') ? el('pcqPosition').value : 0,
            time_limit_sec: el('pcqTimeLimit').value,
            memory_limit: el('pcqMemory').value,
            compare_mode: el('pcqCompareMode') ? el('pcqCompareMode').value : 'exact',
            float_tolerance: el('pcqFloatTol') ? el('pcqFloatTol').value : '',
            allowed_languages: Array.prototype.map.call(
                document.querySelectorAll('#pcqLangs input:checked'),
                function (box) { return box.value; }),
            templates: (function () {
                var out = {};
                document.querySelectorAll('.pcq-tpl').forEach(function (box) {
                    if (box.value.trim()) out[box.getAttribute('data-lang')] = box.value;
                });
                return out;
            }()),
            testcases: Array.prototype.map.call(
                document.querySelectorAll('#pcqTestcases .cdp-row'),
                function (row) {
                    return {
                        input_text: row.querySelector('.pcq-tc-in').value,
                        expected_output: row.querySelector('.pcq-tc-out').value,
                        is_hidden: row.querySelector('.pcq-tc-hidden').checked
                    };
                })
        };
    }

    function syncCompareUI() {
        var sel = el('pcqCompareMode');
        if (!sel) return;
        var mode = sel.value;
        var box = el('pcqFloatTolBox');
        if (box) box.style.display = mode === 'float' ? '' : 'none';
        var hint = el('pcqCompareHint');
        if (hint) hint.textContent = mode === 'float'
            ? 'Numbers are compared within the tolerance; other text must match.'
            : mode === 'unordered'
            ? 'Output lines may come back in any order.'
            : 'Output is matched exactly (whitespace-trimmed).';
    }
    if (el('pcqCompareMode')) el('pcqCompareMode').addEventListener('change', syncCompareUI);

    function resetEditor() {
        el('pcqId').value = '';
        ['pcqTitle', 'pcqSubject', 'pcqStatement', 'pcqInputSpec', 'pcqExample',
         'pcqOutputSpec'].forEach(function (id) { el(id).value = ''; });
        el('pcqDifficulty').value = 'Easy';
        if (el('pcqCompanies')) el('pcqCompanies').value = '';
        if (el('pcqPosition')) el('pcqPosition').value = 0;
        el('pcqTimeLimit').value = 10;
        el('pcqMemory').value = '512m';
        if (el('pcqCompareMode')) el('pcqCompareMode').value = 'exact';
        if (el('pcqFloatTol')) el('pcqFloatTol').value = '';
        syncCompareUI();
        setTier(false);
        document.querySelectorAll('#pcqLangs input').forEach(function (b) { b.checked = true; });
        document.querySelectorAll('.pcq-tpl').forEach(function (b) { b.value = ''; });
        el('pcqTestcases').innerHTML = '';
        addRow();
        Object.keys(images).forEach(function (slot) { images[slot] = null; renderPreview(slot); });
        ['statement', 'input', 'example'].forEach(function (p) { showMode(p, 'text'); });
        el('pcqEditorTitle').innerHTML = '<i class="fas fa-plus-circle" style="color:#6b1d2b"></i> Add a question';
        el('pcqSaveLabel').textContent = 'Save question';
        el('pcqCancelEdit').classList.add('is-hidden');
    }

    el('pcqCancelEdit').addEventListener('click', resetEditor);

    el('pcqSaveBtn').addEventListener('click', function () {
        var editingId = el('pcqId').value;
        var url = editingId ? '/api/practice-coding/questions/' + editingId
                            : '/api/practice-coding/questions';
        var go = editingId
            ? ask({ tone: 'primary', title: 'Save changes to "' + (el('pcqTitle').value || 'this question') + '"?',
                    message: 'The stored question, its test cases and starter code are replaced with what is in the editor now.', confirmText: 'Save changes' })
            : Promise.resolve(true);
        go.then(function (ok) {
        if (!ok) return;
        el('pcqSaveBtn').disabled = true;
        send(url, editingId ? 'PUT' : 'POST', buildPayload())
            .then(function (r) {
                if (r.ok && r.data.success) {
                    toast(editingId ? 'Question updated.' : 'Question saved.', true);
                    resetEditor();
                    loadList();
                } else {
                    toast(r.data.message || 'Could not save the question.', false);
                }
            })
            .catch(function () { toast('Network error. Please try again.', false); })
            .finally(function () { el('pcqSaveBtn').disabled = false; });
        });
    });

    function loadForEdit(qid) {
        send('/api/practice-coding/questions/' + qid).then(function (r) {
            if (!r.ok || !r.data.success) {
                toast((r.data && r.data.message) || 'Could not open the question.', false);
                return;
            }
            resetEditor();
            var q = r.data.question;
            el('pcqId').value = q.id;
            el('pcqTitle').value = q.title || '';
            el('pcqDifficulty').value = q.difficulty || 'Easy';
            el('pcqSubject').value = q.subject || '';
            setTier(!!q.is_paid);
            el('pcqStatement').value = q.statement_html || '';
            el('pcqInputSpec').value = q.input_spec || '';
            el('pcqExample').value = q.example_html || '';
            el('pcqOutputSpec').value = q.output_spec || '';
            if (el('pcqCompanies')) el('pcqCompanies').value = (q.companies || []).join(', ');
            if (el('pcqPosition')) el('pcqPosition').value = q.position || 0;
            el('pcqTimeLimit').value = q.time_limit_sec || 10;
            el('pcqMemory').value = q.memory_limit || '512m';
            if (el('pcqCompareMode')) el('pcqCompareMode').value = q.compare_mode || 'exact';
            if (el('pcqFloatTol')) el('pcqFloatTol').value = (q.float_tolerance != null ? q.float_tolerance : '');
            syncCompareUI();
            var allowed = q.allowed_languages || [];
            document.querySelectorAll('#pcqLangs input').forEach(function (box) {
                box.checked = allowed.indexOf(box.value) !== -1;
            });
            var templates = r.data.templates || {};
            document.querySelectorAll('.pcq-tpl').forEach(function (box) {
                box.value = templates[box.getAttribute('data-lang')] || '';
            });
            [['statement', 'statement_image'], ['input', 'input_image'], ['example', 'example_image']]
                .forEach(function (pair) {
                    if (q[pair[1]]) {
                        images[pair[1]] = q[pair[1]];
                        renderPreview(pair[1]);
                        showMode(pair[0], 'image');
                    }
                });
            el('pcqTestcases').innerHTML = '';
            (r.data.testcases || []).forEach(function (tc) {
                addRow(function (row) {
                    row.querySelector('.pcq-tc-in').value = tc.input_text || '';
                    row.querySelector('.pcq-tc-out').value = tc.expected_output || '';
                    row.querySelector('.pcq-tc-hidden').checked = !!tc.is_hidden;
                });
            });
            el('pcqEditorTitle').innerHTML =
                '<i class="fas fa-pen-to-square" style="color:#6b1d2b"></i> Editing: ' + escapeHtml(q.title);
            el('pcqSaveLabel').textContent = 'Update question';
            el('pcqCancelEdit').classList.remove('is-hidden');
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    var list = el('pcqList');
    var subjectFilter = el('pcqFilterSubject');
    var tierFilter = el('pcqFilterTier');
    var statusFilter = el('pcqFilterStatus');

    // Rebuilt on every load so a subject added a moment ago is filterable
    // immediately, keeping whatever the admin had selected.
    function refreshSubjects(subjects) {
        var current = subjectFilter.value;
        subjectFilter.innerHTML = '<option value="">All subjects</option>';
        (subjects || []).forEach(function (s) {
            var opt = document.createElement('option');
            opt.value = s.subject;
            opt.textContent = s.subject + ' (' + s.n + ')';
            subjectFilter.appendChild(opt);
        });
        subjectFilter.value = current;
        if (subjectFilter.selectedIndex === -1) subjectFilter.value = '';
    }

    function loadList() {
        var params = [];
        if (subjectFilter.value) params.push('subject=' + encodeURIComponent(subjectFilter.value));
        if (tierFilter.value) params.push('tier=' + tierFilter.value);
        if (statusFilter.value) params.push('status=' + statusFilter.value);
        send('/api/practice-coding/questions' + (params.length ? '?' + params.join('&') : ''))
            .then(function (r) {
                if (!r.ok || !r.data.success) {
                    list.innerHTML = '<p class="cd-empty">Could not load the questions.</p>';
                    return;
                }
                refreshSubjects(r.data.subjects);
                var questions = r.data.questions || [];
                if (!questions.length) {
                    list.innerHTML = '<p class="cd-empty">No questions match this filter.</p>';
                    return;
                }
                var removedView = statusFilter.value === 'removed';
                list.innerHTML = questions.map(function (q, i) {
                    if (removedView) {
                        return '<article style="display:flex;align-items:center;gap:14px;padding:13px 16px;margin-bottom:10px;border:1px dashed #d0b9ad;border-radius:10px;background:#fdf8f3">' +
                            '<span class="cd-q__num" style="background:#8a8078">' + (i + 1) + '</span>' +
                            '<div style="flex:1;min-width:0"><strong>' + escapeHtml(q.title) + '</strong>' +
                            '<div class="cd-q__meta" style="margin-top:6px">' +
                                '<span class="cd-tag">' + escapeHtml(q.subject) + '</span>' +
                                '<span class="cd-tag">removed</span></div></div>' +
                            '<button type="button" class="btn btn-sm btn-success" data-restore-q="' + q.id + '">' +
                                '<i class="fas fa-rotate-left me-1"></i>Restore</button></article>';
                    }
                    var tier = q.is_paid
                        ? '<button type="button" class="pcq-flag pcq-flag--paid" data-tier-q="' + q.id + '" title="Click to make Free"><i class="fas fa-crown"></i> Paid</button>'
                        : '<button type="button" class="pcq-flag pcq-flag--free" data-tier-q="' + q.id + '" title="Click to make Paid"><i class="fas fa-unlock"></i> Free</button>';
                    return '<article class="cd-q" style="display:flex;align-items:center;gap:14px;padding:13px 16px;margin-bottom:10px;border:1px solid #e6ded6;border-radius:10px;background:#fff">' +
                        '<span class="cd-q__num">' + (i + 1) + '</span>' +
                        '<div style="flex:1;min-width:0"><strong>' + escapeHtml(q.title) + '</strong>' +
                        '<div class="cd-q__meta" style="margin-top:6px">' +
                            '<span class="cd-tag cd-tag--' + q.difficulty.toLowerCase().replace('moderate', 'medium') + '">' + escapeHtml(q.difficulty) + '</span>' +
                            '<span class="cd-tag">' + escapeHtml(q.subject) + '</span>' +
                            '<span class="cd-tag">' + q.testcase_count + ' case' + (q.testcase_count === 1 ? '' : 's') + '</span>' +
                            '<span class="cd-tag">' + q.attempt_count + ' attempt' + (q.attempt_count === 1 ? '' : 's') + '</span>' +
                        '</div></div>' +
                        tier +
                        '<div style="display:flex;gap:6px">' +
                        '<button type="button" class="btn btn-sm btn-outline-primary" data-edit-q="' + q.id + '"><i class="fas fa-pen"></i></button>' +
                        '<button type="button" class="btn btn-sm btn-outline-danger" data-del-q="' + q.id + '"><i class="fas fa-trash"></i></button>' +
                        '</div></article>';
                }).join('');
            });
    }

    subjectFilter.addEventListener('change', loadList);
    tierFilter.addEventListener('change', loadList);
    statusFilter.addEventListener('change', loadList);

    list.addEventListener('click', function (e) {
        var restore = e.target.closest('[data-restore-q]');
        if (restore) {
            send('/api/practice-coding/questions/' + restore.getAttribute('data-restore-q') + '/restore', 'PUT')
                .then(function (r) {
                    if (r.ok && r.data.success) { toast('Question restored.', true); loadList(); }
                    else { toast((r.data && r.data.message) || 'Could not restore.', false); }
                });
            return;
        }
        var edit = e.target.closest('[data-edit-q]');
        if (edit) { loadForEdit(edit.getAttribute('data-edit-q')); return; }

        var flip = e.target.closest('[data-tier-q]');
        if (flip) {
            var toPaid = flip.classList.contains('pcq-flag--free');
            ask({ tone: 'primary', title: toPaid ? 'Make this question Paid?' : 'Make this question Free?',
                  message: toPaid ? 'Only students with Coding Practice Premium will be able to open it.' : 'Every student will be able to open it.',
                  confirmText: toPaid ? 'Make Paid' : 'Make Free' }).then(function (ok) {
            if (!ok) return;
            send('/api/practice-coding/questions/' + flip.getAttribute('data-tier-q') + '/tier', 'PUT')
                .then(function (r) {
                    if (r.ok && r.data.success) {
                        toast(r.data.is_paid ? 'Now a Paid question.' : 'Now a Free question.', true);
                        loadList();
                    } else {
                        toast((r.data && r.data.message) || 'Could not change access.', false);
                    }
                });
            });
            return;
        }

        var del = e.target.closest('[data-del-q]');
        if (!del) return;
        var card = del.closest('article');
        var title = card ? (card.querySelector('strong') || {}).textContent : '';
        ask({ tone: 'danger', title: 'Remove "' + (title || 'this question') + '" from the bank?',
              message: 'Students will no longer see it. Their solve history is kept, and you can restore it from the Removed list.',
              confirmText: 'Remove' }).then(function (ok) {
            if (!ok) return;
            send('/api/practice-coding/questions/' + del.getAttribute('data-del-q'), 'DELETE')
                .then(function (r) {
                    if (r.ok && r.data.success) { toast('Question removed.', true); loadList(); }
                    else { toast((r.data && r.data.message) || 'Could not remove it.', false); }
                });
        });
    });

    var bulkFile = el('pcqBulkFile');
    var bulkResult = el('pcqBulkResult');
    if (bulkFile) {
        bulkFile.addEventListener('change', function () {
            var file = bulkFile.files && bulkFile.files[0];
            if (!file) return;
            var data = new FormData();
            data.append('file', file);
            bulkResult.innerHTML = '<div class="alert alert-info py-2 mb-0">Checking the file...</div>';
            fetch('/api/practice-coding/bulk/upload', { method: 'POST', body: data })
                .then(function (res) { return res.json().catch(function () { return {}; }); })
                .then(function (json) {
                    if (json && json.success) {
                        var skipped = (json.skipped || []).map(function (t) { return '<li>' + escapeHtml(t) + '</li>'; }).join('');
                        bulkResult.innerHTML = '<div class="alert ' + (json.imported ? 'alert-success' : 'alert-info') + ' py-2 mb-0">' +
                            escapeHtml(json.message || ('Imported ' + json.imported + ' question(s).')) +
                            (skipped ? '<ul class="mb-0 mt-1 small">' + skipped + '</ul>' : '') + '</div>';
                        loadList();
                    } else {
                        var items = (json.errors || []).map(function (e) {
                            return '<li>' + escapeHtml(e) + '</li>';
                        }).join('');
                        bulkResult.innerHTML = '<div class="alert alert-danger py-2 mb-0">' +
                            escapeHtml((json && json.message) || 'Upload failed.') +
                            (items ? '<ul class="mb-0 mt-1">' + items + '</ul>' : '') + '</div>';
                    }
                })
                .catch(function () {
                    bulkResult.innerHTML = '<div class="alert alert-danger py-2 mb-0">Network error. Please try again.</div>';
                })
                .finally(function () { bulkFile.value = ''; });
        });
    }

    loadList();
}());