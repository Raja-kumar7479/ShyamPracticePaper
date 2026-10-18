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

    var questionImage = null;

    var tierBox = el('qzTier');
    tierBox.addEventListener('change', function () {
        tierBox.querySelectorAll('.pcq-tier__opt').forEach(function (opt) {
            opt.classList.toggle('is-active', opt.querySelector('input').checked);
        });
    });
    function setTier(paid) {
        var radio = document.querySelector('input[name="qzTier"][value="' + (paid ? 'paid' : 'free') + '"]');
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
    function showMode(mode) {
        var part = document.querySelector('.cdp-part[data-part="question"]');
        var btn = part.querySelector('.cdp-mode[data-mode="' + mode + '"]');
        if (btn) btn.click();
    }

    function renderPreview() {
        var box = el('qzImagePreview');
        box.innerHTML = '';
        if (!questionImage) return;
        var img = document.createElement('img');
        img.src = questionImage;
        var remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn btn-sm btn-outline-danger';
        remove.innerHTML = '<i class="fas fa-trash"></i> Remove';
        remove.addEventListener('click', function () { questionImage = null; renderPreview(); });
        box.appendChild(img);
        box.appendChild(remove);
    }

    el('qzImagePick').addEventListener('change', function () {
        var file = this.files && this.files[0];
        if (!file) return;
        var input = this;
        var data = new FormData();
        data.append('image', file);
        input.disabled = true;
        fetch('/api/practice-quiz/image', { method: 'POST', body: data })
            .then(function (res) { return res.json().catch(function () { return {}; }); })
            .then(function (json) {
                if (json && json.success) {
                    questionImage = json.url;
                    renderPreview();
                    toast('Image uploaded.', true);
                } else {
                    toast((json && json.message) || 'Upload failed.', false);
                }
            })
            .catch(function () { toast('Upload failed. Please try again.', false); })
            .finally(function () { input.disabled = false; input.value = ''; });
    });

    function buildPayload() {
        var correct = document.querySelector('input[name="qzCorrect"]:checked');
        return {
            subject: el('qzSubject').value,
            question_text: el('qzQuestion').value,
            question_image: questionImage,
            option_a: el('qzOptA').value, option_b: el('qzOptB').value,
            option_c: el('qzOptC').value, option_d: el('qzOptD').value,
            correct_option: correct ? correct.value : '',
            explanation: el('qzExplanation').value,
            is_paid: (document.querySelector('input[name="qzTier"]:checked') || {}).value === 'paid',
            position: el('qzPosition').value
        };
    }

    function resetEditor() {
        el('qzId').value = '';
        ['qzSubject', 'qzQuestion', 'qzOptA', 'qzOptB', 'qzOptC', 'qzOptD',
         'qzExplanation'].forEach(function (id) { el(id).value = ''; });
        el('qzPosition').value = 0;
        setTier(false);
        document.querySelectorAll('input[name="qzCorrect"]').forEach(function (r) { r.checked = false; });
        questionImage = null;
        renderPreview();
        showMode('text');
        el('qzEditorTitle').innerHTML = '<i class="fas fa-plus-circle" style="color:#6b1d2b"></i> Add a question';
        el('qzSaveLabel').textContent = 'Save question';
        el('qzCancelEdit').classList.add('is-hidden');
    }
    el('qzCancelEdit').addEventListener('click', resetEditor);

    el('qzSaveBtn').addEventListener('click', function () {
        var editingId = el('qzId').value;
        var url = editingId ? '/api/practice-quiz/questions/' + editingId
                            : '/api/practice-quiz/questions';
        var go = editingId
            ? ask({ tone: 'primary', title: 'Save changes to this quiz question?', message: 'The stored question, options, answer and explanation are replaced with what is in the form now.', confirmText: 'Save changes' })
            : Promise.resolve(true);
        go.then(function (ok) {
        if (!ok) return;
        el('qzSaveBtn').disabled = true;
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
            .finally(function () { el('qzSaveBtn').disabled = false; });
        });
    });

    function loadForEdit(qid) {
        send('/api/practice-quiz/questions/' + qid).then(function (r) {
            if (!r.ok || !r.data.success) {
                toast('Could not open the question.', false);
                return;
            }
            resetEditor();
            var q = r.data.question;
            el('qzId').value = q.id;
            el('qzSubject').value = q.subject || '';
            el('qzQuestion').value = q.question_text || '';
            el('qzOptA').value = q.option_a || '';
            el('qzOptB').value = q.option_b || '';
            el('qzOptC').value = q.option_c || '';
            el('qzOptD').value = q.option_d || '';
            el('qzExplanation').value = q.explanation || '';
            el('qzPosition').value = q.position || 0;
            setTier(!!q.is_paid);
            var radio = document.querySelector('input[name="qzCorrect"][value="' + q.correct_option + '"]');
            if (radio) radio.checked = true;
            if (q.question_image) {
                questionImage = q.question_image;
                renderPreview();
                showMode('image');
            }
            var label = q.question_text ? q.question_text.slice(0, 60) : (q.subject + ' image question');
            el('qzEditorTitle').innerHTML =
                '<i class="fas fa-pen-to-square" style="color:#6b1d2b"></i> Editing: ' + escapeHtml(label);
            el('qzSaveLabel').textContent = 'Update question';
            el('qzCancelEdit').classList.remove('is-hidden');
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    var list = el('qzList');
    var subjectFilter = el('qzFilterSubject');
    var tierFilter = el('qzFilterTier');
    var statusFilter = el('qzFilterStatus');

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
        send('/api/practice-quiz/questions' + (params.length ? '?' + params.join('&') : ''))
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
                        var t = q.question_text
                            ? escapeHtml(q.question_text.slice(0, 80))
                            : '<i class="fas fa-image"></i> image question';
                        return '<article style="display:flex;align-items:center;gap:14px;padding:13px 16px;margin-bottom:10px;border:1px dashed #d0b9ad;border-radius:10px;background:#fdf8f3">' +
                            '<span class="cd-q__num" style="background:#8a8078">' + (i + 1) + '</span>' +
                            '<div style="flex:1;min-width:0"><strong>' + t + '</strong>' +
                            '<div class="cd-q__meta" style="margin-top:6px">' +
                                '<span class="cd-tag">' + escapeHtml(q.subject) + '</span>' +
                                '<span class="cd-tag">removed</span></div></div>' +
                            '<button type="button" class="btn btn-sm btn-success" data-restore-q="' + q.id + '">' +
                                '<i class="fas fa-rotate-left me-1"></i>Restore</button></article>';
                    }
                    var label = q.question_text
                        ? escapeHtml(q.question_text.slice(0, 90)) + (q.question_text.length > 90 ? '&hellip;' : '')
                        : '<i class="fas fa-image"></i> image question';
                    var tier = q.is_paid
                        ? '<button type="button" class="pcq-flag pcq-flag--paid" data-tier-q="' + q.id + '" title="Click to make Free"><i class="fas fa-crown"></i> Paid</button>'
                        : '<button type="button" class="pcq-flag pcq-flag--free" data-tier-q="' + q.id + '" title="Click to make Paid"><i class="fas fa-unlock"></i> Free</button>';
                    return '<article style="display:flex;align-items:center;gap:14px;padding:13px 16px;margin-bottom:10px;border:1px solid #e6ded6;border-radius:10px;background:#fff">' +
                        '<span class="cd-q__num">' + (i + 1) + '</span>' +
                        '<div style="flex:1;min-width:0"><strong>' + label + '</strong>' +
                        '<div class="cd-q__meta" style="margin-top:6px">' +
                            '<span class="cd-tag">' + escapeHtml(q.subject) + '</span>' +
                            '<span class="cd-tag">Answer: ' + q.correct_option + '</span>' +
                            '<span class="cd-tag">' + q.answer_count + ' answer' + (q.answer_count === 1 ? '' : 's') + '</span>' +
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
            send('/api/practice-quiz/questions/' + restore.getAttribute('data-restore-q') + '/restore', 'PUT')
                .then(function (r) {
                    if (r.ok && r.data.success) { toast('Question restored.', true); loadList(); }
                    else { toast('Could not restore.', false); }
                });
            return;
        }
        var edit = e.target.closest('[data-edit-q]');
        if (edit) { loadForEdit(edit.getAttribute('data-edit-q')); return; }
        var flip = e.target.closest('[data-tier-q]');
        if (flip) {
            var toPaid = flip.classList.contains('pcq-flag--free');
            ask({ tone: 'primary', title: toPaid ? 'Make this question Paid?' : 'Make this question Free?',
                  message: toPaid ? 'Only students with Coding Practice Premium will see it in the quiz.' : 'Every student will see it in the quiz.',
                  confirmText: toPaid ? 'Make Paid' : 'Make Free' }).then(function (ok) {
                if (!ok) return;
                send('/api/practice-quiz/questions/' + flip.getAttribute('data-tier-q') + '/tier', 'PUT')
                    .then(function (r) {
                        if (r.ok && r.data.success) {
                            toast(r.data.is_paid ? 'Now a Paid question.' : 'Now a Free question.', true);
                            loadList();
                        } else { toast('Could not change access.', false); }
                    });
            });
            return;
        }
        var del = e.target.closest('[data-del-q]');
        if (!del) return;
        var card = del.closest('article');
        ask({ tone: 'danger', title: 'Remove this quiz question?', message: (card ? (card.querySelector('strong') || {}).textContent : '') || '',
              note: 'Student results that used it are kept, and you can restore it from the Removed list.', confirmText: 'Remove' }).then(function (ok) {
            if (!ok) return;
            send('/api/practice-quiz/questions/' + del.getAttribute('data-del-q'), 'DELETE')
                .then(function (r) {
                    if (r.ok && r.data.success) { toast('Question removed.', true); loadList(); }
                    else { toast('Could not remove it.', false); }
                });
        });
    });

    var bulkFile = el('qzBulkFile');
    var bulkResult = el('qzBulkResult');
    bulkFile.addEventListener('change', function () {
        var file = bulkFile.files && bulkFile.files[0];
        if (!file) return;
        var data = new FormData();
        data.append('file', file);
        bulkResult.innerHTML = '<div class="alert alert-info py-2 mb-0">Checking the file...</div>';
        fetch('/api/practice-quiz/bulk/upload', { method: 'POST', body: data })
            .then(function (res) { return res.json().catch(function () { return {}; }); })
            .then(function (json) {
                if (json && json.success) {
                    var skipped = (json.skipped || []).map(function (t) { return '<li>' + escapeHtml(t) + '</li>'; }).join('');
                    bulkResult.innerHTML = '<div class="alert alert-inline ' + (json.imported ? 'alert-success' : 'alert-info') + ' py-2 mb-0">' +
                        escapeHtml(json.message || ('Imported ' + json.imported + ' question(s).')) +
                        (skipped ? '<ul class="mb-0 mt-1 small">' + skipped + '</ul>' : '') + '</div>';
                    toast(json.message || ('Imported ' + json.imported + ' question(s).'), true);
                    loadList();
                } else {
                    var items = (json.errors || []).map(function (e) {
                        return '<li>' + escapeHtml(e) + '</li>';
                    }).join('');
                    toast((json && json.message) || 'Upload failed.', false);
                    bulkResult.innerHTML = '<div class="alert alert-inline alert-danger py-2 mb-0">' +
                        escapeHtml((json && json.message) || 'Upload failed.') +
                        (items ? '<ul class="mb-0 mt-1">' + items + '</ul>' : '') + '</div>';
                }
            })
            .catch(function () {
                bulkResult.innerHTML = '<div class="alert alert-danger py-2 mb-0">Network error. Please try again.</div>';
            })
            .finally(function () { bulkFile.value = ''; });
    });

    loadList();
}());
