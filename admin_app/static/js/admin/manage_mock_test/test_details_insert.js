$(document).ready(function() {
    let testDescriptionsTable;
    let currentQuestions = [];
    let currentQuestionIndex = 0;
    let quillEditors = {};
    let activeTestId = null;
    let activeTestDescriptionId = null;
    let activeTestKey = null;
    let activeSectionId = null;
    let activeSectionName = null;
    const fmtMarks = (v) => {
        if (v === null || v === undefined || v === '') return '0';
        const n = Number(v);
        return Number.isNaN(n) ? String(v) : String(n);
    };
    function goToQuestion(num) {
        if (!currentQuestions.length) return;
        let idx = parseInt(num, 10) - 1;
        if (Number.isNaN(idx)) return;
        idx = Math.min(Math.max(idx, 0), currentQuestions.length - 1);
        currentQuestionIndex = idx;
        displayQuestion(currentQuestionIndex);
    }
    function selectLocalImage(editor) {
        const input = document.createElement('input');
        input.setAttribute('type', 'file');
        input.setAttribute('accept', 'image/*');
        input.click();
        input.onchange = () => {
            const file = input.files[0];
            if (file) {
                const formData = new FormData();
                formData.append('image', file);
                fetch('/api/upload-quill-image', { method: 'POST', body: formData })
                .then(response => {
                    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                    return response.json();
                })
                .then(result => {
                    if (result.url) {
                        const range = editor.getSelection(true);
                        editor.insertEmbed(range.index, 'image', result.url);
                    } else {
                        alert('Image upload failed: ' + (result.message || 'Unknown error'));
                    }
                })
                .catch(error => {
                    console.error('Error uploading image:', error);
                    alert('Image upload failed. See console for details.');
                });
            }
        };
    }
    const initQuill = (selector) => {
        if (quillEditors[selector]) {
            quillEditors[selector].setContents([]);
            return;
        }
        const toolbarOptions = [
            [{ 'header': [1, 2, 3, 4, 5, 6, false] }],
            ['bold', 'italic', 'underline', 'strike'],
            [{ 'script': 'sub'}, { 'script': 'super' }],
            ['blockquote', 'code-block'],
            [{ 'list': 'ordered'}, { 'list': 'bullet' }],
            ['link', 'image', 'formula'],
            [{ 'color': [] }, { 'background': [] }], ['clean']
        ];
        const editor = new Quill(`#${selector}`, {
            theme: 'snow',
            modules: {
                toolbar: {
                    container: toolbarOptions,
                    handlers: { 'image': function() { selectLocalImage(this.quill); } }
                },
                formula: true
            }
        });
        quillEditors[selector] = editor;
    };
    ['addQuestionTextEditor', 'addOptionAEditor', 'addOptionBEditor', 'addOptionCEditor', 'addOptionDEditor', 'addAnswerTextEditor', 'editQuestionTextEditor', 'editOptionAEditor', 'editOptionBEditor', 'editOptionCEditor', 'editOptionDEditor', 'editAnswerTextEditor'].forEach(initQuill);
    const confirmAction = (opts) => (window.adminConfirm ? window.adminConfirm(opts) : Promise.resolve(window.confirm(opts.title)));
    const toast = (text, kind) => {
        const safe = $('<div>').text(text == null ? '' : String(text)).html();
        if (window.adminToast) window.adminToast(safe, kind === 'error' ? 'danger' : (kind || 'info'));
    };
    const plain = (html) => {
        const doc = new DOMParser().parseFromString(html || '', 'text/html');
        return (doc.body.textContent || '').replace(/\s+/g, ' ').trim();
    };
    const shorten = (text, max) => (text.length > max ? text.slice(0, max - 1) + '\u2026' : text);
    const loadEditor = (id, html) => {
        const q = quillEditors[id];
        q.setContents(q.clipboard.convert(html || ''), 'silent');
        q.history.clear();
    };
    let sectionsCache = [];
    const selectedIds = new Set();
    let editBaseline = null;
    function showMessage(selector, type, message, isMain = false) {
        const alertDiv = $(selector);
        alertDiv.removeClass('alert-success alert-danger').addClass(`alert-${type}`).html(message).show();
        if(isMain) return;
        setTimeout(() => alertDiv.fadeOut(), 5000);
    }
    $.get('/api/content-for-tests', function(data) {
        const select = $('#testIdSelect');
        data.forEach(item => {
            const opt = $('<option>').val(item.test_id).text(`${item.code ? '[' + item.code + '] ' : ''}${item.title}`);
            select.append(opt);
        });
        window.MT_CONTENT = data;
        document.dispatchEvent(new CustomEvent('mt-content-loaded', { detail: data }));
        console.log('[TESTS] picker loaded with', data.length, 'mock-test item(s)');
    }).fail(function() {
        console.error('[TESTS] could not load the test list');
    });
    testDescriptionsTable = $('#testDescriptionsTable').DataTable({
        ajax: { url: '/api/test-descriptions/0', dataSrc: '' },
        columns: [
            { data: 'id' },
            { data: 'test_key', render: (d) => `<span class="test-key-cell"><code>${d}</code> <button type="button" class="btn btn-outline-secondary btn-sm copy-key-btn" data-key="${d}" title="Copy test key"><i class="fas fa-copy"></i></button></span>` },
            { data: 'subject_title', render: (d,t,r) => `${d}${accessBadge(r.access_label)}${activityBadge(r.student_activity)}${tcsBadge(r)} <br><small class="text-muted">${r.subject_subtitle}</small>` },
            { data: 'total_questions' }, { data: 'total_marks' }, { data: 'total_duration_minutes' },
            { data: null, searchable: false, orderable: false, render: (d,t,r) => `<div class="desc-actions"><button class="btn btn-warning btn-sm edit-desc-btn" data-id="${r.id}" title="Edit"><i class="fas fa-edit"></i></button> <button class="btn btn-danger btn-sm delete-desc-btn" data-id="${r.id}" title="Delete"><i class="fas fa-trash"></i></button> <button class="btn btn-info btn-sm load-questions-btn" data-id="${r.id}" data-test-id="${r.test_id}" data-test-key="${r.test_key}" title="Load Questions"><i class="fas fa-tasks"></i></button> <button class="btn btn-secondary btn-sm details-desc-btn" data-id="${r.id}" data-test-id="${r.test_id}" data-test-key="${r.test_key}" title="Details"><i class="fas fa-circle-info"></i> Details</button>${tcsButtons(r)}</div>` }
        ],
        searching: false, paging: false, info: false
    });
    function contentLabelFor(testId) {
        const item = (window.MT_CONTENT || []).find(i => String(i.test_id) === String(testId));
        return item ? item.label : null;
    }
    function contentItemFor(testId) {
        return (window.MT_CONTENT || []).find(i => String(i.test_id) === String(testId)) || null;
    }
    function addAccessValue() {
        return contentLabelFor(activeTestId) === 'Paid' ? 'inherit' : ($('#addAccessLabel').val() || '');
    }
    function makeTestKey(access) {
        const bytes = new Uint8Array(access === 'free' || access === 'paid' ? 10 : 12);
        window.crypto.getRandomValues(bytes);
        const hex = Array.from(bytes, b => ('0' + b.toString(16)).slice(-2)).join('');
        return access === 'free' ? 'free_' + hex : access === 'paid' ? 'prem_' + hex : hex;
    }
    function setAddFieldsEnabled(on) {
        $('#addTestFields').prop('disabled', !on).toggleClass('opacity-50', !on);
    }
    function noCalculator(testId) {
        const item = contentItemFor(testId);
        return !!item && (item.section === 'coding_test' || item.section === 'communication_test');
    }
    function applyAccessRules(testId) {
        const item = contentItemFor(testId);
        const isTcs = !!item && item.section === 'tcs_test';
        const noCalc = noCalculator(testId);
        $('#addCalcWrap').toggleClass('is-hidden', noCalc);
        $('#addShowCalculator').prop('checked', !noCalc);
        $('#mtDescLead').toggleClass('is-hidden', isTcs);
        $('#mtDescLeadTcs').toggleClass('is-hidden', !isTcs);
        const paid = contentLabelFor(testId) === 'Paid';
        $('#addAccessLabel').toggle(!paid).val('');
        $('#addAccessHelp').toggle(!paid);
        $('#addAccessPaidNote').removeClass('d-none is-hidden').toggle(paid);
        $('#addTestKey').val(paid ? makeTestKey('inherit') : '');
        setAddFieldsEnabled(paid);
        refreshDescUsage(testId);
    }
    function refreshDescUsage(testId) {
        const item = contentItemFor(testId);
        const usage = $('#descUsage'), note = $('#descLimitNote');
        if (!item) { usage.text(''); note.hide(); $('#addDescriptionSubmit').prop('disabled', false); return; }
        const used = Number(item.description_count || 0);
        const cap = item.max_test_descriptions ? Number(item.max_test_descriptions) : null;
        const full = cap !== null && used >= cap;
        usage.text(cap === null
            ? `${used} test description(s) added - no limit set in Course Content.`
            : `${used} of ${cap} test description(s) used.`);
        $('#descLimitText').text(`Limit reached: this content allows ${cap} test description(s). Not allowed to add more - raise the limit in Course Content first.`);
        note.removeClass('d-none is-hidden').toggle(full);
        $('#addDescriptionSubmit').prop('disabled', full);
        console.log('[TESTS] description usage', used, 'of', cap === null ? 'unlimited' : cap);
    }
    function reloadContentMeta() {
        $.get('/api/content-for-tests', function(data) {
            window.MT_CONTENT = data;
            document.dispatchEvent(new CustomEvent('mt-content-loaded', { detail: data }));
            refreshDescUsage(activeTestId);
        });
    }
    function setAddPanel(open) {
        $('#addTestDescriptionContainer').toggleClass('is-hidden', !open);
        $('#mtAddToggle').toggleClass('is-open', open)
            .html(open ? '<i class="fas fa-xmark me-1"></i>Close' : '<i class="fas fa-plus me-1"></i>Add new description');
        if (open) {
            $('#addTestDescriptionContainer')[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
            $('#addAccessLabel:visible').trigger('focus');
        }
    }
    $('#mtAddToggle').on('click', function() { setAddPanel($('#addTestDescriptionContainer').hasClass('is-hidden')); });
    $('#addAccessLabel').on('change', function() {
        const access = $(this).val();
        if (!access) return;
        $('#addTestKey').val(makeTestKey(access));
        setAddFieldsEnabled(true);
        console.log('[TESTS] access chosen:', access, '-> key', $('#addTestKey').val());
    });
    function activityBadge(activity) {
        if (!activity || Object.keys(activity).length === 0) return '';
        const summary = Object.keys(activity).map(k => activity[k] + ' ' + k).join(', ');
        return ` <span class="badge bg-secondary" title="${summary}. Questions can still be edited or deleted; the access and key are fixed."><i class="fas fa-user-check"></i> in use</span>`;
    }
    function tcsBadge(r) {
        if (r.section !== 'tcs_test') return '';
        const t = r.tcs || {};
        return t.published
            ? ' <span class="badge bg-success" title="Students can see and take this exam"><i class="fas fa-eye"></i> Published</span>'
            : ' <span class="badge bg-secondary" title="Hidden from students until you publish it"><i class="fas fa-eye-slash"></i> Draft</span>';
    }
    function tcsButtons(r) {
        if (r.section !== 'tcs_test') return '';
        const t = r.tcs || {};
        return ` <button class="btn btn-dark btn-sm coding-questions-btn" data-id="${r.id}" title="Coding problems of this exam (${t.coding_questions || 0} so far)"><i class="fas fa-code"></i> Coding (${t.coding_questions || 0})</button>` +
               ` <button class="btn btn-sm ${t.published ? 'btn-outline-secondary' : 'btn-success'} tcs-publish-btn" data-id="${r.id}" data-published="${t.published ? 1 : 0}" title="${t.published ? 'Hide this exam from students' : 'Make this exam visible to students'}"><i class="fas fa-${t.published ? 'eye-slash' : 'bullhorn'}"></i> ${t.published ? 'Unpublish' : 'Publish'}</button>`;
    }
    function accessBadge(v) {
        if (v === 'paid') return ' <span class="badge bg-warning text-dark">Premium</span>';
        if (v === 'free') return ' <span class="badge bg-success">Free</span>';
        return '';
    }
    $('#testIdSelect').on('change', function() {
        activeTestId = $(this).val();
        applyAccessRules(activeTestId);
        $('#questionManagementContainer').hide();
        $('#commManagementContainer').hide();
        setAddPanel(false);
        if (typeof window.codingPanelClose === 'function') window.codingPanelClose();
        if (activeTestId) {
            $('#addTestDescriptionTestId').val(activeTestId);
            $('#managementArea').show();
            testDescriptionsTable.ajax.url(`/api/test-descriptions/${activeTestId}`).load();
        } else {
            $('#managementArea').hide();
            testDescriptionsTable.clear().draw();
        }
    });
    $('#generateTestKeyBtn').on('click', function() {
        const access = addAccessValue();
        if (!access) { showMessage('#addTestDescriptionMessage', 'warning', 'Choose Free or Premium first - the key is built from it.'); return; }
        $('#addTestKey').val(makeTestKey(access));
    });
    $('#testDescriptionsTable tbody').on('click', '.load-questions-btn', function() {
        const data = testDescriptionsTable.row($(this).closest('tr')).data();
        activeTestDescriptionId = data.id;
        activeTestId = data.test_id;
        activeTestKey = data.test_key;
        if (data.section === 'coding_test' && typeof window.codingPanelOpen === 'function') {
            $('#questionManagementContainer').hide();
            $('#commManagementContainer').hide();
            window.codingPanelOpen(data);
            return;
        }
        if (typeof window.codingPanelClose === 'function') window.codingPanelClose();
        if (data.section === 'communication_test' || (data.id >= 1000000 && data.section !== 'coding_test')) {
            if (typeof window.commPanelOpen === 'function') {
                $('#questionManagementContainer').hide();
                window.commPanelOpen(data);
                return;
            }
        }
        $('#commManagementContainer').hide();
        $('#questionManagementHeader').text(`Questions - ${data.subject_title} (key ${data.test_key})`);
        $('#questionManagementContainer').show();
        showSectionPicker();
        $('#questionManagementContainer')[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    const escText = (v) => $('<div>').text(v == null ? '' : String(v)).html();

    function structureBadge(status) {
        if (status.questions === 'complete') {
            return '<span class="badge bg-success">Complete - all declared questions uploaded</span>';
        }
        if (status.questions === 'over') {
            return `<span class="badge bg-danger">Over limit - ${status.over_by} more than declared</span>`;
        }
        return `<span class="badge bg-warning text-dark">${status.remaining} question(s) still to upload</span>`;
    }

    function renderStructurePanel(data) {
        const d = data.declared, a = data.actual, st = data.status;
        const marksNote = st.marks_match
            ? '<span class="badge bg-success">Marks match description</span>'
            : `<span class="badge ${st.marks_diff > 0 ? 'bg-danger' : 'bg-warning text-dark'}">Marks ${st.marks_diff > 0 ? 'exceed' : 'short of'} description by ${Math.abs(st.marks_diff)}</span>`;

        let sectionRows = '';
        if (data.sections.length) {
            data.sections.forEach(s => {
                sectionRows += `<tr>
                    <td><code>${escText(s.section_id)}</code>
                        <button class="btn btn-outline-secondary btn-sm copy-section-btn" data-copy="${escText(s.section_id)}" title="Copy Section ID"><i class="fas fa-copy"></i></button></td>
                    <td>${escText(s.section_name)}</td>
                    <td>${s.questions}</td>
                    <td>${s.mcq}</td><td>${s.msq}</td><td>${s.nat}</td>
                    <td>${fmtMarks(s.marks)}</td>
                    <td><button class="btn btn-primary btn-sm use-section-btn" data-sid="${escText(s.section_id)}" data-sname="${escText(s.section_name)}"><i class="fas fa-folder-open"></i> Open</button></td>
                </tr>`;
            });
        } else {
            sectionRows = '<tr><td colspan="8" class="text-center text-muted">No questions uploaded yet - no sections exist.</td></tr>';
        }

        const html = `
            <div class="structure-head">
                <h4><i class="fas fa-sitemap"></i> Structure: ${escText(d.subject_title)} <small class="text-muted">(key ${escText(d.test_key)})</small></h4>
                <div class="structure-head__actions">
                    <a class="btn btn-success btn-sm" href="/api/test-questions/export/${activeTestDescriptionId}?fmt=xlsx" download title="Download all questions as Excel">
                        <i class="fas fa-file-excel"></i> Export Excel
                    </a>
                    <a class="btn btn-outline-success btn-sm" href="/api/test-questions/export/${activeTestDescriptionId}?fmt=csv" download title="Download all questions as CSV">
                        <i class="fas fa-file-csv"></i> Export CSV
                    </a>
                    <button type="button" class="btn-close" id="closeStructureBtn" title="Close"></button>
                </div>
            </div>
            <div class="structure-stats">
                <div class="stat-box"><small>Questions</small><strong>${a.questions} / ${d.total_questions}</strong></div>
                <div class="stat-box"><small>Marks</small><strong>${fmtMarks(a.marks)} / ${fmtMarks(d.total_marks)}</strong></div>
                <div class="stat-box"><small>MCQ</small><strong>${a.mcq}</strong></div>
                <div class="stat-box"><small>MSQ</small><strong>${a.msq}</strong></div>
                <div class="stat-box"><small>NAT</small><strong>${a.nat}</strong></div>
                <div class="stat-box"><small>Duration</small><strong>${d.total_duration_minutes} min</strong></div>
            </div>
            <div class="structure-badges">${structureBadge(st)} ${marksNote}</div>
            <div class="table-responsive">
                <table class="table table-sm table-bordered structure-table">
                    <thead><tr><th>Section ID</th><th>Section Name</th><th>Questions</th><th>MCQ</th><th>MSQ</th><th>NAT</th><th>Marks</th><th></th></tr></thead>
                    <tbody>${sectionRows}</tbody>
                </table>
            </div>`;
        $('#structurePanel').html(html).show();
        $('#structurePanel')[0].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    $('#testDescriptionsTable tbody').on('click', '.coding-questions-btn', function() {
        const data = testDescriptionsTable.row($(this).closest('tr')).data();
        activeTestDescriptionId = data.id;
        activeTestId = data.test_id;
        activeTestKey = data.test_key;
        $('#questionManagementContainer').hide();
        $('#commManagementContainer').hide();
        if (typeof window.codingPanelOpen === 'function') window.codingPanelOpen(Object.assign({}, data, { subject_title: `${data.subject_title} - Coding` }));
    });
    $('#testDescriptionsTable tbody').on('click', '.tcs-publish-btn', async function() {
        const data = testDescriptionsTable.row($(this).closest('tr')).data();
        const t = data.tcs || {};
        const publish = !t.published;
        const ok = await confirmAction({
            tone: publish ? 'primary' : 'danger',
            icon: publish ? 'fa-bullhorn' : 'fa-eye-slash',
            title: publish ? `Publish "${data.subject_title}" to students?` : `Hide "${data.subject_title}" from students?`,
            message: publish ? 'Students enrolled in this course will see the exam and can start it.' : 'Students will no longer see the exam. Finished attempts are kept.',
            items: [{ label: 'Aptitude', value: `${t.aptitude_questions || 0} of ${data.total_questions} questions` }, { label: 'Coding', value: `${t.coding_questions || 0} problem(s)` }],
            confirmText: publish ? 'Publish exam' : 'Unpublish'
        });
        if (!ok) return;
        $.ajax({ url: `/api/test-descriptions/${data.id}/tcs-publish`, type: 'POST', contentType: 'application/json', data: JSON.stringify({ published: publish }) })
            .done(res => { toast(res.message, 'success'); testDescriptionsTable.ajax.reload(); })
            .fail(xhr => toast((xhr.responseJSON && xhr.responseJSON.message) || 'Could not change the exam.', 'error'));
    });
    $('#testDescriptionsTable tbody').on('click', '.details-desc-btn', function() {
        const data = testDescriptionsTable.row($(this).closest('tr')).data();
        activeTestDescriptionId = data.id;
        activeTestId = data.test_id;
        activeTestKey = data.test_key;
        console.log('[TESTS] loading structure for description', data.id);
        $('#structurePanel').html('<div class="text-center p-4"><div class="spinner-border text-primary"></div></div>').show();
        $.get(`/api/test-structure/${data.id}`)
            .done(renderStructurePanel)
            .fail(function(xhr) {
                const msg = xhr.responseJSON ? xhr.responseJSON.message : 'Could not load the structure.';
                $('#structurePanel').html(`<div class="alert alert-danger mb-0">${escText(msg)}</div>`).show();
            });
    });

    $(document).on('click', '#closeStructureBtn', function() { $('#structurePanel').hide().empty(); });

    $(document).on('click', '.copy-key-btn', function(e) {
        e.stopPropagation();
        const btn = $(this);
        navigator.clipboard.writeText(String(btn.data('key'))).then(() => {
            btn.html('<i class="fas fa-check"></i>');
            setTimeout(() => btn.html('<i class="fas fa-copy"></i>'), 1200);
        });
    });

    $(document).on('click', '.copy-section-btn', function() {
        const value = $(this).data('copy');
        navigator.clipboard.writeText(value).then(() => {
            const btn = $(this);
            btn.html('<i class="fas fa-check"></i>');
            setTimeout(() => btn.html('<i class="fas fa-copy"></i>'), 1200);
        });
    });

    function loadSections() {
        if (!activeTestDescriptionId) return $.Deferred().resolve({ sections: [] }).promise();
        return $.get(`/api/test-sections/${activeTestDescriptionId}`).then(function(d) {
            sectionsCache = (d && d.sections) || [];
            renderSectionCards();
            renderSwitchMenu();
            return d;
        }, function() {
            $('#qmSectionList').html('<p class="text-danger mb-0">Could not load the sections. Refresh the page.</p>');
        });
    }

    function renderSectionCards() {
        const box = $('#qmSectionList');
        if (!sectionsCache.length) {
            box.html('<p class="text-muted mb-0"><i class="fas fa-circle-info me-1"></i>No sections yet - create the first one below.</p>');
            return;
        }
        box.html(sectionsCache.map(sec => `
            <button type="button" class="qm-section" data-sid="${escText(sec.section_id)}" data-sname="${escText(sec.section_name)}">
                <span class="qm-section__name">${escText(sec.section_name)}</span>
                <code class="qm-section__id">${escText(sec.section_id)}</code>
                <span class="qm-section__count">${sec.questions} question${sec.questions === 1 ? '' : 's'} &middot; ${fmtMarks(sec.marks)} marks</span>
            </button>`).join(''));
    }

    function renderSwitchMenu() {
        const items = sectionsCache.map(sec => `
            <li><button type="button" class="dropdown-item qm-switch-item${String(sec.section_id) === String(activeSectionId) ? ' active' : ''}"
                        data-sid="${escText(sec.section_id)}" data-sname="${escText(sec.section_name)}">
                <strong>${escText(sec.section_name)}</strong> <code>${escText(sec.section_id)}</code>
                <small>${sec.questions} question${sec.questions === 1 ? '' : 's'}</small></button></li>`).join('');
        $('#qmSwitchMenu').html((items || '<li><span class="dropdown-item-text text-muted">No other sections yet</span></li>') +
            '<li><hr class="dropdown-divider"></li><li><button type="button" class="dropdown-item" id="qmNewSectionItem"><i class="fas fa-folder-plus me-1"></i>Create a new section</button></li>');
    }

    function showSectionPicker() {
        activeSectionId = null;
        activeSectionName = null;
        selectedIds.clear();
        $('#questionControls').hide();
        $('#sectionEntryContainer').show();
        $('#sectionIdInput, #sectionNameInput').val('');
        $('#qmSectionList').html('<p class="text-muted mb-0">Loading sections...</p>');
        loadSections();
    }

    function openSection(sid, sname) {
        activeSectionId = String(sid);
        activeSectionName = String(sname);
        selectedIds.clear();
        console.log('[TESTS] opening section', activeSectionId, activeSectionName);
        $('#sectionEntryContainer').hide();
        $('#questionControls').show();
        $('#currentSectionBadge').text(activeSectionName);
        $('#qmCurrentId').text(activeSectionId);
        $('#qmBatchLink').attr('href', '/manage-tests/image-batch?' + $.param({
            test: activeTestId, desc: activeTestDescriptionId, sid: activeSectionId, sname: activeSectionName
        }));
        renderSwitchMenu();
        fetchQuestionsForDisplay();
    }

    $(document).on('click', '.qm-section, .qm-switch-item', function() {
        openSection($(this).data('sid'), $(this).data('sname'));
    });
    $(document).on('click', '#qmNewSectionItem', function() {
        showSectionPicker();
        $('#sectionIdInput').trigger('focus');
    });

    $(document).on('click', '.use-section-btn', function() {
        $('#commManagementContainer').hide();
        $('#questionManagementHeader').text(`Questions - key ${activeTestKey}`);
        $('#questionManagementContainer').show();
        openSection($(this).data('sid'), $(this).data('sname'));
        loadSections();
        $('#questionManagementContainer')[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    $('#loadQuestionsForSectionBtn').on('click', function() {
        const sid = String($('#sectionIdInput').val() || '').trim();
        const sname = String($('#sectionNameInput').val() || '').trim();
        if (!/^[A-Za-z0-9_-]{1,50}$/.test(sid)) {
            toast('Section ID: 1-50 letters, numbers, - or _ (no spaces), for example SEC1.', 'error');
            return;
        }
        if (!sname) { toast('Give the section a name, for example Physics.', 'error'); return; }
        const existing = sectionsCache.find(sec => String(sec.section_id).toLowerCase() === sid.toLowerCase());
        if (existing) {
            toast(`Section ${existing.section_id} already exists as "${existing.section_name}" - opened it.`, 'info');
            openSection(existing.section_id, existing.section_name);
            return;
        }
        openSection(sid, sname);
        toast(`Section "${sname}" (${sid}) is ready - add its first question.`, 'success');
    });

    function setAddAllowed(isFull) {
        const why = 'Limit reached - edit the description to raise Total Questions.';
        $('.qm-method[data-method]').each(function() {
            const el = $(this);
            el.toggleClass('is-disabled', isFull).attr('title', isFull ? why : '');
            if (el.is('button')) el.prop('disabled', isFull);
            else el.attr('aria-disabled', isFull ? 'true' : null);
        });
    }

    $('#qmBatchLink').on('click', function(e) {
        if ($(this).hasClass('is-disabled')) e.preventDefault();
    });

    function updateSelectionUI() {
        const ids = currentQuestions.map(q => q.id);
        const picked = ids.filter(id => selectedIds.has(id)).length;
        $('#qmSelectedCount').text(`${picked} selected`);
        $('#qmDeleteSelected').prop('disabled', picked === 0)
            .html(`<i class="fas fa-trash me-1"></i>Delete selected${picked ? ' (' + picked + ')' : ''}`);
        $('#qmMarksSelected, #qmMoveSelected').prop('disabled', picked === 0);
        const all = $('#qmSelectAll')[0];
        if (all) {
            all.checked = ids.length > 0 && picked === ids.length;
            all.indeterminate = picked > 0 && picked < ids.length;
            all.disabled = ids.length === 0;
        }
    }

    function renderQuestionList() {
        const rows = currentQuestions.map((q, i) => {
            const text = q.question_image
                ? '<span class="badge bg-success"><i class="fas fa-image me-1"></i>Image question</span>'
                : escText(shorten(plain(q.question_text), 120) || '(no text)');
            return `<tr data-id="${q.id}" class="${i === currentQuestionIndex ? 'is-current' : ''}">
                <td class="qm-col-check"><input type="checkbox" class="form-check-input qm-row-check" data-id="${q.id}" aria-label="Select question ${q.question_number}" ${selectedIds.has(q.id) ? 'checked' : ''}></td>
                <td><strong class="qm-num">Q${escText(q.question_number)}</strong></td>
                <td class="qm-text">${text}</td>
                <td><span class="badge bg-dark">${escText(q.question_type || '')}</span></td>
                <td class="text-nowrap">+${fmtMarks(q.correct_marks)} / -${fmtMarks(q.negative_marks)}</td>
                <td><strong>${escText(q.correct_option || '-')}</strong></td>
                <td class="text-end text-nowrap">
                    <button type="button" class="btn btn-outline-primary btn-sm view-question-btn" data-index="${i}" title="View"><i class="fas fa-eye"></i></button>
                    <button type="button" class="btn btn-outline-secondary btn-sm edit-question-btn" data-id="${q.id}" title="Edit"><i class="fas fa-pen"></i></button>
                    <button type="button" class="btn btn-outline-danger btn-sm delete-question-btn" data-id="${q.id}" title="Delete"><i class="fas fa-trash"></i></button>
                </td></tr>`;
        }).join('');
        $('#qmQuestionTable tbody').html(rows);
        $('#qmQuestionTable').toggle(currentQuestions.length > 0);
        applyFind();
        updateSelectionUI();
    }

    function applyFind() {
        const q = String($('#qmFind').val() || '').trim().toLowerCase();
        let shown = 0;
        $('#qmQuestionTable tbody tr').each(function() {
            const id = Number($(this).data('id'));
            const item = currentQuestions.find(x => x.id === id) || {};
            const hay = [plain(item.question_text), plain(item.option_a), plain(item.option_b), plain(item.option_c), plain(item.option_d),
                         item.question_type, item.correct_option, 'q' + item.question_number].join(' ').toLowerCase();
            const hit = !q || hay.includes(q);
            $(this).toggleClass('qm-hidden-row', !hit);
            if (hit) shown++;
        });
        $('#qmFindCount').remove();
        if (q) $('#qmSelectedCount').after(`<span class="text-muted small" id="qmFindCount">${shown} of ${currentQuestions.length} match</span>`);
    }
    $('#qmFind').on('input', applyFind);

    const selectedList = () => currentQuestions.map(q => q.id).filter(id => selectedIds.has(id));
    const bulkPost = (url, body) => $.ajax({ url, type: 'POST', contentType: 'application/json', data: JSON.stringify(body) });
    const failMsg = (xhr, fallback) => toast((xhr.responseJSON && xhr.responseJSON.message) || fallback, 'error');

    $('#qmMarksSelected').on('click', async function() {
        const ids = selectedList();
        if (!ids.length) return;
        const values = await window.qmForm({
            title: `Set marks for ${ids.length} selected question${ids.length === 1 ? '' : 's'}`,
            lead: 'Leave a box empty to keep that value as it is.',
            fields: [{ name: 'correct_marks', label: 'Correct marks', type: 'number', step: '0.01', placeholder: 'e.g. 2' },
                     { name: 'negative_marks', label: 'Negative marks', placeholder: 'e.g. 0.66 or 2/3' }],
            validate: v => (!v.correct_marks && !v.negative_marks ? 'Enter correct marks, negative marks, or both.' : null),
            submitText: 'Continue'
        });
        if (!values) return;
        const items = [];
        if (values.correct_marks) items.push({ label: 'Correct marks', value: values.correct_marks });
        if (values.negative_marks) items.push({ label: 'Negative marks', value: values.negative_marks });
        const ok = await confirmAction({ tone: 'primary', title: `Apply these marks to ${ids.length} question${ids.length === 1 ? '' : 's'}?`,
                                         message: `Only the selected questions in ${activeSectionName} (${activeSectionId}) change.`, items, confirmText: 'Set marks' });
        if (!ok) return;
        bulkPost('/api/test-questions/bulk-marks', { description_id: activeTestDescriptionId, ids, correct_marks: values.correct_marks, negative_marks: values.negative_marks })
            .done(res => { toast(res.message, 'success'); fetchQuestionsForDisplay(currentQuestionIndex); })
            .fail(xhr => failMsg(xhr, 'Could not update the marks. Nothing was changed.'));
    });

    $('#qmMoveSelected').on('click', async function() {
        const ids = selectedList();
        if (!ids.length) return;
        const others = sectionsCache.filter(sec => String(sec.section_id) !== String(activeSectionId));
        const options = others.map(sec => ({ value: sec.section_id, label: `${sec.section_name} (${sec.section_id}) - ${sec.questions} question${sec.questions === 1 ? '' : 's'}` }));
        options.push({ value: '__new__', label: '+ New section...' });
        const values = await window.qmForm({
            title: `Move ${ids.length} selected question${ids.length === 1 ? '' : 's'}`,
            lead: `From ${activeSectionName} (${activeSectionId}). They are added after the last question of the target section, and both sections are renumbered.`,
            fields: [{ name: 'target', label: 'Move to section', type: 'select', options, value: options[0].value },
                     { name: 'new_id', label: 'New section ID', placeholder: 'e.g. SEC2', maxlength: 50 },
                     { name: 'new_name', label: 'New section name', placeholder: 'e.g. Chemistry', maxlength: 100 }],
            showWhen: [{ field: 'new_id', when: 'target=__new__' }, { field: 'new_name', when: 'target=__new__' }],
            validate: v => {
                if (v.target !== '__new__') return null;
                if (!/^[A-Za-z0-9_-]{1,50}$/.test(v.new_id)) return 'Section ID: 1-50 letters, numbers, - or _ (no spaces).';
                if (!v.new_name) return 'Give the new section a name.';
                return null;
            },
            submitText: 'Continue'
        });
        if (!values) return;
        const target = values.target === '__new__'
            ? { section_id: values.new_id, section_name: values.new_name }
            : { section_id: values.target, section_name: (others.find(sec => String(sec.section_id) === values.target) || {}).section_name || values.target };
        const ok = await confirmAction({ tone: 'primary', title: `Move ${ids.length} question${ids.length === 1 ? '' : 's'} to ${target.section_name} (${target.section_id})?`,
                                         message: 'Student results are not affected. Both sections are renumbered 1, 2, 3... afterwards.',
                                         items: [{ label: 'From', value: `${activeSectionName} (${activeSectionId})` }, { label: 'To', value: `${target.section_name} (${target.section_id})` }],
                                         confirmText: 'Move questions' });
        if (!ok) return;
        bulkPost('/api/test-questions/bulk-move', { description_id: activeTestDescriptionId, ids, section_id: target.section_id, section_name: target.section_name })
            .done(res => { toast(res.message, 'success'); ids.forEach(id => selectedIds.delete(id)); fetchQuestionsForDisplay(0); })
            .fail(xhr => failMsg(xhr, 'Could not move the questions. Nothing was changed.'));
    });

    $('#qmRenameSection').on('click', async function() {
        if (!activeSectionId) return;
        const values = await window.qmForm({
            title: `Rename section ${activeSectionId}`,
            lead: 'The section ID stays the same; only the name shown to you and to students changes.',
            fields: [{ name: 'section_name', label: 'Section name', value: activeSectionName, required: true, maxlength: 100 }],
            submitText: 'Continue'
        });
        if (!values || values.section_name === activeSectionName) return;
        const ok = await confirmAction({ tone: 'primary', title: `Rename section ${activeSectionId}?`, itemsTitle: 'What will change',
                                         items: [{ label: 'Name', from: activeSectionName, to: values.section_name }], confirmText: 'Rename' });
        if (!ok) return;
        bulkPost(`/api/test-sections/${activeTestDescriptionId}/rename`, { section_id: activeSectionId, section_name: values.section_name })
            .done(res => { toast(res.message, 'success'); activeSectionName = values.section_name; $('#currentSectionBadge').text(activeSectionName); fetchQuestionsForDisplay(currentQuestionIndex); })
            .fail(xhr => failMsg(xhr, 'Could not rename the section.'));
    });

    $(document).on('change', '.qm-row-check', function() {
        const id = Number($(this).data('id'));
        if (this.checked) selectedIds.add(id); else selectedIds.delete(id);
        updateSelectionUI();
    });
    $('#qmSelectAll').on('change', function() {
        const on = this.checked;
        currentQuestions.forEach(q => { if (on) selectedIds.add(q.id); else selectedIds.delete(q.id); });
        $('.qm-row-check').prop('checked', on);
        updateSelectionUI();
    });
    $(document).on('click', '.view-question-btn', function() {
        currentQuestionIndex = Number($(this).data('index'));
        displayQuestion(currentQuestionIndex);
        $('#questionsDisplayArea')[0].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });

    function deleteQuestions(ids) {
        if (!ids.length) return;
        const body = { description_id: activeTestDescriptionId, ids: ids };
        $.ajax({ url: '/api/test-questions/bulk-delete', type: 'POST', contentType: 'application/json',
                 data: JSON.stringify(Object.assign({ dry_run: true }, body)) })
            .done(function(info) {
                const n = ids.length;
                const one = n === 1 ? currentQuestions.find(q => q.id === ids[0]) : null;
                const what = one ? `question ${one.question_number}` : `${n} questions`;
                confirmAction({
                    tone: 'danger',
                    title: n === 1 ? `Delete ${what}?` : `Delete ${n} selected questions?`,
                    message: info.answers
                        ? `${info.answers} student answer(s) from ${info.students} student(s) belong to ${n === 1 ? 'this question' : 'these questions'} and will be removed with ${n === 1 ? 'it' : 'them'}. Finished test scores are kept.`
                        : `No student has answered ${n === 1 ? 'this question' : 'these questions'}.`,
                    items: [{ label: 'Section', value: `${activeSectionName} (${activeSectionId})` },
                            { label: 'Deleting', value: what }],
                    note: 'This cannot be undone. The remaining questions are renumbered 1, 2, 3... with no gaps.',
                    confirmText: n === 1 ? 'Delete question' : `Delete ${n} questions`
                }).then(function(ok) {
                    if (!ok) return;
                    $.ajax({ url: '/api/test-questions/bulk-delete', type: 'POST', contentType: 'application/json', data: JSON.stringify(body) })
                        .done(function(res) {
                            toast(res.message, 'success');
                            ids.forEach(id => selectedIds.delete(id));
                            fetchQuestionsForDisplay(Math.max(0, currentQuestionIndex - 1));
                        })
                        .fail(function(xhr) { toast((xhr.responseJSON && xhr.responseJSON.message) || 'Could not delete. Nothing was removed.', 'error'); });
                });
            })
            .fail(function(xhr) { toast((xhr.responseJSON && xhr.responseJSON.message) || 'Could not check these questions. Refresh and try again.', 'error'); });
    }

    $('#qmDeleteSelected').on('click', function() {
        deleteQuestions(currentQuestions.map(q => q.id).filter(id => selectedIds.has(id)));
    });

    function fetchQuestionsForDisplay(targetIndex) {
        if (!activeTestDescriptionId || !activeSectionId) return;
        $.get(`/api/questions/${activeTestDescriptionId}`, { section_id: activeSectionId })
            .done(function(data) {
                currentQuestions = data.questions || [];
                const present = new Set(currentQuestions.map(q => q.id));
                Array.from(selectedIds).forEach(id => { if (!present.has(id)) selectedIds.delete(id); });
                const count = data.current_count, max = data.max_allowed;
                const badge = $('#questionCountBadge');
                badge.removeClass('bg-info bg-success bg-danger text-dark text-white');
                if (count > max) {
                    badge.addClass('bg-danger text-white').text(`Over limit! ${count} uploaded, the description allows ${max}`);
                } else if (count === max) {
                    badge.addClass('bg-success text-white').text(`Test full: ${count} / ${max} questions`);
                } else {
                    badge.addClass('bg-info text-dark').text(`Test: ${count} / ${max} questions (${max - count} left)`);
                }
                const isFull = count >= max;
                setAddAllowed(isFull);
                let hint = $('#limitHint');
                if (!hint.length) {
                    hint = $('<div id="limitHint" class="mt-note mt-note--warn"></div>').insertBefore('.qm-methods').first();
                }
                if (isFull) {
                    hint.html('<i class="fas fa-lock me-1"></i> This test is full. To add more questions, click the ' +
                              '<strong>Edit</strong> (pencil) button on the description above and increase ' +
                              '<strong>Total Questions</strong> - the options here unlock automatically.').show();
                } else {
                    hint.hide();
                }
                $('#currentSectionBadge').text(activeSectionName || '');
                if (currentQuestions.length > 0) {
                    const desired = (typeof targetIndex === 'number') ? targetIndex : 0;
                    currentQuestionIndex = Math.min(Math.max(desired, 0), currentQuestions.length - 1);
                    renderQuestionList();
                    displayQuestion(currentQuestionIndex);
                    $('#questionNavigation').show();
                    $('#noQuestionsMessage').hide();
                } else {
                    renderQuestionList();
                    $('#questionsDisplayArea').empty();
                    $('#questionNavigation').hide();
                    $('#noQuestionsMessage').text('No questions in this section yet - add them with one of the options above.').show();
                }
                loadSections();
            })
            .fail(() => {
                currentQuestions = [];
                renderQuestionList();
                $('#questionsDisplayArea').empty();
                $('#questionNavigation').hide();
                $('#noQuestionsMessage').text('Error loading questions. Refresh the page.').show();
            });
    }
    function displayQuestion(index) {
        const question = currentQuestions[index];
        const displayArea = $('#questionsDisplayArea');
        const sectionInfo = activeSectionName ? `Section: ${activeSectionName} &nbsp;|&nbsp; ` : '';
        const marksInfo = `${question.question_type || ''} &nbsp;|&nbsp; +${fmtMarks(question.correct_marks)} / -${fmtMarks(question.negative_marks)}`;

        let contentHtml;
        if (question.question_image) {
            let regions = {};
            try {
                regions = typeof question.option_regions === 'string'
                    ? JSON.parse(question.option_regions)
                    : (question.option_regions || {});
            } catch (err) { regions = {}; }
            const src = question.question_image.charAt(0) === '/' ? question.question_image : '/' + question.question_image;
            const boxes = Object.keys(regions).map(l => {
                const r = regions[l];
                return `<div class="iq-view-region" style="left:${r.x}%;top:${r.y}%;width:${r.w}%;height:${r.h}%"><span>${l.toUpperCase()}</span></div>`;
            }).join('');
            contentHtml = `<div class="iq-view-wrap"><img src="${src}" alt="Question image">${boxes}</div>
                           <p class="mt-2 mb-0"><span class="badge bg-success"><i class="fas fa-image me-1"></i>Image question</span>
                           &nbsp;Correct answer: <strong>${question.correct_option || '-'}</strong></p>`;
        } else {
            contentHtml = question.question_text || 'N/A';
        }

        const questionHtml = `<div class="question-display-card">
                                  <div class="card-header">
                                      <h5 class="mb-0">Question ${escText(question.question_number)} <small class="text-muted fw-normal">${index + 1} of ${currentQuestions.length} in this section</small></h5>
                                      <div>
                                          <button class="btn btn-outline-secondary btn-sm edit-question-btn" data-id="${question.id}"><i class="fas fa-edit"></i> Edit</button>
                                          <button class="btn btn-outline-danger btn-sm delete-question-btn" data-id="${question.id}"><i class="fas fa-trash"></i> Delete</button>
                                      </div>
                                  </div>
                                  <div class="px-3 pt-2"><small class="text-muted">${sectionInfo}${marksInfo}</small></div>
                                  <div class="question-content-container">${contentHtml}</div>
                              </div>`;
        displayArea.html(questionHtml);
        $('#qmQuestionTable tbody tr').removeClass('is-current').eq(index).addClass('is-current');
        renderMathInElement(displayArea[0], { delimiters: [{left: "$$", right: "$$", display: true}, {left: "$", right: "$", display: false}], throwOnError : false });
        displayArea.find('pre').each(function(i, block) { hljs.highlightElement(block); });
        $('#prevQuestionBtn').prop('disabled', index === 0);
        $('#nextQuestionBtn').prop('disabled', index === currentQuestions.length - 1);
    }
    $('#uploadQuestionsCsvForm').on('submit', function(e) {
        e.preventDefault();
        const form = $(this), submitBtn = $('#uploadCsvSubmitBtn'), spinner = submitBtn.find('.spinner-border'), messageDiv = $('#csvUploadMessage'), errorDiv = $('#csvUploadErrors'), errorList = $('#csvErrorList');
        submitBtn.prop('disabled', true);
        spinner.show();
        messageDiv.hide();
        errorDiv.hide();
        errorList.empty();
        const file = $('#csvFile')[0].files[0];
        if (!file) { toast('Choose the .xlsx or .csv file first.', 'error'); submitBtn.prop('disabled', false); spinner.hide(); return; }
        const formData = new FormData();
        formData.append('csv_file', file);
        formData.append('test_id', activeTestId);
        formData.append('test_key', activeTestKey);
        formData.append('test_description_id', activeTestDescriptionId);
        formData.append('section_id', activeSectionId);
        formData.append('section_name', activeSectionName);
        $.ajax({
            url: '/api/test-questions/upload-csv', type: 'POST', data: formData, processData: false, contentType: false,
            success: (res) => {
                toast(res.message, res.inserted_count ? 'success' : 'info');
                fetchQuestionsForDisplay(currentQuestionIndex);
                if (res.skipped && res.skipped.length) {
                    $('#csvUploadErrors h6').text('Already in this test - these rows were skipped, nothing duplicated:').removeClass('text-danger').addClass('text-primary');
                    errorDiv.removeClass('is-hidden').show();
                    res.skipped.forEach(sk => errorList.append(`<li class="list-group-item list-group-item-info">Row ${escText(sk.row_number)}: ${escText(sk.message)}</li>`));
                } else {
                    $('#uploadQuestionsCsvModal').modal('hide');
                }
            },
            error: (xhr) => {
                const res = xhr.responseJSON || {};
                toast(res.message || 'The upload failed. Nothing was saved.', 'error');
                if (res.errors && res.errors.length) {
                    errorDiv.removeClass('is-hidden').show();
                    res.errors.forEach(err => errorList.append(
                        `<li class="list-group-item list-group-item-warning">Row ${escText(err.row_number)}: ${escText(err.message)}</li>`));
                }
            },
            complete: () => { submitBtn.prop('disabled', false); spinner.hide(); form[0].reset(); }
        });
    });
    $('#uploadQuestionsCsvModal, #addQuestionModal, #imageQuestionModal').on('show.bs.modal', function () {
        $(this).find('.qm-target').text(activeSectionName ? `- section ${activeSectionName} (${activeSectionId})` : '');
    });
    $('#uploadQuestionsCsvModal').on('show.bs.modal', function () {
        $('#csvErrorList').empty();
        $('#csvUploadErrors').addClass('is-hidden').hide();
        $('#csvUploadErrors h6').text('Nothing was saved - fix these rows and upload the same file again:').removeClass('text-primary').addClass('text-danger');
    });
    $('#uploadQuestionsCsvModal').on('hidden.bs.modal', function () {
        $('#csvUploadMessage').hide();
        $('#csvUploadErrors').hide();
        $('#uploadCsvSubmitBtn').prop('disabled', false).find('.spinner-border').hide();
    });
    $('#addTestDescriptionForm').on('submit', function(e) {
        e.preventDefault();
        const payload = { test_id: $('#addTestDescriptionTestId').val(), test_key: $('#addTestKey').val(), subject_title: $('#addSubjectTitle').val(), subject_subtitle: $('#addSubjectSubtitle').val(), total_questions: $('#addTotalQuestions').val(), total_marks: $('#addTotalMarks').val(), total_duration_minutes: $('#addTotalDurationMinutes').val(), show_calculator: $('#addShowCalculator').is(':checked') ? 1 : 0, access_label: addAccessValue() || '' };
        if (!payload.access_label) { showMessage('#addTestDescriptionMessage', 'warning', 'Choose Free or Premium for Test Access first.'); return; }
        $.ajax({
            url: '/api/test-descriptions/add', type: 'POST', contentType: 'application/json', data: JSON.stringify(payload),
            success: (res) => { toast(res.message, 'success'); testDescriptionsTable.ajax.reload(); $('#addTestDescriptionForm')[0].reset(); applyAccessRules(activeTestId); reloadContentMeta(); setAddPanel(false); },
            error: (xhr) => showMessage('#addTestDescriptionMessage', 'danger', (xhr.responseJSON && xhr.responseJSON.message) || 'Could not add the test description.')
        });
    });
    $('#testDescriptionsTable tbody').on('click', '.delete-desc-btn', function() {
        const data = testDescriptionsTable.row($(this).closest('tr')).data();
        const activity = data.student_activity || {};
        const used = Object.keys(activity).map(k => activity[k] + ' ' + k);
        if (used.length) {
            confirmAction({
                tone: 'blocked',
                title: `"${data.subject_title}" can't be deleted`,
                message: 'Students have already worked on this test:',
                items: used,
                note: 'Their results are kept safe, so the test stays. You can still edit or delete its questions. Nothing was changed.'
            });
            return;
        }
        confirmAction({
            tone: 'danger',
            title: `Delete "${data.subject_title}"?`,
            message: 'The test description and every question inside it will be removed.',
            items: [{ label: 'Key', value: data.test_key }, { label: 'Questions', value: String(data.total_questions) }],
            note: 'This cannot be undone.',
            confirmText: 'Delete test'
        }).then(function(ok) {
            if (!ok) return;
            $.ajax({
                url: `/api/test-descriptions/delete/${data.id}`, type: 'DELETE',
                success: (res) => {
                    toast(res.message, 'success');
                    testDescriptionsTable.ajax.reload();
                    reloadContentMeta();
                    if (String(activeTestDescriptionId) === String(data.id)) {
                        $('#questionManagementContainer, #commManagementContainer').hide();
                        if (typeof window.codingPanelClose === 'function') window.codingPanelClose();
                        activeTestDescriptionId = null;
                    }
                },
                error: (xhr) => toast((xhr.responseJSON && xhr.responseJSON.message) || 'Could not delete the test.', 'error')
            });
        });
    });
    $('#testDescriptionsTable tbody').on('click', '.edit-desc-btn', function() {
        const data = testDescriptionsTable.row($(this).closest('tr')).data();
        $('#editTestDescriptionId').val(data.id); $('#editTestKey').val(data.test_key); $('#editSubjectTitle').val(data.subject_title); $('#editSubjectSubtitle').val(data.subject_subtitle); $('#editTotalQuestions').val(data.total_questions); $('#editTotalMarks').val(data.total_marks); $('#editTotalDurationMinutes').val(data.total_duration_minutes); $('#editShowCalculator').prop('checked', Number(data.show_calculator) !== 0);
        const noCalcEdit = noCalculator(data.test_id);
        $('#editCalcWrap').toggleClass('is-hidden', noCalcEdit);
        if (noCalcEdit) $('#editShowCalculator').prop('checked', false);
        const paidContent = contentLabelFor(data.test_id) === 'Paid';
        const currentAccess = (data.access_label === 'paid' || data.access_label === 'free') ? data.access_label : (paidContent ? 'inherit' : 'free');
        $('#editAccessLabel').val(currentAccess).prop('disabled', paidContent);
        const activity = data.student_activity || {};
        const used = Object.keys(activity).length > 0;
        $('#editAccessLabel').prop('disabled', paidContent || used);
        $('#editAccessNote').text(paidContent
            ? 'This content is Paid: buying it unlocks every test, so there is no per-test premium setting.'
            : (used
                ? 'Students have already worked on this test (' + Object.keys(activity).map(k => activity[k] + ' ' + k).join(', ')
                  + '), so its access is fixed. Its questions can still be edited or deleted.'
                : 'Free or Premium. Changing it gives the test a new key (free_… / prem_…) and is only possible while no student has attempted it.'));
        $('#editTestDescriptionModal').modal('show');
    });
    $('#editTestDescriptionForm').on('submit', async function(e) {
        e.preventDefault();
        const id = $('#editTestDescriptionId').val();
        const payload = { subject_title: $('#editSubjectTitle').val(), subject_subtitle: $('#editSubjectSubtitle').val(), total_questions: $('#editTotalQuestions').val(), total_marks: $('#editTotalMarks').val(), total_duration_minutes: $('#editTotalDurationMinutes').val(), show_calculator: $('#editShowCalculator').is(':checked') ? 1 : 0, access_label: $('#editAccessLabel').val() || 'inherit' };
        const row = (testDescriptionsTable.rows().data().toArray() || []).find(r => String(r.id) === String(id)) || {};
        const accessName = { free: 'Free', paid: 'Premium', inherit: 'Unlocked by buying the content' };
        const oldAccess = (row.access_label === 'paid' || row.access_label === 'free') ? row.access_label : 'inherit';
        const fields = [['Subject title', row.subject_title, payload.subject_title], ['Subtitle', row.subject_subtitle, payload.subject_subtitle],
                        ['Total questions', row.total_questions, payload.total_questions], ['Total marks', fmtMarks(row.total_marks), fmtMarks(payload.total_marks)],
                        ['Duration (min)', row.total_duration_minutes, payload.total_duration_minutes],
                        ['Calculator', Number(row.show_calculator) !== 0 ? 'On' : 'Off', payload.show_calculator ? 'On' : 'Off'],
                        ['Access', accessName[oldAccess], accessName[payload.access_label] || payload.access_label]];
        const changes = fields.filter(f => String(f[1] == null ? '' : f[1]).trim() !== String(f[2] == null ? '' : f[2]).trim())
                              .map(f => ({ label: f[0], from: String(f[1] == null ? '' : f[1]), to: String(f[2] == null ? '' : f[2]) }));
        if (!changes.length) { toast('No changes to save.', 'info'); return; }
        const approved = await confirmAction({ tone: 'primary', title: `Save changes to "${row.subject_title || 'this test'}"?`,
                                               itemsTitle: 'What will change', items: changes, confirmText: 'Save changes' });
        if (!approved) return;
        console.log('[TESTS] saving description', id, 'access', payload.access_label);
        $.ajax({
            url: `/api/test-descriptions/update/${id}`, type: 'PUT', contentType: 'application/json', data: JSON.stringify(payload),
            success: (res) => {
                showMessage('#editTestDescriptionMessage', 'success', res.message);
                testDescriptionsTable.ajax.reload();
                $('#editTestDescriptionModal').modal('hide');
                if (String(activeTestDescriptionId) === String(id)) {
                    console.log('[TESTS] description edited; refreshing question limits');
                    if ($('#questionControls').is(':visible')) {
                        fetchQuestionsForDisplay(currentQuestionIndex);
                    }
                    if ($('#structurePanel').is(':visible')) {
                        $.get(`/api/test-structure/${id}`).done(renderStructurePanel);
                    }
                }
            },
            error: (xhr) => showMessage('#editTestDescriptionMessage', 'danger', xhr.responseJSON ? xhr.responseJSON.message : 'Update failed.')
        });
    });
    $('#prevQuestionBtn').on('click', () => { if (currentQuestionIndex > 0) displayQuestion(--currentQuestionIndex); });
    $('#nextQuestionBtn').on('click', () => { if (currentQuestionIndex < currentQuestions.length - 1) displayQuestion(++currentQuestionIndex); });
    $('#jumpToQuestionBtn').on('click', () => goToQuestion($('#jumpToQuestionInput').val()));
    $('#jumpToQuestionInput').on('keypress', (e) => { if (e.which === 13) { e.preventDefault(); goToQuestion($('#jumpToQuestionInput').val()); } });
    let addAnother = false;
    $('#addQuestionAnother').on('click', function() { addAnother = true; });
    $('#addQuestionForm').on('submit', function(e) {
        e.preventDefault();
        const keepGoing = addAnother;
        addAnother = false;
        const payload = {
            test_id: activeTestId, test_key: activeTestKey, test_description_id: activeTestDescriptionId, section_id: activeSectionId, section_name: activeSectionName,
            question_type: $('#addQuestionType').val(), question_level: $('#addQuestionLevel').val(), correct_marks: $('#addCorrectMarks').val(), negative_marks: $('#addNegativeMarks').val(),
            question_text: quillEditors.addQuestionTextEditor.root.innerHTML, option_a: quillEditors.addOptionAEditor.root.innerHTML, option_b: quillEditors.addOptionBEditor.root.innerHTML,
            option_c: quillEditors.addOptionCEditor.root.innerHTML, option_d: quillEditors.addOptionDEditor.root.innerHTML, correct_option: $('#addCorrectOption').val(),
            answer_text: quillEditors.addAnswerTextEditor.root.innerHTML, answer_link: $('#addAnswerLink').val(),
        };
        $.ajax({
            url: '/api/test-questions/add', type: 'POST', contentType: 'application/json', data: JSON.stringify(payload),
            success: (res) => {
                toast(res.message, 'success');
                const keep = { type: $('#addQuestionType').val(), level: $('#addQuestionLevel').val(), marks: $('#addCorrectMarks').val(), neg: $('#addNegativeMarks').val() };
                $('#addQuestionForm')[0].reset();
                ['addQuestionTextEditor', 'addOptionAEditor', 'addOptionBEditor', 'addOptionCEditor', 'addOptionDEditor', 'addAnswerTextEditor'].forEach(id => quillEditors[id].setContents([]));
                fetchQuestionsForDisplay(Number.MAX_SAFE_INTEGER);
                if (keepGoing && (res.remaining === undefined || res.remaining > 0)) {
                    $('#addQuestionType').val(keep.type); $('#addQuestionLevel').val(keep.level); $('#addCorrectMarks').val(keep.marks); $('#addNegativeMarks').val(keep.neg);
                    $('#addQuestionType').trigger('change');
                    quillEditors.addQuestionTextEditor.focus();
                } else {
                    $('#addQuestionModal').modal('hide');
                }
            },
            error: (xhr) => toast((xhr.responseJSON && xhr.responseJSON.message) || 'Could not add the question.', 'error')
        });
    });
    $(document).on('click', '.delete-question-btn', function() { deleteQuestions([Number($(this).data('id'))]); });
    $(document).on('click', '.edit-question-btn', function() {
        const id = $(this).data('id'); const q = currentQuestions.find(q => q.id === id);
        if (q && q.question_image && typeof window.iqOpenForEdit === 'function') {
            window.iqOpenForEdit(q);
            $('#imageQuestionModal').modal('show');
            return;
        }
        $('#editQuestionId').val(q.id); $('#editQuestionType').val(q.question_type); $('#editQuestionLevel').val(q.question_level); $('#editCorrectMarks').val(fmtMarks(q.correct_marks));
        $('#editNegativeMarks').val(fmtMarks(q.negative_marks)); $('#editCorrectOption').val(q.correct_option); $('#editAnswerLink').val(q.answer_link);
        loadEditor('editQuestionTextEditor', q.question_text); loadEditor('editOptionAEditor', q.option_a); loadEditor('editOptionBEditor', q.option_b);
        loadEditor('editOptionCEditor', q.option_c); loadEditor('editOptionDEditor', q.option_d); loadEditor('editAnswerTextEditor', q.answer_text);
        editBaseline = editPayload();
        $('#editQuestionModal').modal('show');
    });
    function editPayload() {
        return {
            question_type: $('#editQuestionType').val(), question_level: $('#editQuestionLevel').val(), correct_marks: $('#editCorrectMarks').val(), negative_marks: $('#editNegativeMarks').val(),
            question_text: quillEditors.editQuestionTextEditor.root.innerHTML, option_a: quillEditors.editOptionAEditor.root.innerHTML, option_b: quillEditors.editOptionBEditor.root.innerHTML,
            option_c: quillEditors.editOptionCEditor.root.innerHTML, option_d: quillEditors.editOptionDEditor.root.innerHTML, correct_option: $('#editCorrectOption').val(),
            answer_text: quillEditors.editAnswerTextEditor.root.innerHTML, answer_link: $('#editAnswerLink').val()
        };
    }
    const EDIT_LABELS = { question_type: 'Type', question_level: 'Level', correct_marks: 'Correct marks', negative_marks: 'Negative marks',
                          question_text: 'Question text', option_a: 'Option A', option_b: 'Option B', option_c: 'Option C', option_d: 'Option D',
                          correct_option: 'Correct answer', answer_text: 'Explanation', answer_link: 'Explanation link' };
    const RICH = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'answer_text'];
    $('#editQuestionForm').on('submit', async function(e) {
        e.preventDefault();
        const id = $('#editQuestionId').val();
        const payload = editPayload();
        const base = editBaseline || {};
        const changes = Object.keys(payload).filter(k => String(payload[k] == null ? '' : payload[k]).trim() !== String(base[k] == null ? '' : base[k]).trim())
            .map(k => RICH.indexOf(k) > -1
                ? (plain(base[k]) === plain(payload[k]) ? { label: EDIT_LABELS[k], value: 'Formatting changed' }
                                                        : { label: EDIT_LABELS[k], from: shorten(plain(base[k]), 60), to: shorten(plain(payload[k]), 60) })
                : { label: EDIT_LABELS[k], from: String(base[k] == null ? '' : base[k]), to: String(payload[k]) });
        if (!changes.length) { toast('No changes to save.', 'info'); return; }
        const cur = currentQuestions.find(q => String(q.id) === String(id)) || {};
        const approved = await confirmAction({ tone: 'primary', title: `Save changes to question ${cur.question_number || ''}?`,
                                               itemsTitle: 'What will change', items: changes, confirmText: 'Save changes' });
        if (!approved) return;
        $.ajax({
            url: `/api/test-questions/update/${id}`, type: 'PUT', contentType: 'application/json', data: JSON.stringify(payload),
            success: (res) => { toast(res.message, 'success'); fetchQuestionsForDisplay(currentQuestionIndex); $('#editQuestionModal').modal('hide'); },
            error: (xhr) => toast((xhr.responseJSON && xhr.responseJSON.message) || 'Could not save the question.', 'error')
        });
    });

    $(document).on('iq-save', function (e) {
        const detail = e.originalEvent ? e.originalEvent.detail : e.detail;

        if (detail.payload.edit_id) {
            $.ajax({
                url: '/api/test-questions/update-image/' + detail.payload.edit_id,
                type: 'PUT',
                contentType: 'application/json',
                data: JSON.stringify(detail.payload),
                success: function (res) {
                    detail.done(true, res.message || 'Image question updated.');
                    if (typeof fetchQuestionsForDisplay === 'function') {
                        fetchQuestionsForDisplay(currentQuestionIndex);
                    }
                },
                error: function (xhr) {
                    detail.done(false, (xhr.responseJSON && xhr.responseJSON.message) || 'Could not update the image question.');
                }
            });
            return;
        }

        const payload = Object.assign({}, detail.payload, {
            test_id: activeTestId,
            test_key: activeTestKey,
            test_description_id: activeTestDescriptionId,
            section_id: activeSectionId,
            section_name: activeSectionName
        });
        if (!payload.test_description_id || !payload.section_id) {
            detail.done(false, 'Load a section first (Load Questions), then add the image question.');
            return;
        }
        $.ajax({
            url: '/api/test-questions/add-image',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(payload),
            success: function (res) {
                detail.done(true, res.message || 'Image question added.');
                if (typeof fetchQuestionsForDisplay === 'function') {
                    fetchQuestionsForDisplay(currentQuestionIndex);
                }
            },
            error: function (xhr) {
                detail.done(false, (xhr.responseJSON && xhr.responseJSON.message) || 'Could not save the image question.');
            }
        });
    });
});

function loadFlaggedQuestions(descriptionId) {
    const box = document.getElementById('flaggedPanel');
    if (!box) return;
    box.innerHTML = '<p class="text-muted mb-0"><i class="fas fa-spinner fa-spin me-1"></i> Loading flagged questions...</p>';
    $.get('/api/test-descriptions/' + descriptionId + '/flagged', function (rows) {
        if (!rows || !rows.length) {
            box.innerHTML = '<p class="text-muted mb-0"><i class="fas fa-flag me-1"></i> No student has flagged any question in this test.</p>';
            return;
        }
        const esc = (v) => $('<div>').text(v == null ? '' : String(v)).html();
        box.innerHTML = '<h5 class="fq-title"><i class="fas fa-flag"></i> Questions flagged by students (' + rows.length + ')</h5>' +
            rows.map(function (r) {
                const text = $('<div>').html(r.question_text || '').text().slice(0, 160);
                return '<div class="fq-item">' +
                    '<div class="fq-item__head"><span class="fq-badge">' + r.flag_count + ' flag' + (r.flag_count > 1 ? 's' : '') + '</span>' +
                    '<strong>Q' + esc(r.question_number) + '</strong> <span class="text-muted">' + esc(r.section_name || r.section_id) + '</span></div>' +
                    '<div class="fq-item__text">' + esc(text) + '</div>' +
                    (r.notes ? '<div class="fq-item__note"><i class="fas fa-comment me-1"></i>' + esc(r.notes) + '</div>' : '') +
                    '<div class="fq-item__by">Flagged by: ' + esc(r.flagged_by || '') + '</div>' +
                    '</div>';
            }).join('');
    }).fail(function () {
        box.innerHTML = '<p class="text-danger mb-0">Could not load flagged questions.</p>';
    });
}

$(document).on('click', '.details-desc-btn', function () {
    loadFlaggedQuestions($(this).data('id'));
});
