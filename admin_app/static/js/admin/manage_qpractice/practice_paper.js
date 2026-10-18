$(document).ready(function() {
    const confirmAction = (opts) => (window.adminConfirm ? window.adminConfirm(opts) : Promise.resolve(window.confirm(opts.title)));
    const toast = (text, kind) => { if (window.adminToast) window.adminToast($('<div>').text(text == null ? '' : String(text)).html(), kind === 'error' ? 'danger' : (kind || 'info')); };
    const plain = (html) => (new DOMParser().parseFromString(html || '', 'text/html').body.textContent || '').replace(/\s+/g, ' ').trim();
    let quillEditors = {};
    let currentSearchResults = [];
    let currentQuestionIndex = 0;

    const toolbarOptions = [
        [{'header': [1, 2, 3, 4, 5, 6, false]}],
        ['bold', 'italic', 'underline', 'strike', 'link'],
        [{'script': 'sub'}, {'script': 'super'}],
        ['blockquote', 'code-block'],
        [{'list': 'ordered'}, {'list': 'bullet'}, {'indent': '-1'}, {'indent': '+1'}],
        [{'align': []}],
        ['image', 'video', 'formula'],
        [{'color': []}, {'background': []}],
        ['clean']
    ];

    function selectLocalImage(editor) {
        const input = document.createElement('input');
        input.setAttribute('type', 'file');
        input.setAttribute('accept', 'image/*');
        input.click();
        input.onchange = () => {
            if (!input.files[0]) return;
            const formData = new FormData();
            formData.append('image', input.files[0]);
            fetch('/api/upload-quill-image', {method: 'POST', body: formData})
                .then(response => response.json())
                .then(result => {
                    if (result.url) {
                        editor.insertEmbed(editor.getSelection(true).index, 'image', result.url);
                    } else {
                        alert('Image upload failed: ' + (result.error || 'Unknown error'));
                    }
                }).catch(error => {
                    console.error('Error uploading image:', error);
                    alert('An error occurred during image upload.');
                });
        };
    }

    const createQuill = (selectorId) => {
        if (quillEditors[selectorId]) {
            quillEditors[selectorId].setContents([]);
            return quillEditors[selectorId];
        }
        const editor = new Quill(`#${selectorId}`, {
            theme: 'snow',
            modules: {
                toolbar: { container: toolbarOptions, handlers: { 'image': function() { selectLocalImage(this.quill); } } },
                formula: true
            }
        });
        quillEditors[selectorId] = editor;
        return editor;
    };

    const getFullQuestionFormHtml = (prefix) => `
        <input type="hidden" id="${prefix}DbId">
        <div class="row">
            <div class="col-md-3 mb-3"><label class="form-label">Question number</label><input type="number" id="${prefix}QuestionId" class="form-control" min="1" placeholder="next number"><small class="text-muted">${prefix === 'manual' ? 'Leave empty to use the next number in this paper.' : 'Unique inside the paper.'}</small></div>
            <div class="col-md-3 mb-3"><label class="form-label">Question Type</label><select id="${prefix}QuestionType" class="form-select" required><option value="">Select...</option><option>MCQ</option><option>MSQ</option><option>NAT</option></select></div>
            <div class="col-md-3 mb-3"><label class="form-label">Year</label><input type="number" id="${prefix}Year" class="form-control"></div>
            <div class="col-md-3 mb-3"><label class="form-label">Paper Set</label><input type="text" id="${prefix}PaperSet" class="form-control"></div>
        </div>
        <div class="mb-3"><label class="form-label">Question Text</label><div id="${prefix}QuestionText" class="quill-editor"></div></div>
        <div class="mb-3"><label class="form-label">Option A</label><div id="${prefix}OptionA" class="quill-editor"></div></div>
        <div class="mb-3"><label class="form-label">Option B</label><div id="${prefix}OptionB" class="quill-editor"></div></div>
        <div class="mb-3"><label class="form-label">Option C</label><div id="${prefix}OptionC" class="quill-editor"></div></div>
        <div class="mb-3"><label class="form-label">Option D</label><div id="${prefix}OptionD" class="quill-editor"></div></div>
        <div class="mb-3"><label class="form-label">Correct Option</label><input type="text" id="${prefix}CorrectOption" class="form-control" required placeholder="MCQ: B &middot; MSQ: AC &middot; NAT: the numeric answer"></div>
        <div class="mb-3"><label class="form-label">Answer Explanation</label><div id="${prefix}AnswerText" class="quill-editor"></div></div>
        <div class="mb-3"><label class="form-label">Explanation Link</label><input type="text" id="${prefix}ExplanationLink" class="form-control"></div>
        ${prefix === 'manual' ? '<button type="submit" class="btn btn-success w-100 mt-3"><i class="fas fa-plus"></i> Add This Question</button>' : ''}
    `;

    const createAllQuills = (prefix) => ['QuestionText', 'OptionA', 'OptionB', 'OptionC', 'OptionD', 'AnswerText'].forEach(f => createQuill(`${prefix}${f}`));

    const escText = (v) => $('<div>').text(v == null ? '' : String(v)).html();
    function showMessage(selector, type, message, errors = [], skipped = []) {
        let errorHtml = errors.length > 0 ? '<ul class="mb-0 mt-1">' + errors.map(e => `<li>Row ${escText(e.row)}: ${escText(e.error)}</li>`).join('') + '</ul>' : '';
        let skipHtml = skipped.length > 0 ? '<div class="mt-2 small"><strong>Already in this paper - skipped, nothing duplicated:</strong><ul class="mb-0">' + skipped.map(e => `<li>Row ${escText(e.row)}: ${escText(e.error)}</li>`).join('') + '</ul></div>' : '';
        $(selector).removeClass('alert-success alert-danger alert-warning alert-info is-hidden').addClass(`alert-${type}`).html(message + errorHtml + skipHtml).show();
    }
    function refreshNextId() {
        const code = $('#manualPaperCode').val();
        if (!code || !$('#manualQuestionId').length) return;
        $.get('/api/papers/next-id', { paper_code: code }).done(d => { $('#manualQuestionId').attr('placeholder', `next: ${d.next_question_id}`); });
    }

    function populateDropdown(selector, data, defaultOptionText) {
        const dropdown = $(selector);
        dropdown.empty().append($('<option>', { value: '', text: defaultOptionText }));
        $.each(data, (i, item) => {
            dropdown.append($('<option>', { value: item, text: item }));
        });
    }

    $.get('/api/papers/codes', (data) => {
        populateDropdown('#csvPaperCode', data, 'Select a Paper Code...');
        populateDropdown('#manualPaperCode', data, 'Select a Paper Code...');
        populateDropdown('#searchPaperCode', data, 'Select Paper Code...');
    }).fail(() => alert('Failed to load paper codes. Please refresh the page.'));

    $('#searchPaperCode').on('change', function() {
        const paperCode = $(this).val();
        const subjectDropdown = $('#searchSubject');
        const topicDropdown = $('#searchTopic');
        subjectDropdown.empty().append('<option value="">Loading...</option>').prop('disabled', true);
        topicDropdown.empty().append('<option value="">All Topics</option>').prop('disabled', true);
        if (paperCode) {
            $.get('/api/papers/subjects', { paper_code: paperCode }, (data) => {
                populateDropdown('#searchSubject', data, 'Select Subject...');
                subjectDropdown.prop('disabled', false);
            }).fail(() => alert('Failed to load subjects.'));
            loadPaperOverview(paperCode);
        } else {
            $('#paperOverview').hide().empty();
        }
        updateExportLinks();
    });

    $('#searchSubject').on('change', function() {
        const paperCode = $('#searchPaperCode').val();
        const subject = $(this).val();
        const topicDropdown = $('#searchTopic');
        topicDropdown.empty().append('<option value="">Loading...</option>').prop('disabled', true);
        if (paperCode && subject) {
            $.get('/api/papers/topics', { paper_code: paperCode, subject: subject }, (data) => {
                populateDropdown('#searchTopic', data, 'All Topics');
                topicDropdown.prop('disabled', data.length === 0);
            }).fail(() => alert('Failed to load topics.'));
        }
        updateExportLinks();
    });

    $('#searchTopic').on('change', updateExportLinks);

    function updateExportLinks() {
        const paperCode = $('#searchPaperCode').val();
        const params = new URLSearchParams();
        if (paperCode) params.set('paper_code', paperCode);
        const subject = $('#searchSubject').val();
        const topic = $('#searchTopic').val();
        if (subject) params.set('subject', subject);
        if (topic) params.set('topic', topic);
        const enabled = !!paperCode;
        $('#exportXlsxBtn').toggleClass('disabled', !enabled)
            .attr('href', enabled ? `/api/questions/export-practice?${params.toString()}&fmt=xlsx` : '#');
        $('#exportCsvBtn').toggleClass('disabled', !enabled)
            .attr('href', enabled ? `/api/questions/export-practice?${params.toString()}&fmt=csv` : '#');
    }

    function loadPaperOverview(paperCode) {
        const box = $('#paperOverview');
        box.html('<div class="text-center p-3"><div class="spinner-border spinner-border-sm text-primary"></div></div>').show();
        console.log('[PRACTICE] loading overview for', paperCode);
        $.get('/api/papers/structure', { paper_code: paperCode })
            .done(function(data) {
                const t = data.totals;
                if (!data.subjects.length) {
                    box.html('<div class="alert alert-light border mb-0"><i class="fas fa-box-open me-1"></i> No questions in this paper yet. Upload some above.</div>');
                    return;
                }
                let rows = '';
                data.subjects.forEach(function(s) {
                    rows += `<tr><td>${$('<div>').text(s.subject || '-').html()}</td>
                             <td>${s.topics}</td><td>${s.questions}</td>
                             <td>${s.mcq}</td><td>${s.msq}</td><td>${s.nat}</td><td>${s.years}</td></tr>`;
                });
                box.html(`
                    <div class="card">
                      <div class="card-header py-2"><strong><i class="fas fa-sitemap me-1"></i> Paper Overview</strong>
                        <span class="badge bg-secondary ms-2">${t.subjects} subject(s)</span>
                        <span class="badge bg-secondary ms-1">${t.questions} question(s)</span>
                        <span class="badge bg-secondary ms-1">MCQ ${t.mcq} · MSQ ${t.msq} · NAT ${t.nat}</span>
                      </div>
                      <div class="table-responsive">
                        <table class="table table-sm table-bordered mb-0">
                          <thead><tr><th>Subject</th><th>Topics</th><th>Questions</th><th>MCQ</th><th>MSQ</th><th>NAT</th><th>Years</th></tr></thead>
                          <tbody>${rows}</tbody>
                        </table>
                      </div>
                    </div>`);
            })
            .fail(function() {
                box.html('<div class="alert alert-danger mb-0">Could not load the paper overview.</div>');
            });
    }

    $('#uploadCsvForm').on('submit', function(e) {
        e.preventDefault();
        const formData = new FormData();
        formData.append('paper_code', $('#csvPaperCode').val());
        formData.append('csv_file', $('#csvFile')[0].files[0]);
        if (!$('#csvPaperCode').val()) { toast('Pick the paper code first.', 'error'); return; }
        if (!$('#csvFile')[0].files[0]) { toast('Choose the .xlsx or .csv file first.', 'error'); return; }
        $.ajax({
            url: '/api/questions/upload-csv', type: 'POST', data: formData, processData: false, contentType: false,
            success: (res) => { showMessage('#csvUploadMessage', res.inserted ? 'success' : 'info', `<b>${escText(res.message)}</b>`, [], res.skipped || []); toast(res.message, res.inserted ? 'success' : 'info'); if ($('#searchPaperCode').val() === $('#csvPaperCode').val()) loadPaperOverview($('#csvPaperCode').val()); },
            error: (xhr) => { const r = xhr.responseJSON || {}; showMessage('#csvUploadMessage', 'danger', `<b>${escText(r.message || 'Upload failed.')}</b>`, r.errors || [], r.skipped || []); }
        });
    });

    $('#setManualContextBtn').on('click', function() {
        if (!$('#manualPaperCode').val() || !$('#manualSubject').val()) {
            alert('Paper Code and Subject are required.'); return;
        }
        $('#manualContext').hide();
        $('#manualQuestionForm').html(getFullQuestionFormHtml('manual'));
        createAllQuills('manual');
        const topic = $('#manualTopic').val();
        $('#manualContextDisplay').text(`Adding to: ${$('#manualPaperCode').val()} | ${$('#manualSubject').val()} ${topic ? '| ' + topic : ''}`);
        $('#manualQuestionFormContainer').show();
        refreshNextId();
    });

    $('#resetManualContextBtn').on('click', function() {
        $('#manualQuestionFormContainer').hide();
        $('#manualContext').show().find('input, select').val('');
        $('#manualAddMessage').hide();
    });

    $('#manualQuestionForm').on('submit', function(e) {
        e.preventDefault();
        const payload = {
            paper_code: $('#manualPaperCode').val(), subject: $('#manualSubject').val(), topic: $('#manualTopic').val(),
            question_id: $('#manualQuestionId').val(), question_type: $('#manualQuestionType').val(),
            year: $('#manualYear').val(), paper_set: $('#manualPaperSet').val(),
            question_text: quillEditors.manualQuestionText.root.innerHTML,
            option_a: quillEditors.manualOptionA.root.innerHTML, option_b: quillEditors.manualOptionB.root.innerHTML,
            option_c: quillEditors.manualOptionC.root.innerHTML, option_d: quillEditors.manualOptionD.root.innerHTML,
            correct_option: $('#manualCorrectOption').val(), answer_text: quillEditors.manualAnswerText.root.innerHTML,
            explanation_link: $('#manualExplanationLink').val(),
        };
        $.ajax({
            url: '/api/questions/add-manual', type: 'POST', contentType: 'application/json', data: JSON.stringify(payload),
            success: (res) => {
                toast(res.message, 'success');
                showMessage('#manualAddMessage', 'success', escText(res.message));
                const keep = { type: $('#manualQuestionType').val(), year: $('#manualYear').val(), set: $('#manualPaperSet').val() };
                $('#manualQuestionForm').trigger('reset');
                $('#manualQuestionType').val(keep.type); $('#manualYear').val(keep.year); $('#manualPaperSet').val(keep.set);
                Object.values(quillEditors).forEach(editor => editor.setContents([]));
                refreshNextId();
            },
            error: (xhr) => { const m = xhr.responseJSON?.message || 'Could not add question.'; toast(m, 'error'); showMessage('#manualAddMessage', 'danger', escText(m)); }
        });
    });

    $('#searchBtn').on('click', function() {
        const paperCode = $('#searchPaperCode').val();
        const subject = $('#searchSubject').val();
        if (!paperCode || !subject) {
            alert('Paper Code and Subject are required.');
            return;
        }
        $.get('/api/questions/search', { paper_code: paperCode, subject: subject, topic: $('#searchTopic').val() })
        .done(function(data) {
            $('#resultsSection').show();
            $('#resultsCount').text(`${data.count} question(s) found.`);
            currentSearchResults = data.questions;
            currentQuestionIndex = 0;
            if (data.count > 0) {
                displayQuestion(0);
                $('#questionNavigation, #questionDisplayArea').show();
            } else {
                $('#questionDisplayArea').html('<div class="alert alert-info">No questions match your criteria.</div>').show();
                $('#questionNavigation').hide();
            }
        })
        .fail((xhr) => alert(`Search failed: ${xhr.responseJSON?.message || 'Server error'}`));
    });

    function displayQuestion(index) {
        currentQuestionIndex = index;
        const q = currentSearchResults[index];
        let bodyHtml;
        if (q.question_image) {
            let regions = {};
            try {
                regions = typeof q.option_regions === 'string' ? (JSON.parse(q.option_regions) || {}) : (q.option_regions || {});
            } catch (err) { regions = {}; }
            const src = q.question_image.charAt(0) === '/' ? q.question_image : '/' + q.question_image;
            const boxes = Object.keys(regions).map(l => {
                const r = regions[l];
                return `<div class="piq-view-region" style="left:${r.x}%;top:${r.y}%;width:${r.w}%;height:${r.h}%"><span>${l.toUpperCase()}</span></div>`;
            }).join('');
            bodyHtml = `<div class="piq-view-wrap"><img src="${src}" alt="Question image">${boxes}</div>
                        <p class="mt-2 mb-0"><span class="badge bg-success"><i class="fas fa-image me-1"></i>Image question</span>
                        &nbsp;Correct answer: <strong>${q.correct_option || '-'}</strong></p>`;
        } else {
            bodyHtml = `<div class="question-render">${q.question_text || ''}</div>`;
        }
        const questionHtml = `
            <div class="card shadow-sm">
                <div class="card-header bg-light d-flex justify-content-between align-items-center">
                    <strong>Question #${q.question_id}</strong> <span class="text-muted small">${index + 1} of ${currentSearchResults.length}</span>
                    <div>
                        <button class="btn btn-warning btn-sm edit-btn" data-index="${index}"><i class="fas fa-edit"></i> Edit</button>
                        <button class="btn btn-danger btn-sm delete-btn" data-id="${q.id}"><i class="fas fa-trash"></i> Delete</button>
                    </div>
                </div>
                <div class="card-body">${bodyHtml}</div>
            </div>`;
        $('#questionDisplayArea').html(questionHtml);
        if(window.renderMathInElement) {
            renderMathInElement(document.getElementById('questionDisplayArea'), { delimiters: [{left: "$$", right: "$$", display: true}, {left: "$", right: "$", display: false}], throwOnError: false });
        }
        if(window.hljs) {
            document.querySelectorAll('#questionDisplayArea pre').forEach(block => hljs.highlightElement(block));
        }
        $('#prevQuestionBtn').prop('disabled', index === 0);
        $('#nextQuestionBtn').prop('disabled', index === currentSearchResults.length - 1);
    }

    $('#prevQuestionBtn').on('click', () => { if (currentQuestionIndex > 0) displayQuestion(currentQuestionIndex - 1); });
    $('#nextQuestionBtn').on('click', () => { if (currentQuestionIndex < currentSearchResults.length - 1) displayQuestion(currentQuestionIndex + 1); });

    $(document).on('click', '#questionDisplayArea .edit-btn', function() {
        const q = currentSearchResults[$(this).data('index')];
        if (q.question_image && typeof window.ppiqOpenForEdit === 'function') {
            window.ppiqOpenForEdit(q);
            if (typeof window.ppShowView === 'function') window.ppShowView('image');
            return;
        }
        $('#editQuestionForm').html(getFullQuestionFormHtml('edit'));
        createAllQuills('edit');
        $('#editDbId').val(q.id);
        $('#editQuestionId').val(q.question_id);
        $('#editQuestionType').val(q.question_type);
        $('#editYear').val(q.year);
        $('#editPaperSet').val(q.paper_set);
        quillEditors.editQuestionText.root.innerHTML = q.question_text || '';
        quillEditors.editOptionA.root.innerHTML = q.option_a || '';
        quillEditors.editOptionB.root.innerHTML = q.option_b || '';
        quillEditors.editOptionC.root.innerHTML = q.option_c || '';
        quillEditors.editOptionD.root.innerHTML = q.option_d || '';
        $('#editCorrectOption').val(q.correct_option);
        quillEditors.editAnswerText.root.innerHTML = q.answer_text || '';
        $('#editExplanationLink').val(q.explanation_link);
        editBaseline = editPayload(q);
        $('#editQuestionModal').modal('show');
    });
    let editBaseline = null;
    function editPayload(original_question) {
        return {
            paper_code: original_question.paper_code, subject: original_question.subject, topic: original_question.topic,
            question_id: $('#editQuestionId').val(), question_type: $('#editQuestionType').val(),
            year: $('#editYear').val(), paper_set: $('#editPaperSet').val(),
            question_text: quillEditors.editQuestionText.root.innerHTML,
            option_a: quillEditors.editOptionA.root.innerHTML, option_b: quillEditors.editOptionB.root.innerHTML,
            option_c: quillEditors.editOptionC.root.innerHTML, option_d: quillEditors.editOptionD.root.innerHTML,
            correct_option: $('#editCorrectOption').val(), answer_text: quillEditors.editAnswerText.root.innerHTML,
            explanation_link: $('#editExplanationLink').val(),
        };
    }

    const EDIT_LABELS = { question_id: 'Question number', question_type: 'Type', year: 'Year', paper_set: 'Paper set', question_text: 'Question text',
                          option_a: 'Option A', option_b: 'Option B', option_c: 'Option C', option_d: 'Option D', correct_option: 'Correct answer',
                          answer_text: 'Explanation', explanation_link: 'Explanation link' };
    const RICH = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'answer_text'];
    $('#saveQuestionChangesBtn').on('click', async function() {
        const $btn = $(this);
        if ($btn.prop('disabled')) return;

        const db_id = $('#editDbId').val();
        const original_question = currentSearchResults.find(q => q.id == db_id);
        if (!original_question) {
            toast('This question is no longer in the current results. Search again and reopen it.', 'error');
            $('#editQuestionModal').modal('hide');
            return;
        }
        const payload = editPayload(original_question);
        const base = editBaseline || {};
        const changes = Object.keys(EDIT_LABELS).filter(k => String(payload[k] == null ? '' : payload[k]).trim() !== String(base[k] == null ? '' : base[k]).trim())
            .map(k => RICH.indexOf(k) > -1
                ? (plain(base[k]) === plain(payload[k]) ? { label: EDIT_LABELS[k], value: 'Formatting changed' } : { label: EDIT_LABELS[k], from: plain(base[k]).slice(0, 60), to: plain(payload[k]).slice(0, 60) })
                : { label: EDIT_LABELS[k], from: String(base[k] == null ? '' : base[k]), to: String(payload[k]) });
        if (!changes.length) { toast('No changes to save.', 'info'); return; }
        const ok = await confirmAction({ tone: 'primary', title: `Save changes to question #${original_question.question_id}?`, itemsTitle: 'What will change', items: changes, confirmText: 'Save changes' });
        if (!ok) return;
        $btn.prop('disabled', true);
        $.ajax({
            url: `/api/questions/update/${db_id}`, type: 'PUT', contentType: 'application/json', data: JSON.stringify(payload),
            success: (res) => { toast((res && res.message) || 'Question updated.', 'success'); $('#editQuestionModal').modal('hide'); $('#searchBtn').click(); },
            error: (xhr) => toast(`Update failed: ${xhr.responseJSON?.message || 'Server error'}`, 'error'),
            complete: () => $btn.prop('disabled', false)
        });
    });

    $(document).on('click', '#questionDisplayArea .delete-btn', async function() {
        const id = $(this).data('id');
        const q = currentSearchResults.find(x => x.id == id) || {};
        const ok = await confirmAction({ tone: 'danger', title: `Delete question #${q.question_id || ''}?`,
                                         message: q.question_image ? 'This image question will be removed from the paper.' : plain(q.question_text || '').slice(0, 120),
                                         items: [{ label: 'Paper', value: `${q.paper_code || ''} › ${q.subject || ''}` }], note: 'This cannot be undone.', confirmText: 'Delete question' });
        if (!ok) return;
        $.ajax({
            url: `/api/questions/delete/${id}`, type: 'DELETE',
            success: (res) => { toast((res && res.message) || 'Question deleted.', 'success'); $('#searchBtn').click(); },
            error: (xhr) => toast(`Delete failed: ${xhr.responseJSON?.message || 'Server error'}`, 'error')
        });
    });
});