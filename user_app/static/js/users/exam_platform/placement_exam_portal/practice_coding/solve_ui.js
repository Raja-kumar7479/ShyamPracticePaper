/* Solve page chrome: left tabs, editorial language switcher, submission code
 * viewer, bookmark, reset, expand and the stopwatch.
 *
 * Kept separate from solve.js, which owns the editor and the run/submit calls,
 * so the two concerns can be changed independently. */
(function () {
    'use strict';

    var $ = function (id) { return document.getElementById(id); };
    var CFG = window.PCP || {};
    var CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

    document.addEventListener('DOMContentLoaded', function () {

        /* ---------- left tabs: Description | Editorial | Submissions ---------- */
        var tabs = document.querySelectorAll('.pc-ltab');
        var panels = document.querySelectorAll('.pc-lpanel');
        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                var want = tab.getAttribute('data-ltab');
                tabs.forEach(function (t) {
                    var on = t === tab;
                    t.classList.toggle('is-active', on);
                    t.setAttribute('aria-selected', on ? 'true' : 'false');
                });
                panels.forEach(function (p) {
                    p.classList.toggle('is-hidden', p.getAttribute('data-lpanel') !== want);
                });
                // A tab switch should start at the top, not halfway down the
                // previous tab's scroll position.
                var pane = $('pcLeftPane');
                if (pane) pane.scrollTop = 0;
            });
        });

        /* ---------- editorial: language tabs + copy ---------- */
        document.querySelectorAll('.pc-ed').forEach(function (article) {
            var langs = article.querySelectorAll('[data-edlang]');
            var blocks = article.querySelectorAll('[data-edcode]');

            langs.forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var want = btn.getAttribute('data-edlang');
                    langs.forEach(function (b) { b.classList.toggle('is-active', b === btn); });
                    blocks.forEach(function (pre) {
                        pre.classList.toggle('is-hidden', pre.getAttribute('data-edcode') !== want);
                    });
                });
            });

            var copy = article.querySelector('[data-edcopy]');
            if (copy) {
                copy.addEventListener('click', function () {
                    var visible = article.querySelector('[data-edcode]:not(.is-hidden) code');
                    if (visible) copyText(visible.textContent, copy);
                });
            }
        });

        /* ---------- submissions: reveal the code of a row ---------- */
        document.querySelectorAll('.pc-subrow').forEach(function (row) {
            row.addEventListener('click', function () {
                var id = row.getAttribute('data-subid');
                var code = document.querySelector('[data-subcode="' + id + '"]');
                if (!code) return;
                var open = !code.classList.contains('is-hidden');
                code.classList.toggle('is-hidden', open);
                row.classList.toggle('is-open', !open);
            });
        });

        /* ---------- bookmark ---------- */
        var bookmarks = document.querySelectorAll('.js-bookmark');
        bookmarks.forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (!CFG.bookmarkUrl) return;
                btn.disabled = true;
                fetch(CFG.bookmarkUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF }
                })
                    .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
                    .then(function (data) { paintBookmark(!!data.bookmarked); })
                    .catch(function () { toast('Could not save the bookmark. Try again.'); })
                    .finally(function () { btn.disabled = false; });
            });
        });

        function paintBookmark(on) {
            bookmarks.forEach(function (b) {
                b.classList.toggle('is-on', on);
                b.setAttribute('aria-pressed', on ? 'true' : 'false');
                b.title = on ? 'Remove bookmark' : 'Bookmark this problem';
                var icon = b.querySelector('i');
                if (icon) icon.className = (on ? 'fas' : 'far') + ' fa-bookmark';
            });
            toast(on ? 'Bookmarked' : 'Bookmark removed');
        }

        /* ---------- reset to the starter code ---------- */
        var reset = $('pcReset');
        if (reset) {
            reset.addEventListener('click', function () {
                var lang = $('pcLang') ? $('pcLang').value : null;
                var starter = (CFG.templates || {})[lang];
                if (starter === undefined || starter === null) starter = '';
                if (!confirm('Reset the editor to the starter code? Your current code will be lost.')) return;
                var box = $('pcCode');
                if (!box) return;
                box.value = starter;
                box.dispatchEvent(new Event('input', { bubbles: true }));
                box.focus();
                toast('Editor reset');
            });
        }

        /* ---------- expand the editor ---------- */
        var expand = $('pcExpand');
        if (expand) {
            expand.addEventListener('click', function () { setExpanded(!document.body.classList.contains('pc-expanded')); });
        }
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && document.body.classList.contains('pc-expanded')) setExpanded(false);
        });

        function setExpanded(on) {
            document.body.classList.toggle('pc-expanded', on);
            var icon = expand ? expand.querySelector('i') : null;
            // Same glyph both ways; the is-on class carries the state colour.
            if (icon) icon.className = 'fas fa-table-columns';
            if (expand) {
                expand.title = on ? 'Show the problem again (Esc)'
                                  : 'Hide the problem and widen the editor (Esc to exit)';
                expand.classList.toggle('is-on', on);
            }
        }

        /* ---------- full window (browser fullscreen) ---------- */
        (function () {
            var btn = $('pcFullscreen');
            if (!btn) return;

            var root = document.documentElement;
            var supported = !!(root.requestFullscreen || root.webkitRequestFullscreen);
            if (!supported) { btn.style.display = 'none'; return; }

            function isFull() {
                return !!(document.fullscreenElement || document.webkitFullscreenElement);
            }

            function paint() {
                var on = isFull();
                var icon = btn.querySelector('i');
                if (icon) icon.className = on ? 'fas fa-compress' : 'fas fa-expand';
                btn.title = on ? 'Leave full window (Esc)' : 'Full window';
                btn.setAttribute('aria-pressed', on ? 'true' : 'false');
                btn.classList.toggle('is-on', on);
            }

            btn.addEventListener('click', function () {
                if (isFull()) {
                    (document.exitFullscreen || document.webkitExitFullscreen).call(document);
                    return;
                }
                var req = root.requestFullscreen || root.webkitRequestFullscreen;
                var out = req.call(root);
                // Chrome rejects when the gesture is not trusted; say so rather
                // than leaving the button looking broken.
                if (out && typeof out.catch === 'function') {
                    out.catch(function () { toast('Your browser blocked full window mode.'); });
                }
            });

            // The user can also leave with Esc or F11, so follow the event
            // rather than assuming the click is the only way out.
            document.addEventListener('fullscreenchange', paint);
            document.addEventListener('webkitfullscreenchange', paint);
            paint();
        })();

        /* ---------- resize the console: drag the grip or nudge the arrows ---------- */
        (function () {
            var io = $('pcIo');
            var grip = $('pcIoGrip');
            var pane = $('pcEditorPane');
            if (!io || !grip || !pane) return;

            var STORE = 'pcpIoHeight';
            var MIN = 88;                 // the tabs plus a line of output
            var DEFAULT = 240;
            var STEP = 60;

            function maxHeight() {
                // Never more than three quarters of the pane, so the editor
                // always keeps a usable strip.
                return Math.max(MIN, Math.round(pane.clientHeight * 0.75));
            }

            function current() { return io.getBoundingClientRect().height; }

            function apply(px, save) {
                var h = Math.min(maxHeight(), Math.max(MIN, Math.round(px)));
                io.style.setProperty('--pc-io-h', h + 'px');
                if (io.classList.contains('is-collapsed')) {
                    io.classList.remove('is-collapsed');
                    var ci = $('pcIoCollapse');
                    if (ci) {
                        var icon = ci.querySelector('i');
                        if (icon) icon.className = 'fas fa-chevron-down';
                        ci.title = 'Collapse the console';
                    }
                }
                var up = $('pcIoUp'), down = $('pcIoDown');
                if (up) up.disabled = h >= maxHeight();
                if (down) down.disabled = h <= MIN;
                if (save !== false) {
                    try { localStorage.setItem(STORE, String(h)); } catch (e) {}
                }
                return h;
            }

            var stored = null;
            try { stored = parseInt(localStorage.getItem(STORE), 10); } catch (e) {}
            apply(stored && !isNaN(stored) ? stored : DEFAULT, false);

            var startY = 0, startH = 0, dragging = false;

            grip.addEventListener('pointerdown', function (e) {
                if (e.target.closest('.pc-io__nudge')) return;   // arrows handle themselves
                dragging = true;
                startY = e.clientY;
                startH = current();
                grip.setPointerCapture(e.pointerId);
                grip.classList.add('is-dragging');
                document.body.classList.add('pc-io-resizing');
                e.preventDefault();
            });

            grip.addEventListener('pointermove', function (e) {
                if (!dragging) return;
                // Dragging up grows the console, the direction people expect.
                apply(startH + (startY - e.clientY));
            });

            function endDrag(e) {
                if (!dragging) return;
                dragging = false;
                grip.classList.remove('is-dragging');
                document.body.classList.remove('pc-io-resizing');
                if (e && e.pointerId !== undefined && grip.hasPointerCapture(e.pointerId)) {
                    grip.releasePointerCapture(e.pointerId);
                }
            }
            grip.addEventListener('pointerup', endDrag);
            grip.addEventListener('pointercancel', endDrag);

            grip.addEventListener('dblclick', function () { apply(DEFAULT); });

            var upBtn = $('pcIoUp'), downBtn = $('pcIoDown');
            if (upBtn) upBtn.addEventListener('click', function () { apply(current() + STEP); });
            if (downBtn) downBtn.addEventListener('click', function () { apply(current() - STEP); });

            grip.addEventListener('keydown', function (e) {
                if (e.key === 'ArrowUp') { e.preventDefault(); apply(current() + STEP); }
                else if (e.key === 'ArrowDown') { e.preventDefault(); apply(current() - STEP); }
                else if (e.key === 'Home') { e.preventDefault(); apply(DEFAULT); }
            });

            // A shorter window can leave the console taller than the new cap.
            window.addEventListener('resize', function () { apply(current(), false); });
        })();

        /* ---------- collapse the console ---------- */
        var collapse = $('pcIoCollapse');
        if (collapse) {
            collapse.addEventListener('click', function () {
                var io = $('pcIo');
                if (!io) return;
                var on = io.classList.toggle('is-collapsed');
                var icon = collapse.querySelector('i');
                if (icon) icon.className = on ? 'fas fa-chevron-up' : 'fas fa-chevron-down';
                collapse.title = on ? 'Show the console' : 'Collapse the console';
            });
        }

        /* ---------- stopwatch ---------- */
        var timerBtn = $('pcTimerBtn');
        var timerOut = $('pcTimer');
        if (timerBtn && timerOut) {
            var seconds = 0, handle = null;
            var tick = function () {
                seconds += 1;
                var m = String(Math.floor(seconds / 60)).padStart(2, '0');
                var s = String(seconds % 60).padStart(2, '0');
                timerOut.textContent = m + ':' + s;
            };
            handle = setInterval(tick, 1000);
            timerBtn.addEventListener('click', function () {
                if (handle) {
                    clearInterval(handle);
                    handle = null;
                    timerBtn.classList.add('is-paused');
                    timerBtn.title = 'Stopwatch paused - click to resume';
                } else {
                    handle = setInterval(tick, 1000);
                    timerBtn.classList.remove('is-paused');
                    timerBtn.title = 'Stopwatch running - click to pause';
                }
            });
            window.addEventListener('beforeunload', function () { if (handle) clearInterval(handle); });
        }

        /* ---------- helpers ---------- */
        function copyText(text, btn) {
            var done = function () {
                var original = btn.innerHTML;
                btn.innerHTML = '<i class="fas fa-check"></i> Copied';
                setTimeout(function () { btn.innerHTML = original; }, 1500);
            };
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(done).catch(fallback);
            } else { fallback(); }

            function fallback() {
                var ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.select();
                try { document.execCommand('copy'); done(); } catch (err) {}
                document.body.removeChild(ta);
            }
        }

        function toast(message) {
            var box = document.createElement('div');
            box.className = 'pc-toast';
            box.textContent = message;
            document.body.appendChild(box);
            setTimeout(function () { box.classList.add('is-out'); }, 1600);
            setTimeout(function () { box.remove(); }, 2100);
        }
    });
})();
