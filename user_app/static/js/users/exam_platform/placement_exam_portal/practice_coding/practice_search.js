/* Live search for the practice list.
 *
 * Typing filters the list straight away instead of waiting for the Go button.
 * The request goes to the same API the infinite scroll uses, so the current
 * status, difficulty, sort and topic all stay applied, and the URL is kept in
 * step so a refresh or a shared link reproduces exactly what is on screen.
 *
 * The form still submits normally, so this is an enhancement rather than a
 * dependency: with JavaScript off, Go and Enter work as before. */
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var input = document.getElementById('pcSearch');
        var list = document.querySelector('.pc-list');
        if (!input || !list) return;

        var form = input.form;
        var clear = document.getElementById('pcSearchClear');
        var spin = document.getElementById('pcSearchSpin');
        var shown = document.getElementById('pcShown');
        var countLine = document.getElementById('pcCount');
        var timer = null;
        var seq = 0;
        var isAnon = false;

        function esc(text) {
            var d = document.createElement('div');
            d.textContent = text == null ? '' : String(text);
            return d.innerHTML;
        }

        function lockCell(q) {
            if (q.locked) {
                return q.lock_reason === 'login'
                    ? '<i class="fas fa-lock pc-lock--login" title="Log in to unlock"></i>'
                    : '<i class="fas fa-lock" title="Premium question"></i>';
            }
            if (q.is_paid) return '<i class="fas fa-crown pc-crown" title="Premium (unlocked)"></i>';
            if (isAnon) return '<span class="pc-preview-tag" title="Open in preview">Preview</span>';
            return '';
        }

        function rowHtml(q, i) {
            var diff = q.difficulty === 'Moderate' ? 'Med.' : q.difficulty;
            var status = q.solved
                ? '<i class="fas fa-circle-check pc-solved" title="Solved"></i>'
                : (q.attempted
                    ? '<i class="fas fa-circle-half-stroke pc-attempted" title="Attempted, not solved yet"></i>'
                    : '');
            var lock = lockCell(q);
            var companies = (q.companies && q.companies.length)
                ? '<span class="pc-cobadge" title="' + esc(q.companies.join(', ')) + '">' +
                  '<i class="fas fa-building"></i> ' + q.companies.length + '</span>' : '';
            return '<a class="pc-row' + (i % 2 ? ' pc-row--alt' : '') + '" href="' + esc(q.url) + '">' +
                '<span class="pc-row__status">' + status + '</span>' +
                '<span class="pc-row__title">' + (i + 1) + '. ' + esc(q.title) + '</span>' +
                '<span class="pc-row__subject">' + esc(q.subject) + '</span>' +
                '<span class="pc-row__acc">' +
                    (q.acceptance === null || q.acceptance === undefined ? '--' : q.acceptance) + '%</span>' +
                '<span class="pc-row__diff pc-diff--' + esc(String(q.difficulty).toLowerCase()) + '">' +
                    esc(diff) + '</span>' +
                '<span class="pc-row__companies">' + companies + '</span>' +
                '<span class="pc-row__lock">' + lock + '</span>' +
            '</a>';
        }

        function params() {
            // Start from the form so status, difficulty and sort travel with
            // the query, then keep the topic/tier the page was opened with.
            var p = new URLSearchParams(new FormData(form));
            var current = new URLSearchParams(window.location.search);
            ['subject', 'tier'].forEach(function (k) {
                if (current.get(k) && !p.get(k)) p.set(k, current.get(k));
            });
            for (var key of Array.from(p.keys())) {
                if (!p.get(key)) p.delete(key);          // drop empty selects
            }
            return p;
        }

        function run() {
            var mine = ++seq;
            var p = params();
            if (spin) spin.hidden = false;

            fetch('/practice-coding/api/questions?' + p.toString(), {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
                .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
                .then(function (data) {
                    if (mine !== seq) return;            // a newer keystroke won
                    isAnon = !!data.is_anon;
                    var rows = data.questions || [];
                    list.innerHTML = rows.length
                        ? rows.map(rowHtml).join('')
                        : '<div class="pc-empty">No questions match this search.</div>';
                    list.scrollTop = 0;
                    if (shown) shown.textContent = rows.length;
                    if (countLine) {
                        countLine.innerHTML = 'Showing <strong id="pcShown">' + rows.length +
                            '</strong> question' + (rows.length === 1 ? '' : 's');
                    }
                    // The URL follows what is on screen, so refresh and share work.
                    var qs = p.toString();
                    history.replaceState(null, '', qs ? '?' + qs : window.location.pathname);
                })
                .catch(function () {
                    if (mine === seq) form.submit();     // fall back to a full reload
                })
                .finally(function () {
                    if (mine === seq && spin) spin.hidden = true;
                });
        }

        input.addEventListener('input', function () {
            if (clear) clear.hidden = !input.value;
            clearTimeout(timer);
            timer = setTimeout(run, 300);               // wait for a pause in typing
        });

        // Enter should filter in place rather than reload the page.
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); clearTimeout(timer); run(); }
        });

        if (clear) {
            clear.addEventListener('click', function () {
                input.value = '';
                clear.hidden = true;
                clearTimeout(timer);
                run();
                input.focus();
            });
        }
    });
})();
