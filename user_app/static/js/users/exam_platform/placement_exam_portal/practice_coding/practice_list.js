/* Infinite scroll for the practice question list.
 *
 * The server sends the first page only. As the sentinel at the bottom of the
 * scrolling list comes into view the next page is fetched and appended, so a
 * bank of 10,000 questions costs the same to open as a bank of 100.
 *
 * Falls back to a plain "Load more" button when IntersectionObserver is
 * missing, and the button is always there for keyboard users. */
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var more = document.getElementById('pcMore');
        var list = document.querySelector('.pc-list');
        if (!more || !list) return;

        var btn = document.getElementById('pcMoreBtn');
        var shown = document.getElementById('pcShown');
        var total = parseInt(more.dataset.total, 10) || 0;
        var offset = parseInt(more.dataset.offset, 10) || 0;
        var loading = false;
        var done = false;
        var isAnon = false;

        // Whatever filter the page was opened with has to travel with each
        // page, or page 2 would come back unfiltered.
        var params = new URLSearchParams(window.location.search);

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

        function rowHtml(q, index) {
            var diff = q.difficulty === 'Moderate' ? 'Med.' : q.difficulty;
            var lock = lockCell(q);
            var companies = (q.companies && q.companies.length)
                ? '<span class="pc-cobadge" title="' + esc(q.companies.join(', ')) + '">' +
                  '<i class="fas fa-building"></i> ' + q.companies.length + '</span>'
                : '';
            var status = q.solved
                ? '<i class="fas fa-circle-check pc-solved" title="Solved"></i>'
                : (q.attempted
                    ? '<i class="fas fa-circle-half-stroke pc-attempted" title="Attempted, not solved yet"></i>'
                    : '');
            return '<a class="pc-row' + (index % 2 ? ' pc-row--alt' : '') + '" href="' + esc(q.url) + '">' +
                '<span class="pc-row__status">' + status + '</span>' +
                '<span class="pc-row__title">' + (index + 1) + '. ' + esc(q.title) + '</span>' +
                '<span class="pc-row__subject">' + esc(q.subject) + '</span>' +
                '<span class="pc-row__acc">' +
                    (q.acceptance === null || q.acceptance === undefined ? '--' : q.acceptance) + '%</span>' +
                '<span class="pc-row__diff pc-diff--' + esc(String(q.difficulty).toLowerCase()) + '">' +
                    esc(diff) + '</span>' +
                '<span class="pc-row__companies">' + companies + '</span>' +
                '<span class="pc-row__lock">' + lock + '</span>' +
            '</a>';
        }

        function finish() {
            done = true;
            more.remove();
        }

        function load() {
            if (loading || done) return;
            loading = true;
            more.classList.add('is-loading');

            params.set('offset', offset);
            fetch('/practice-coding/api/questions?' + params.toString(), {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
                .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
                .then(function (data) {
                    isAnon = !!data.is_anon;
                    var rows = data.questions || [];
                    if (!rows.length) { finish(); return; }

                    var html = rows.map(function (q, i) { return rowHtml(q, offset + i); }).join('');
                    more.insertAdjacentHTML('beforebegin', html);

                    offset = data.next_offset;
                    if (shown) shown.textContent = offset;
                    if (btn) btn.textContent = 'Load more (' + Math.max(0, total - offset) + ' left)';
                    if (!data.has_more || offset >= total) finish();
                })
                .catch(function () {
                    if (btn) btn.textContent = 'Could not load more. Tap to retry.';
                    more.classList.add('is-error');
                })
                .finally(function () {
                    loading = false;
                    more.classList.remove('is-loading');
                });
        }

        if (btn) btn.addEventListener('click', load);

        if ('IntersectionObserver' in window) {
            // The list is its own scroll container on desktop, so the observer
            // watches that box rather than the viewport.
            var scroller = list.scrollHeight > list.clientHeight ? list : null;
            var io = new IntersectionObserver(function (entries) {
                entries.forEach(function (e) { if (e.isIntersecting) load(); });
            }, { root: scroller, rootMargin: '400px' });
            io.observe(more);
        }
    });
})();
