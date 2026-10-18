(function () {
    var descId = null;
    var descRow = null;
    var sections = [];
    var questions = [];
    var selected = {};
    var editing = null;

    function el(id) { return document.getElementById(id); }
    function esc(v) {
        var d = document.createElement('div');
        d.appendChild(document.createTextNode(v == null ? '' : String(v)));
        return d.innerHTML;
    }
    function say(text, kind) {
        if (window.adminToast) {
            window.adminToast(esc(text), kind === 'danger' || !kind ? 'danger' : kind);
            return;
        }
        var box = el('commMessage');
        box.className = 'alert alert-' + (kind || 'danger');
        box.textContent = text;
        box.classList.remove('is-hidden');
    }
    function ask(opts) {
        return window.adminConfirm ? window.adminConfirm(opts) : Promise.resolve(window.confirm(opts.title));
    }
    function send(url, method, body) {
        var init = { method: method || 'GET', headers: { 'Accept': 'application/json' } };
        if (body !== undefined) {
            init.headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(body);
        }
        return fetch(url, init).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, status: r.status, d: d }; });
        });
    }

    var TYPE_SHOW = {
        MCQ: { mcq: true },
        COMPREHENSION: { mcq: true, media: true },
        SPEAK: { rec: true },
        THINK_SPEAK: { rec: true, think: true },
        WRITING: { word: true }
    };
    var GROUP_IDS = { mcq: 'commGrpMcq', media: 'commGrpMedia', rec: 'commGrpRec', think: 'commGrpThink', word: 'commGrpWord' };
    var FIELDS = {
        section_name: 'commQSection', question_type: 'commQType', question_level: 'commQLevel',
        correct_marks: 'commQMarks', negative_marks: 'commQNegative', recording_time_seconds: 'commQRecTime',
        thinking_time_seconds: 'commQThinkTime', word_limit: 'commQWordLimit', instruction_text: 'commQInstruction',
        question_text: 'commQText', media_url: 'commQMedia', options_title: 'commQOptTitle',
        correct_option: 'commQCorrect', option_a: 'commQOptA', option_b: 'commQOptB', option_c: 'commQOptC', option_d: 'commQOptD'
    };
    var LABELS = {
        section_name: 'Section', question_type: 'Type', question_level: 'Level', correct_marks: 'Marks',
        negative_marks: 'Negative marks', recording_time_seconds: 'Recording time', thinking_time_seconds: 'Thinking time',
        word_limit: 'Word limit', instruction_text: 'Instruction', question_text: 'Question text', media_url: 'Audio URL',
        options_title: 'Options title', correct_option: 'Correct option', option_a: 'Option A', option_b: 'Option B',
        option_c: 'Option C', option_d: 'Option D'
    };
    var DEFAULTS = { question_type: 'MCQ', question_level: 'Medium', correct_marks: '5', negative_marks: '0',
                     recording_time_seconds: '45', thinking_time_seconds: '30', word_limit: '150' };

    function applyTypeVisibility() {
        var show = TYPE_SHOW[el('commQType').value] || {};
        Object.keys(GROUP_IDS).forEach(function (key) {
            var node = el(GROUP_IDS[key]);
            if (node) node.style.display = show[key] ? '' : 'none';
        });
    }

    function readForm() {
        var out = {};
        Object.keys(FIELDS).forEach(function (k) { out[k] = String(el(FIELDS[k]).value == null ? '' : el(FIELDS[k]).value).trim(); });
        return out;
    }

    function fillForm(values) {
        Object.keys(FIELDS).forEach(function (k) {
            var v = values[k];
            el(FIELDS[k]).value = v == null ? '' : String(v);
        });
        applyTypeVisibility();
    }

    function clearForm(keepSection) {
        var section = el('commQSection').value;
        var keep = { question_type: el('commQType').value, question_level: el('commQLevel').value,
                     correct_marks: el('commQMarks').value, negative_marks: el('commQNegative').value };
        fillForm({});
        Object.keys(DEFAULTS).forEach(function (k) { el(FIELDS[k]).value = DEFAULTS[k]; });
        if (keepSection) {
            Object.keys(keep).forEach(function (k) { el(FIELDS[k]).value = keep[k]; });
            el('commQSection').value = section;
        }
        applyTypeVisibility();
    }

    function openMethod(which) {
        document.querySelectorAll('#commMethods [data-comm-method]').forEach(function (b) {
            b.classList.toggle('is-active', b.getAttribute('data-comm-method') === which);
        });
        el('commExcelPanel').classList.toggle('is-hidden', which !== 'excel');
        el('commManualPanel').classList.toggle('is-hidden', which !== 'manual');
    }

    function stopEditing() {
        editing = null;
        el('commEditId').value = '';
        el('commManualTitle').textContent = 'Manual entry';
        el('commSaveLabel').textContent = 'Add Question';
        el('commCancelEdit').classList.add('is-hidden');
        document.querySelectorAll('.comm-q.is-editing').forEach(function (n) { n.classList.remove('is-editing'); });
    }

    function paintSections() {
        var tbody = document.querySelector('#commSectionsTable tbody');
        tbody.innerHTML = sections.length ? '' : '<tr><td colspan="7" class="text-muted">No sections yet - add the first one below.</td></tr>';
        sections.forEach(function (s) {
            var tr = document.createElement('tr');
            tr.innerHTML = '<td>' + esc(s.section_order) + '</td>' +
                '<td><code>' + esc(s.section_name) + '</code></td>' +
                '<td>' + esc(s.section_title) + '</td>' +
                '<td class="small text-muted">' + esc(s.section_instruction || '') + '</td>' +
                '<td>' + esc(s.section_duration_seconds) + '</td>' +
                '<td>' + esc(s.question_count) + '</td>' +
                '<td class="text-nowrap"><button type="button" class="btn btn-outline-secondary btn-sm comm-edit-sec me-1" data-id="' + esc(s.id) + '" title="Edit section"><i class="fas fa-pen"></i></button>' +
                '<button type="button" class="btn btn-outline-danger btn-sm comm-del-sec" data-id="' + esc(s.id) + '" title="Delete section"><i class="fas fa-trash"></i></button></td>';
            tbody.appendChild(tr);
        });
        ['commQSection', 'commViewSection'].forEach(function (selId) {
            var sel = el(selId);
            var prev = sel.value;
            sel.innerHTML = sections.map(function (s) {
                return '<option value="' + esc(s.section_name) + '" data-sid="' + esc(s.section_id) + '">' +
                    esc(s.section_name) + ' - ' + esc(s.section_title) + ' (' + esc(s.question_count) + ')</option>';
            }).join('');
            if (prev && sections.some(function (s) { return s.section_name === prev; })) sel.value = prev;
        });
    }

    function loadSections() {
        return send('/api/comm-sections/' + descId).then(function (res) {
            sections = Array.isArray(res.d) ? res.d : [];
            paintSections();
            loadQuestionList();
        }).catch(function () { say('Could not load the sections. Refresh the page.'); });
    }

    function selectedIds() {
        return questions.map(function (q) { return q.id; }).filter(function (id) { return selected[id]; });
    }

    function paintSelection() {
        var picked = selectedIds().length;
        el('commSelectedCount').textContent = picked + ' selected';
        var btn = el('commDeleteSelected');
        btn.disabled = picked === 0;
        btn.innerHTML = '<i class="fas fa-trash me-1"></i>Delete selected' + (picked ? ' (' + picked + ')' : '');
        el('commMarksSelected').disabled = picked === 0;
        el('commMoveSelected').disabled = picked === 0;
        var all = el('commSelectAll');
        all.checked = questions.length > 0 && picked === questions.length;
        all.indeterminate = picked > 0 && picked < questions.length;
        all.disabled = questions.length === 0;
    }

    function loadQuestionList() {
        var sel = el('commViewSection');
        var opt = sel.options[sel.selectedIndex];
        var box = el('commQuestionsList');
        questions = [];
        if (!opt) { box.innerHTML = '<p class="text-muted">No sections yet.</p>'; paintSelection(); return; }
        send('/api/questions/' + descId + '?section_id=' + encodeURIComponent(opt.dataset.sid)).then(function (res) {
            var d = res.d || {};
            if (d.max_allowed != null) el('commCountBadge').textContent = d.current_count + ' / ' + d.max_allowed;
            questions = d.questions || [];
            var present = {};
            questions.forEach(function (q) { present[q.id] = true; });
            Object.keys(selected).forEach(function (id) { if (!present[id]) delete selected[id]; });
            if (!questions.length) {
                box.innerHTML = '<p class="text-muted">No questions in this section yet.</p>';
                paintSelection();
                return;
            }
            box.innerHTML = questions.map(function (q, i) {
                var extra = [];
                if (q.recording_time_seconds) extra.push('rec ' + q.recording_time_seconds + 's');
                if (q.thinking_time_seconds) extra.push('think ' + q.thinking_time_seconds + 's');
                if (q.word_limit) extra.push(q.word_limit + ' words');
                if (q.media_url) extra.push('audio');
                if (q.correct_option) extra.push('ans: ' + String(q.correct_option).toUpperCase());
                extra.push('+' + Number(q.correct_marks || 0) + ' / -' + Number(q.negative_marks || 0));
                var opts = ['a', 'b', 'c', 'd'].map(function (k) { return q['option_' + k]; }).filter(Boolean);
                return '<div class="comm-q' + (editing && editing.id === q.id ? ' is-editing' : '') + '" data-qid="' + q.id + '">' +
                    '<input type="checkbox" class="form-check-input comm-q-check mt-1" data-id="' + q.id + '" aria-label="Select question ' + (i + 1) + '"' + (selected[q.id] ? ' checked' : '') + '>' +
                    '<div class="comm-q__body"><span class="badge bg-dark me-1">' + esc(q.question_type) + '</span>' +
                    '<span class="badge bg-light text-dark border me-2">Q' + esc(q.question_number) + '</span>' +
                    esc(q.question_text) +
                    (opts.length ? '<div class="small text-muted mt-1">' + opts.map(esc).join(' | ') + '</div>' : '') +
                    '<div class="small text-muted">' + esc(extra.join(' · ')) + '</div>' +
                    '</div>' +
                    '<div class="comm-q__actions">' +
                    '<button type="button" class="btn btn-outline-secondary btn-sm comm-edit-q" data-id="' + q.id + '" title="Edit"><i class="fas fa-pen"></i></button>' +
                    '<button type="button" class="btn btn-outline-danger btn-sm comm-del-q" data-id="' + q.id + '" title="Delete"><i class="fas fa-trash"></i></button>' +
                    '</div></div>';
            }).join('');
            paintSelection();
            applyFind();
        }).catch(function () { box.innerHTML = '<p class="text-danger">Could not load questions.</p>'; });
    }

    function applyFind() {
        var q = String(el('commFind').value || '').trim().toLowerCase();
        var shown = 0;
        document.querySelectorAll('#commQuestionsList .comm-q').forEach(function (node) {
            var hit = !q || node.textContent.toLowerCase().indexOf(q) > -1;
            node.classList.toggle('qm-hidden-row', !hit);
            if (hit) shown++;
        });
        var old = el('commFindCount');
        if (old) old.remove();
        if (q) el('commSelectedCount').insertAdjacentHTML('afterend', '<span class="text-muted small" id="commFindCount">' + shown + ' of ' + questions.length + ' match</span>');
    }

    function setMarks() {
        var ids = selectedIds();
        if (!ids.length) return;
        window.qmForm({
            title: 'Set marks for ' + ids.length + ' selected question' + (ids.length === 1 ? '' : 's'),
            lead: 'Leave a box empty to keep that value as it is.',
            fields: [{ name: 'correct_marks', label: 'Correct marks', type: 'number', step: '0.01', placeholder: 'e.g. 5' },
                     { name: 'negative_marks', label: 'Negative marks', placeholder: 'e.g. 0.33 or 1/3' }],
            validate: function (v) { return (!v.correct_marks && !v.negative_marks) ? 'Enter correct marks, negative marks, or both.' : null; },
            submitText: 'Continue'
        }).then(function (values) {
            if (!values) return;
            var items = [];
            if (values.correct_marks) items.push({ label: 'Correct marks', value: values.correct_marks });
            if (values.negative_marks) items.push({ label: 'Negative marks', value: values.negative_marks });
            return ask({ tone: 'primary', title: 'Apply these marks to ' + ids.length + ' question' + (ids.length === 1 ? '' : 's') + '?',
                         message: 'Only the selected questions in ' + el('commViewSection').value + ' change.', items: items, confirmText: 'Set marks' })
                .then(function (ok) {
                    if (!ok) return;
                    return send('/api/test-questions/bulk-marks', 'POST', { description_id: descId, ids: ids, correct_marks: values.correct_marks, negative_marks: values.negative_marks })
                        .then(function (res) {
                            say(res.d.message || (res.ok ? 'Marks updated.' : 'Could not update the marks.'), res.ok ? 'success' : 'danger');
                            if (res.ok) loadQuestionList();
                        });
                });
        }).catch(function () { say('Network error. Nothing was changed.'); });
    }

    function moveSelected() {
        var ids = selectedIds();
        if (!ids.length) return;
        var current = el('commViewSection').value;
        var options = sections.filter(function (s) { return s.section_name !== current; }).map(function (s) {
            return { value: s.section_name, label: s.section_name + ' - ' + s.section_title + ' (' + s.question_count + ')' };
        });
        if (!options.length) return say('Add another section in step 1 first - there is nowhere to move them.', 'warning');
        window.qmForm({
            title: 'Move ' + ids.length + ' selected question' + (ids.length === 1 ? '' : 's'),
            lead: 'From ' + current + '. They are added after the last question of the target section, and both sections are renumbered.',
            fields: [{ name: 'target', label: 'Move to section', type: 'select', options: options, value: options[0].value }],
            submitText: 'Continue'
        }).then(function (values) {
            if (!values) return;
            return ask({ tone: 'primary', title: 'Move ' + ids.length + ' question' + (ids.length === 1 ? '' : 's') + ' to ' + values.target + '?',
                         message: 'Student results are not affected. Both sections are renumbered afterwards.',
                         items: [{ label: 'From', value: current }, { label: 'To', value: values.target }], confirmText: 'Move questions' })
                .then(function (ok) {
                    if (!ok) return;
                    return send('/api/test-questions/bulk-move', 'POST', { description_id: descId, ids: ids, section_name: values.target })
                        .then(function (res) {
                            say(res.d.message || (res.ok ? 'Moved.' : 'Could not move the questions.'), res.ok ? 'success' : 'danger');
                            if (res.ok) { selected = {}; loadSections(); }
                        });
                });
        }).catch(function () { say('Network error. Nothing was changed.'); });
    }

    function editSection(id) {
        var sec = sections.filter(function (s) { return String(s.id) === String(id); })[0];
        if (!sec) return;
        window.qmForm({
            title: 'Edit section ' + sec.section_name,
            lead: 'The section name (' + sec.section_name + ') stays; the title, instruction and duration can change.',
            fields: [{ name: 'section_title', label: 'Section title', value: sec.section_title, required: true, maxlength: 255 },
                     { name: 'section_instruction', label: 'Instruction shown to the student', value: sec.section_instruction || '' },
                     { name: 'section_duration_seconds', label: 'Duration (seconds)', type: 'number', value: sec.section_duration_seconds, required: true }],
            validate: function (v) { return (parseInt(v.section_duration_seconds, 10) > 0) ? null : 'Duration must be a number of seconds above 0.'; },
            submitText: 'Continue'
        }).then(function (values) {
            if (!values) return;
            var changes = [];
            if (values.section_title !== sec.section_title) changes.push({ label: 'Title', from: sec.section_title, to: values.section_title });
            if (values.section_instruction !== (sec.section_instruction || '')) changes.push({ label: 'Instruction', from: sec.section_instruction || '(empty)', to: values.section_instruction || '(empty)' });
            if (String(values.section_duration_seconds) !== String(sec.section_duration_seconds)) changes.push({ label: 'Duration (sec)', from: String(sec.section_duration_seconds), to: values.section_duration_seconds });
            if (!changes.length) return say('No changes to save.', 'info');
            return ask({ tone: 'primary', title: 'Save changes to section ' + sec.section_name + '?', itemsTitle: 'What will change', items: changes, confirmText: 'Save changes' })
                .then(function (ok) {
                    if (!ok) return;
                    return send('/api/comm-sections/update/' + sec.id, 'PUT', values).then(function (res) {
                        say(res.d.message || (res.ok ? 'Section updated.' : 'Could not save the section.'), res.ok ? 'success' : 'danger');
                        if (res.ok) loadSections();
                    });
                });
        }).catch(function () { say('Network error. Nothing was changed.'); });
    }

    function startEdit(id) {
        var q = questions.filter(function (x) { return x.id === id; })[0];
        if (!q) return;
        editing = q;
        openMethod('manual');
        var values = {};
        Object.keys(FIELDS).forEach(function (k) { values[k] = q[k]; });
        values.correct_option = q.correct_option ? String(q.correct_option).toLowerCase() : '';
        values.correct_marks = Number(q.correct_marks || 0);
        values.negative_marks = Number(q.negative_marks || 0);
        ['recording_time_seconds', 'thinking_time_seconds', 'word_limit'].forEach(function (k) {
            values[k] = q[k] ? q[k] : '';
        });
        fillForm(values);
        editing.base = readForm();
        el('commEditId').value = q.id;
        el('commManualTitle').textContent = 'Editing question Q' + q.question_number + ' of ' + q.section_name;
        el('commSaveLabel').textContent = 'Save changes';
        el('commCancelEdit').classList.remove('is-hidden');
        document.querySelectorAll('.comm-q').forEach(function (n) {
            n.classList.toggle('is-editing', String(n.getAttribute('data-qid')) === String(q.id));
        });
        el('commManualPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function deleteQuestions(ids) {
        if (!ids.length) return;
        var body = { description_id: descId, ids: ids };
        send('/api/test-questions/bulk-delete', 'POST', Object.assign({ dry_run: true }, body)).then(function (res) {
            if (!res.ok) return say(res.d.message || 'Could not check these questions. Refresh and try again.');
            var n = ids.length;
            var one = n === 1 ? questions.filter(function (q) { return q.id === ids[0]; })[0] : null;
            var what = one ? 'question Q' + one.question_number : n + ' questions';
            return ask({
                tone: 'danger',
                title: n === 1 ? 'Delete ' + what + '?' : 'Delete ' + n + ' selected questions?',
                message: res.d.answers
                    ? res.d.answers + ' student answer(s) from ' + res.d.students + ' student(s) belong to ' + (n === 1 ? 'this question' : 'these questions') + '. Finished test scores are kept.'
                    : 'No student has answered ' + (n === 1 ? 'this question' : 'these questions') + '.',
                items: [{ label: 'Section', value: el('commViewSection').value }, { label: 'Deleting', value: what }],
                note: 'This cannot be undone. The remaining questions are renumbered 1, 2, 3... with no gaps.',
                confirmText: n === 1 ? 'Delete question' : 'Delete ' + n + ' questions'
            }).then(function (ok) {
                if (!ok) return;
                return send('/api/test-questions/bulk-delete', 'POST', body).then(function (r2) {
                    if (!r2.ok) return say(r2.d.message || 'Could not delete. Nothing was removed.');
                    say(r2.d.message || 'Deleted.', 'success');
                    ids.forEach(function (id) { delete selected[id]; });
                    if (editing && ids.indexOf(editing.id) > -1) { stopEditing(); clearForm(true); }
                    loadSections();
                });
            });
        }).catch(function () { say('Network error. Nothing was deleted.'); });
    }

    function saveQuestion() {
        var secSel = el('commQSection');
        if (!secSel.value) return say('Add a section first (step 1).');
        var payload = readForm();
        if (!payload.question_text) return say('Write the question text.');
        var t = payload.question_type;
        if ((t === 'MCQ' || t === 'COMPREHENSION')) {
            if (!payload.option_a || !payload.option_b) return say(t + ' needs at least option A and option B.');
            if (!payload.correct_option) return say('Choose the correct option.');
            if (!payload['option_' + payload.correct_option]) return say('The correct option ' + payload.correct_option.toUpperCase() + ' is empty.');
        }
        var btn = el('commAddQuestionBtn');
        if (editing) {
            var base = editing.base || {};
            var changes = Object.keys(payload).filter(function (k) { return String(payload[k]) !== String(base[k] == null ? '' : base[k]); })
                .map(function (k) { return { label: LABELS[k] || k, from: String(base[k] == null ? '' : base[k]), to: String(payload[k]) }; });
            if (!changes.length) return say('No changes to save.', 'info');
            var id = editing.id;
            return ask({ tone: 'primary', title: 'Save changes to question Q' + editing.question_number + '?',
                         itemsTitle: 'What will change', items: changes, confirmText: 'Save changes' }).then(function (ok) {
                if (!ok) return;
                btn.disabled = true;
                return send('/api/comm-questions/update/' + id, 'PUT', payload).then(function (res) {
                    say(res.d.message || (res.ok ? 'Question updated.' : 'Could not save.'), res.ok ? 'success' : 'danger');
                    if (!res.ok) return;
                    stopEditing();
                    clearForm(true);
                    el('commViewSection').value = payload.section_name;
                    loadSections();
                });
            }).catch(function () { say('Network error. Nothing was saved.'); })
              .finally(function () { btn.disabled = false; });
        }
        btn.disabled = true;
        send('/api/comm-questions/add/' + descId, 'POST', payload).then(function (res) {
            say(res.d.message || (res.ok ? 'Question added.' : 'Failed.'), res.ok ? 'success' : 'danger');
            if (!res.ok) return;
            clearForm(true);
            el('commViewSection').value = payload.section_name;
            loadSections();
        }).catch(function () { say('Could not save the question.'); })
          .finally(function () { btn.disabled = false; });
    }

    window.commPanelOpen = function (desc) {
        descId = desc.id;
        descRow = desc;
        selected = {};
        stopEditing();
        el('commManagementHeader').innerHTML = '<i class="fas fa-comments me-1"></i> Communication Questions - ' +
            esc(desc.subject_title || '') + ' <small class="text-muted">(key: ' + esc(desc.test_key) + ')</small>';
        el('commManagementContainer').classList.remove('is-hidden');
        el('commManagementContainer').style.display = '';
        openMethod(null);
        clearForm(false);
        loadSections();
        el('commManagementContainer').scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    document.addEventListener('DOMContentLoaded', function () {
        var container = el('commManagementContainer');
        if (!container) return;

        el('commQType').addEventListener('change', applyTypeVisibility);
        el('commViewSection').addEventListener('change', function () { selected = {}; loadQuestionList(); });
        el('commMethods').addEventListener('click', function (e) {
            var b = e.target.closest('[data-comm-method]');
            if (!b) return;
            var which = b.getAttribute('data-comm-method');
            if (which === 'excel' && editing) { stopEditing(); clearForm(true); }
            openMethod(which);
        });
        el('commCancelEdit').addEventListener('click', function () { stopEditing(); clearForm(true); });

        el('commAddSectionBtn').addEventListener('click', function () {
            var title = el('commSecTitle').value.trim();
            var dur = parseInt(el('commSecDuration').value, 10);
            if (!title) return say('Give the section a title, for example Speaking.');
            if (!(dur > 0)) return say('Section duration must be a number of seconds, for example 600.');
            send('/api/comm-sections/' + descId, 'POST', {
                section_title: title,
                section_instruction: el('commSecInstruction').value,
                section_duration_seconds: dur
            }).then(function (res) {
                say(res.d.message || (res.ok ? 'Section added.' : 'Failed.'), res.ok ? 'success' : 'danger');
                if (res.ok) {
                    el('commSecTitle').value = '';
                    el('commSecInstruction').value = '';
                    el('commSecDuration').value = '';
                    loadSections();
                }
            }).catch(function () { say('Could not add the section.'); });
        });

        container.addEventListener('change', function (e) {
            var box = e.target.closest('.comm-q-check');
            if (box) {
                if (box.checked) selected[box.dataset.id] = true; else delete selected[box.dataset.id];
                paintSelection();
            }
        });
        el('commSelectAll').addEventListener('change', function () {
            var on = this.checked;
            questions.forEach(function (q) { if (on) selected[q.id] = true; else delete selected[q.id]; });
            document.querySelectorAll('.comm-q-check').forEach(function (b) { b.checked = on; });
            paintSelection();
        });
        el('commDeleteSelected').addEventListener('click', function () { deleteQuestions(selectedIds()); });
        el('commMarksSelected').addEventListener('click', setMarks);
        el('commMoveSelected').addEventListener('click', moveSelected);
        el('commFind').addEventListener('input', applyFind);

        container.addEventListener('click', function (e) {
            var delSec = e.target.closest('.comm-del-sec');
            if (delSec) {
                var sec = sections.filter(function (s) { return String(s.id) === delSec.dataset.id; })[0] || {};
                ask({
                    tone: 'danger',
                    title: 'Delete section ' + (sec.section_name || '') + '?',
                    message: 'The section "' + (sec.section_title || '') + '" and all ' + (sec.question_count || 0) + ' question(s) in it will be removed.',
                    note: 'This cannot be undone.',
                    confirmText: 'Delete section'
                }).then(function (ok) {
                    if (!ok) return;
                    send('/api/comm-sections/delete/' + delSec.dataset.id, 'DELETE').then(function (res) {
                        say(res.d.message || (res.ok ? 'Deleted.' : 'Could not delete the section.'), res.ok ? 'success' : 'danger');
                        if (res.ok) { stopEditing(); loadSections(); }
                    }).catch(function () { say('Could not delete the section.'); });
                });
                return;
            }
            var editSec = e.target.closest('.comm-edit-sec');
            if (editSec) { editSection(editSec.dataset.id); return; }
            var edit = e.target.closest('.comm-edit-q');
            if (edit) { startEdit(Number(edit.dataset.id)); return; }
            var delQ = e.target.closest('.comm-del-q');
            if (delQ) deleteQuestions([Number(delQ.dataset.id)]);
        });

        el('commAddQuestionBtn').addEventListener('click', saveQuestion);

        el('commCsvUploadBtn').addEventListener('click', function () {
            var f = el('commCsvFile').files[0];
            if (!f) return say('Choose a CSV or Excel file first.');
            var fd = new FormData();
            fd.append('csv_file', f);
            var btn = this;
            btn.disabled = true;
            fetch('/api/comm-questions/upload-csv/' + descId, { method: 'POST', body: fd, headers: { 'Accept': 'application/json' } })
                .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, d: d }; }); })
                .then(function (res) {
                    var d = res.d;
                    say(d.message || (res.ok ? 'Done.' : 'Upload failed.'), !res.ok ? 'danger' : (d.inserted_count ? 'success' : 'info'));
                    var errBox = el('commCsvErrors');
                    if (d.errors && d.errors.length) {
                        errBox.classList.remove('is-hidden');
                        errBox.innerHTML = '<li class="list-group-item list-group-item-danger fw-semibold">Nothing was saved - fix these rows and upload the same file again:</li>' +
                            d.errors.map(function (er) {
                                return '<li class="list-group-item list-group-item-warning">Row ' + esc(er.row_number) + ': ' + esc(er.message) + '</li>';
                            }).join('');
                    } else if (d.skipped && d.skipped.length) {
                        errBox.classList.remove('is-hidden');
                        errBox.innerHTML = '<li class="list-group-item list-group-item-primary fw-semibold">Already in this test - these rows were skipped, nothing duplicated:</li>' +
                            d.skipped.map(function (sk) {
                                return '<li class="list-group-item list-group-item-info">Row ' + esc(sk.row_number) + ': ' + esc(sk.message) + '</li>';
                            }).join('');
                    } else {
                        errBox.classList.add('is-hidden');
                        errBox.innerHTML = '';
                    }
                    if (res.ok) {
                        el('commCsvFile').value = '';
                        loadSections();
                    }
                })
                .catch(function () { say('Upload failed. Nothing was saved.'); })
                .finally(function () { btn.disabled = false; });
        });
    });
})();
