(function () {
    'use strict';

    var LANGUAGES = ['python', 'java', 'c', 'cpp', 'csharp', 'javascript'];

    var $ = function (id) { return document.getElementById(id); };
    var CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

    var picker, list, form, newBtn, cancelBtn, langTabs, codeBox;
    var currentQuestion = null;
    var codes = {};          // language -> code, for the approach being edited
    var activeLang = 'python';

    document.addEventListener('DOMContentLoaded', function () {
        picker = $('pcqEdQuestion');
        list = $('pcqEdList');
        form = $('pcqEdForm');
        newBtn = $('pcqEdNew');
        cancelBtn = $('pcqEdCancel');
        langTabs = $('pcqEdLangTabs');
        codeBox = $('pcqEdCode');
        if (!picker || !form) return;

        buildLangTabs();
        loadQuestions();

        picker.addEventListener('change', function () {
            currentQuestion = picker.value || null;
            hideForm();
            if (currentQuestion) {
                newBtn.style.display = '';
                loadEditorials();
            } else {
                newBtn.style.display = 'none';
                list.innerHTML = '';
            }
        });

        newBtn.addEventListener('click', function () { showForm(null); });
        cancelBtn.addEventListener('click', hideForm);
        form.addEventListener('submit', save);
        codeBox.addEventListener('input', function () { codes[activeLang] = codeBox.value; });
    });

    function api(url, options) {
        options = options || {};
        options.headers = Object.assign(
            { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF }, options.headers || {});
        return fetch(url, options).then(function (res) {
            return res.json().catch(function () { return {}; })
                .then(function (data) {
                    if (!res.ok) throw new Error(data.message || 'Request failed');
                    return data;
                });
        });
    }

    function loadQuestions() {
        api('/api/practice-coding/questions')
            .then(function (data) {
                (data.questions || []).forEach(function (q) {
                    var opt = document.createElement('option');
                    opt.value = q.id;
                    opt.textContent = q.title + ' (' + (q.subject || 'General') + ')';
                    picker.appendChild(opt);
                });
            })
            .catch(function () { note('Could not load the question list.', true); });
    }

    function loadEditorials() {
        api('/api/practice-coding/questions/' + currentQuestion + '/editorials')
            .then(function (data) { render(data.editorials || []); })
            .catch(function () { note('Could not load the editorial.', true); });
    }

    function render(rows) {
        list.innerHTML = '';
        if (!rows.length) {
            list.innerHTML = '<p class="text-muted" style="font-size:13px">' +
                'No approaches yet for this question.</p>';
            return;
        }
        rows.forEach(function (row) {
            var langs = Object.keys(row.codes || {});
            var item = document.createElement('div');
            item.className = 'cdp-row d-flex align-items-center gap-3 flex-wrap';
            item.innerHTML =
                '<span class="badge bg-secondary">#' + row.position + '</span>' +
                '<strong style="flex:1;min-width:160px"></strong>' +
                '<span class="text-muted" style="font-size:12px">' +
                    (langs.length ? langs.join(', ') : 'no code') + '</span>' +
                (row.is_published ? '' : '<span class="badge bg-warning text-dark">Draft</span>') +
                '<button type="button" class="btn btn-sm btn-outline-secondary" data-edit>' +
                    '<i class="fas fa-pen"></i></button>' +
                '<button type="button" class="btn btn-sm btn-outline-danger" data-del>' +
                    '<i class="fas fa-trash"></i></button>';
            item.querySelector('strong').textContent = row.title;
            item.querySelector('[data-edit]').addEventListener('click', function () { showForm(row); });
            item.querySelector('[data-del]').addEventListener('click', function () { remove(row); });
            list.appendChild(item);
        });
    }

    function buildLangTabs() {
        langTabs.innerHTML = '';
        LANGUAGES.forEach(function (lang) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-sm ' + (lang === activeLang ? 'btn-primary' : 'btn-outline-secondary');
            btn.textContent = lang;
            btn.dataset.lang = lang;
            btn.addEventListener('click', function () { selectLang(lang); });
            langTabs.appendChild(btn);
        });
    }

    function selectLang(lang) {
        codes[activeLang] = codeBox.value;      // keep the outgoing tab
        activeLang = lang;
        codeBox.value = codes[lang] || '';
        Array.prototype.forEach.call(langTabs.children, function (b) {
            var on = b.dataset.lang === lang;
            b.className = 'btn btn-sm ' + (on ? 'btn-primary' : 'btn-outline-secondary');
            b.textContent = b.dataset.lang + ((codes[b.dataset.lang] || '').trim() ? ' •' : '');
        });
    }

    function showForm(row) {
        form.style.display = '';
        $('pcqEdId').value = row ? row.id : '';
        $('pcqEdTitle').value = row ? row.title : '';
        $('pcqEdPos').value = row ? row.position : (list.children.length + 1);
        $('pcqEdPublished').checked = row ? !!row.is_published : true;
        $('pcqEdIntro').value = row ? (row.intro_html || '') : '';
        $('pcqEdOutro').value = row ? (row.outro_html || '') : '';
        $('pcqEdTime').value = row ? (row.time_complexity || '') : '';
        $('pcqEdSpace').value = row ? (row.space_complexity || '') : '';
        codes = Object.assign({}, (row && row.codes) || {});
        activeLang = 'python';
        codeBox.value = codes.python || '';
        selectLang('python');
        form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function hideForm() {
        form.style.display = 'none';
        codes = {};
    }

    function save(event) {
        event.preventDefault();
        if (!currentQuestion) return;
        codes[activeLang] = codeBox.value;

        var title = $('pcqEdTitle').value.trim();
        if (!title) { note('Give the approach a title first.', true); return; }

        var payload = {
            title: title,
            position: parseInt($('pcqEdPos').value, 10) || 0,
            is_published: $('pcqEdPublished').checked ? 1 : 0,
            intro_html: $('pcqEdIntro').value,
            outro_html: $('pcqEdOutro').value,
            time_complexity: $('pcqEdTime').value,
            space_complexity: $('pcqEdSpace').value,
            codes: codes
        };

        var id = $('pcqEdId').value;
        var url = id ? '/api/practice-coding/editorials/' + id
                     : '/api/practice-coding/questions/' + currentQuestion + '/editorials';

        api(url, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) })
            .then(function () {
                note(id ? 'Approach updated.' : 'Approach added.');
                hideForm();
                loadEditorials();
            })
            .catch(function (err) { note(err.message || 'Could not save the approach.', true); });
    }

    function remove(row) {
        var goDel = window.adminConfirm ? window.adminConfirm({ tone: 'danger', title: 'Delete the approach "' + row.title + '"?', note: 'This cannot be undone.', confirmText: 'Delete' }) : Promise.resolve(confirm('Delete the approach?'));
        goDel.then(function (ok) { if (!ok) return; deleteApproachNow(row); });
        return;
    }
    function deleteApproachNow(row) {
        api('/api/practice-coding/editorials/' + row.id, { method: 'DELETE' })
            .then(function () { note('Approach deleted.'); loadEditorials(); })
            .catch(function (err) { note(err.message || 'Could not delete the approach.', true); });
    }

    function note(message, isError) {
        if (window.adminToast) { window.adminToast(message, isError ? 'error' : 'success'); return; }
        if (isError) alert(message); else console.log(message);
    }
})();
