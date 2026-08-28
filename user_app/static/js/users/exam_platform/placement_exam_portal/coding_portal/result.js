/* Coding result page: code viewer, copy button, question filters.
 *
 * Everything here is progressive - the page is complete and readable with
 * JavaScript disabled, this only adds the collapsing and filtering. */
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {

        // ---- submitted code: expand / collapse ----
        document.querySelectorAll('.cr-code__toggle').forEach(function (btn) {
            var body = btn.parentElement.querySelector('.cr-code__body');
            if (!body) return;
            var label = btn.querySelector('span');

            btn.addEventListener('click', function () {
                var open = btn.getAttribute('aria-expanded') === 'true';
                btn.setAttribute('aria-expanded', open ? 'false' : 'true');
                body.hidden = open;
                if (label) label.textContent = open ? 'View my submitted code' : 'Hide my submitted code';
            });
        });

        // ---- copy code ----
        document.querySelectorAll('[data-copy]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var pre = btn.parentElement.querySelector('code');
                if (!pre) return;
                var text = pre.textContent || '';
                var done = function () {
                    var original = btn.innerHTML;
                    btn.innerHTML = '<i class="fas fa-check"></i> Copied';
                    btn.classList.add('is-done');
                    setTimeout(function () {
                        btn.innerHTML = original;
                        btn.classList.remove('is-done');
                    }, 1600);
                };

                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(text).then(done).catch(fallback);
                } else {
                    fallback();
                }

                function fallback() {
                    var ta = document.createElement('textarea');
                    ta.value = text;
                    ta.setAttribute('readonly', '');
                    ta.style.position = 'fixed';
                    ta.style.opacity = '0';
                    document.body.appendChild(ta);
                    ta.select();
                    try { document.execCommand('copy'); done(); } catch (e) {}
                    document.body.removeChild(ta);
                }
            });
        });

        // ---- filter questions by outcome ----
        var buttons = document.querySelectorAll('[data-qfilter]');
        var cards = document.querySelectorAll('.cr-q[data-qstate]');
        var empty = document.getElementById('crFilterEmpty');

        buttons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                var want = btn.getAttribute('data-qfilter');
                buttons.forEach(function (b) { b.classList.toggle('is-active', b === btn); });

                var shown = 0;
                cards.forEach(function (card) {
                    var match = want === 'all' || card.getAttribute('data-qstate') === want;
                    card.style.display = match ? '' : 'none';
                    if (match) shown++;
                });
                if (empty) empty.hidden = shown !== 0;
            });
        });
    });
})();

(function () {
    var btn = document.getElementById('crCopyLink');
    if (!btn) return;
    btn.addEventListener('click', function () {
        var link = btn.dataset.link || '';
        function done() {
            btn.classList.add('is-done');
            btn.innerHTML = '<i class="fas fa-check"></i> Copied';
            setTimeout(function () {
                btn.classList.remove('is-done');
                btn.innerHTML = '<i class="fas fa-link"></i> Copy Link';
            }, 2000);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(link).then(done).catch(function () {});
        } else {
            var t = document.createElement('textarea');
            t.value = link; document.body.appendChild(t); t.select();
            try { document.execCommand('copy'); done(); } catch (e) {}
            document.body.removeChild(t);
        }
    });
})();
