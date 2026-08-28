/* Solve page: lightweight editor (line numbers, tab support, per-language
 * draft persistence) plus run / submit against the practice judge. */
(function () {
    'use strict';

    var CFG = window.PCP || {};
    var code = document.getElementById('pcCode');
    var gutter = document.getElementById('pcGutter');
    var langSel = document.getElementById('pcLang');
    if (!code || !langSel) return;

    var DRAFT_KEY = 'pcp-draft-' + CFG.questionId + '-';

    // ---------------- editor basics ----------------
    function syncGutter() {
        var lines = code.value.split('\n').length || 1;
        var html = '';
        for (var i = 1; i <= lines; i++) html += i + '\n';
        gutter.textContent = html;
        gutter.scrollTop = code.scrollTop;
    }
    code.addEventListener('scroll', function () { gutter.scrollTop = code.scrollTop; });
    code.addEventListener('input', function () {
        syncGutter();
        try { localStorage.setItem(DRAFT_KEY + langSel.value, code.value); } catch (e) {}
    });
    code.addEventListener('keydown', function (e) {
        if (e.key === 'Tab') {
            e.preventDefault();
            var s = code.selectionStart, en = code.selectionEnd;
            code.value = code.value.slice(0, s) + '    ' + code.value.slice(en);
            code.selectionStart = code.selectionEnd = s + 4;
            syncGutter();
        }
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            run();
        }
    });

    var DEFAULT_RESULT_HTML =
        '<p class="pc-muted">Run your code against the sample cases, or submit to be judged ' +
        'on all test cases (including hidden ones).</p>';

    function resetConsole() {
        var rb = document.getElementById('pcResult');
        if (rb) rb.innerHTML = DEFAULT_RESULT_HTML;
        var co = document.getElementById('pcCustomOut');
        if (co) co.textContent = '';
    }

    function loadLanguage() {
        var lang = langSel.value;
        var draft = null;
        try { draft = localStorage.getItem(DRAFT_KEY + lang); } catch (e) {}
        code.value = draft != null ? draft : ((CFG.templates || {})[lang] || '');
        syncGutter();
        resetConsole();
    }
    langSel.addEventListener('change', loadLanguage);
    loadLanguage();

    // ---------------- io tabs ----------------
    document.querySelectorAll('.pc-io__tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
            document.querySelectorAll('.pc-io__tab').forEach(function (t) {
                t.classList.toggle('is-active', t === tab);
            });
            document.querySelectorAll('.pc-io__body').forEach(function (b) {
                b.classList.toggle('is-hidden', b.getAttribute('data-tab') !== tab.getAttribute('data-tab'));
            });
        });
    });

    // ---------------- splitter ----------------
    var splitter = document.getElementById('pcSplitter');
    if (splitter) {
        var dragging = false;
        splitter.addEventListener('mousedown', function () { dragging = true; document.body.style.userSelect = 'none'; });
        window.addEventListener('mouseup', function () { dragging = false; document.body.style.userSelect = ''; });
        window.addEventListener('mousemove', function (e) {
            if (!dragging) return;
            var pct = Math.min(70, Math.max(25, (e.clientX / window.innerWidth) * 100));
            document.querySelector('.pc-question').style.flexBasis = pct + '%';
        });
    }

    // ---------------- run / submit ----------------
    var resultBox = document.getElementById('pcResult');
    var busy = false;

    function post(url, body) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || ''
            },
            body: JSON.stringify(body)
        }).then(function (res) {
            return res.json().catch(function () { return {}; })
                .then(function (data) { return { status: res.status, data: data }; });
        });
    }

    function esc(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function showResult(r, submitted) {
        var d = r.data;
        if (r.status === 402) {
            resultBox.innerHTML = '<div class="pc-res pc-res--err">' + esc(d.message || 'Subscribe to unlock.') + '</div>';
            return;
        }
        if (r.status !== 200 || d.error && !d.cases) {
            resultBox.innerHTML = '<div class="pc-res pc-res--err">' + esc(d.error || 'Something went wrong.') + '</div>';
            return;
        }
        var head;
        if (!d.compiled) {
            head = '<div class="pc-res pc-res--err"><strong>Compilation Error</strong><pre>' +
                   esc(d.error) + '</pre></div>';
            resultBox.innerHTML = head;
            return;
        }
        var ok = d.verdict === 'AC';
        head = '<div class="pc-res ' + (ok ? 'pc-res--ok' : 'pc-res--err') + '">' +
               '<strong>' + esc(d.verdict_label || d.verdict) + '</strong>' +
               ' - ' + d.passed + '/' + d.total + ' test case' + (d.total === 1 ? '' : 's') + ' passed' +
               (submitted && ok ? ' &middot; Solved! &#127881;' : '') + '</div>';

        var rows = (d.cases || []).map(function (c, i) {
            var pf = c.status === 'PASS' ? 'pass' : 'fail';
            var badge = '<span class="pc-case__badge pc-case__badge--' + pf + '">' + esc(c.status) + '</span>';
            if (c.is_hidden && c.input == null) {
                return '<div class="pc-case pc-case--' + pf + '">' + badge + ' Hidden case ' + (i + 1) + '</div>';
            }
            return '<div class="pc-case pc-case--' + pf + '">' + badge + ' Case ' + (i + 1) +
                   '<div class="pc-case__grid">' +
                   '<div><em>Input</em><pre>' + esc(c.input) + '</pre></div>' +
                   '<div><em>Expected</em><pre>' + esc(c.expected) + '</pre></div>' +
                   '<div><em>Your output</em><pre>' + esc(c.output) + '</pre></div>' +
                   '</div>' +
                   (c.error ? '<pre class="pc-case__err">' + esc(c.error) + '</pre>' : '') +
                   '</div>';
        }).join('');
        resultBox.innerHTML = head + rows;
    }

    function setBusy(on, label) {
        busy = on;
        ['pcRun', 'pcSubmit', 'pcRunCustom'].forEach(function (id) {
            var b = document.getElementById(id);
            if (b) b.disabled = on;
        });
        if (on) {
            var io = document.getElementById('pcIo');
            if (io) io.classList.remove('is-collapsed');
            resultBox.innerHTML = '<div class="pc-res">' + esc(label) + '</div>';
            var resultTab = document.querySelector('.pc-io__tab[data-tab="result"]');
            if (resultTab) resultTab.click();
        }
    }

    function run() {
        if (busy) return;
        setBusy(true, 'Running against the sample cases...');
        post(CFG.runUrl, { question_id: CFG.questionId, language: langSel.value, code: code.value })
            .then(function (r) { showResult(r, false); })
            .catch(function () {
                resultBox.innerHTML = '<div class="pc-res pc-res--err">Network error. Please try again.</div>';
            })
            .finally(function () { setBusy(false); });
    }

    document.getElementById('pcRun').addEventListener('click', run);

    function addSubmission(sub) {
        if (!sub) return;
        var panel = document.querySelector('.pc-lpanel[data-lpanel="submissions"]');
        if (!panel) return;

        var tbody = panel.querySelector('.pc-history tbody');
        if (!tbody) {
            panel.innerHTML =
                '<table class="pc-history"><thead><tr>' +
                '<th>Status</th><th>Language</th><th>Runtime</th><th>Test cases</th><th>When</th>' +
                '</tr></thead><tbody></tbody></table>' +
                '<p class="pc-muted pc-subhint"><i class="fas fa-circle-info"></i> ' +
                'Click a row to see the code you submitted.</p>';
            tbody = panel.querySelector('tbody');
        }

        panel.querySelectorAll('.pc-subrow.is-latest').forEach(function (r) {
            r.classList.remove('is-latest');
        });
        panel.querySelectorAll('.pc-latesttag').forEach(function (t) { t.remove(); });

        var vlow = String(sub.verdict || '').toLowerCase();
        var runtime = sub.runtime_ms != null ? (sub.runtime_ms + ' ms') : 'N/A';

        var row = document.createElement('tr');
        row.className = 'pc-subrow is-latest';
        row.setAttribute('data-subid', sub.id);
        row.innerHTML =
            '<td><span class="pc-verdict pc-verdict--' + esc(vlow) + '">' +
            esc(sub.verdict_label || sub.verdict) + '</span> ' +
            '<span class="pc-latesttag">Latest</span></td>' +
            '<td><span class="pc-langtag">' + esc(sub.language) + '</span></td>' +
            '<td>' + esc(runtime) + '</td>' +
            '<td>' + esc(sub.passed + '/' + sub.total) + '</td>' +
            '<td>' + esc(sub.when || '') + '</td>';

        var codeRow = document.createElement('tr');
        codeRow.className = 'pc-subcode is-hidden';
        codeRow.setAttribute('data-subcode', sub.id);
        var errHtml = sub.error_message
            ? '<pre class="pc-suberr">' + esc(sub.error_message) + '</pre>' : '';
        codeRow.innerHTML = '<td colspan="5">' + errHtml +
            '<pre class="pc-subpre"><code>' + esc(sub.code || '') + '</code></pre></td>';

        row.addEventListener('click', function () {
            var open = !codeRow.classList.contains('is-hidden');
            codeRow.classList.toggle('is-hidden', open);
            row.classList.toggle('is-open', !open);
        });

        tbody.insertBefore(codeRow, tbody.firstChild);
        tbody.insertBefore(row, tbody.firstChild);

        var tab = document.querySelector('.pc-ltab[data-ltab="submissions"]');
        if (tab) {
            var badge = tab.querySelector('.pc-ltab__count');
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'pc-ltab__count';
                tab.appendChild(badge);
            }
            badge.textContent = tbody.querySelectorAll('.pc-subrow').length;
        }

        var meta = document.querySelector('.pc-qmeta');
        if (meta) {
            var solved = meta.querySelector('.pc-solvedtag');
            var attempted = meta.querySelector('.pc-attempttag');
            if (sub.verdict === 'AC') {
                if (attempted) attempted.remove();
                if (!solved) {
                    var s = document.createElement('span');
                    s.className = 'pc-solvedtag';
                    s.innerHTML = '<i class="fas fa-circle-check"></i> Solved';
                    meta.appendChild(s);
                }
            } else if (!solved && !attempted) {
                var a = document.createElement('span');
                a.className = 'pc-attempttag';
                a.innerHTML = '<i class="fas fa-circle-half-stroke"></i> Attempted';
                meta.appendChild(a);
            }
        }
    }

    document.getElementById('pcSubmit').addEventListener('click', function () {
        if (busy) return;
        setBusy(true, 'Judging on all test cases...');
        post(CFG.submitUrl, { question_id: CFG.questionId, language: langSel.value, code: code.value })
            .then(function (r) {
                showResult(r, true);
                if (r.status === 200 && r.data) addSubmission(r.data.submission);
            })
            .catch(function () {
                resultBox.innerHTML = '<div class="pc-res pc-res--err">Network error. Please try again.</div>';
            })
            .finally(function () { setBusy(false); });
    });

    var customBtn = document.getElementById('pcRunCustom');
    if (customBtn) {
        customBtn.addEventListener('click', function () {
            if (busy) return;
            busy = true;
            customBtn.disabled = true;
            var out = document.getElementById('pcCustomOut');
            out.textContent = 'Running...';
            post(CFG.runUrl, {
                question_id: CFG.questionId, language: langSel.value, code: code.value,
                custom_input: document.getElementById('pcCustomInput').value
            }).then(function (r) {
                var d = r.data || {};
                out.textContent = d.error && !d.output
                    ? ('Error:\n' + d.error)
                    : ((d.output || '') + (d.error ? '\n[stderr]\n' + d.error : ''));
            }).catch(function () {
                out.textContent = 'Network error. Please try again.';
            }).finally(function () { busy = false; customBtn.disabled = false; });
        });
    }
}());

(function () {
    'use strict';
    var toggle = document.getElementById('pcViewToggle');
    document.body.classList.add('pc-view-question');
    if (!toggle) return;
    var btns = toggle.querySelectorAll('button');
    btns.forEach(function (b) {
        b.addEventListener('click', function () {
            var view = b.getAttribute('data-view');
            btns.forEach(function (x) { x.classList.toggle('is-active', x === b); });
            document.body.classList.toggle('pc-view-code', view === 'code');
            document.body.classList.toggle('pc-view-question', view === 'question');
        });
    });
}());
