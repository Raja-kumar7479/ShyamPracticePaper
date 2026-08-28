(function () {
    'use strict';

    var cfg = document.getElementById('examFullscreenGuard');
    if (!cfg) return;

    var GRACE = Math.max(5, parseInt(cfg.dataset.graceSeconds, 10) || 20);
    var TERMINATE_URL = cfg.dataset.terminateUrl || '';
    var TERMINATED_URL = cfg.dataset.terminatedUrl || '';
    var REQUIRE_FS = cfg.dataset.requireFullscreen !== '0';

    if (!TERMINATE_URL) return;

    var CSRF =
        (document.querySelector('meta[name="csrf-token"]') || {}).content ||
        (document.getElementById('csrfToken') || {}).value ||
        (document.querySelector('input[name="csrf_token"]') || {}).value || '';

    var finished = false;
    var terminated = false;
    var unloading = false;
    var enteredOnce = false;      // has the candidate been in full screen at all yet
    var timerId = null;
    var tickId = null;
    var trigger = null;

    var popup = null;
    var cardEl = null;
    var titleEl = null;
    var subEl = null;
    var countWrapEl = null;
    var countEl = null;
    var actionEl = null;

    function fsElement() {
        return document.fullscreenElement ||
               document.webkitFullscreenElement ||
               document.msFullscreenElement || null;
    }

    function fsSupported() {
        var el = document.documentElement;
        return !!(el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen);
    }

    function requestFs() {
        var el = document.documentElement;
        var fn = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
        if (!fn) return Promise.resolve();
        try {
            var r = fn.call(el);
            return (r && typeof r.then === 'function') ? r : Promise.resolve();
        } catch (e) {
            return Promise.reject(e);
        }
    }

    function buildPopup() {
        popup = document.createElement('div');
        popup.className = 'efg-popup';
        popup.setAttribute('role', 'alertdialog');
        popup.setAttribute('aria-live', 'assertive');
        popup.innerHTML =
            '<div class="efg-card" id="efgCard">' +
              '<h2 class="efg-title" id="efgTitle"></h2>' +
              '<p class="efg-sub" id="efgSub"></p>' +
              '<p class="efg-count" id="efgCountWrap">Auto-ending in <strong id="efgCount">' + GRACE + '</strong>s</p>' +
              '<button type="button" class="efg-btn" id="efgAction"></button>' +
            '</div>';
        document.body.appendChild(popup);
        cardEl = popup.querySelector('#efgCard');
        titleEl = popup.querySelector('#efgTitle');
        subEl = popup.querySelector('#efgSub');
        countWrapEl = popup.querySelector('#efgCountWrap');
        countEl = popup.querySelector('#efgCount');
        actionEl = popup.querySelector('#efgAction');
        actionEl.addEventListener('click', onActionClick);
    }

    function onActionClick() {
        if (trigger === 'away') {
            try { window.focus(); } catch (e) {}
            evaluate();
        } else {
            // entry or fullscreen violation - re-enter full screen, then
            // re-check so the popup and countdown clear the moment we are back.
            requestFs().then(evaluate).catch(function () {});
        }
    }

    // mode: 'entry' (no countdown), 'fullscreen' or 'away' (countdown)
    function showPopup(mode) {
        if (!popup) buildPopup();
        trigger = mode;
        if (mode === 'entry') {
            titleEl.textContent = 'Enter full screen to begin';
            subEl.textContent = 'This assessment runs in full screen.';
            actionEl.textContent = 'Enter full screen';
            if (countWrapEl) countWrapEl.style.display = 'none';
        } else if (mode === 'away') {
            titleEl.textContent = 'Return to the test window';
            subEl.textContent = 'You left the exam window.';
            actionEl.textContent = 'Resume';
            if (countWrapEl) countWrapEl.style.display = '';
        } else {
            titleEl.textContent = 'Return to full screen';
            subEl.textContent = 'You left full screen.';
            actionEl.textContent = 'Return to full screen';
            if (countWrapEl) countWrapEl.style.display = '';
        }
        popup.classList.add('is-on');
    }

    function hidePopup() {
        if (popup) popup.classList.remove('is-on');
    }

    function startCountdown(mode) {
        if (terminated || finished) return;
        if (timerId && trigger === mode) return;
        clearTimers();
        var remaining = GRACE;
        showPopup(mode);
        if (countEl) countEl.textContent = remaining;
        tickId = setInterval(function () {
            remaining -= 1;
            if (countEl) countEl.textContent = remaining > 0 ? remaining : 0;
        }, 1000);
        timerId = setTimeout(function () { terminate(mode); }, GRACE * 1000);
    }

    function cancelCountdown() {
        clearTimers();
        hidePopup();
        trigger = null;
    }

    function clearTimers() {
        if (timerId) { clearTimeout(timerId); timerId = null; }
        if (tickId) { clearInterval(tickId); tickId = null; }
    }

    function leaveTo(url) {
        // Signal the exam's own leave-guard that this navigation is intentional
        // so it does NOT raise a "Leave site?" prompt the candidate could cancel.
        window.sppExamLeaving = true;
        window.location.replace(url || '/');
    }

    function terminate(reason) {
        if (terminated) return;
        terminated = true;
        finished = true;
        window.sppExamLeaving = true;
        clearTimers();
        if (countEl) countEl.textContent = '0';
        fetch(TERMINATE_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ reason: (reason === 'away') ? 'left_exam_window' : 'left_full_screen' }),
            keepalive: true
        }).then(function (res) {
            return res.json().catch(function () { return {}; });
        }).then(function (data) {
            leaveTo((data && data.redirect) || TERMINATED_URL);
        }).catch(function () {
            leaveTo(TERMINATED_URL);
        });
    }

    function isAway() {
        return document.visibilityState === 'hidden' || !document.hasFocus();
    }

    function isFullscreenViolation() {
        return REQUIRE_FS && fsSupported() && !fsElement();
    }

    function evaluate() {
        if (terminated || finished || unloading) return;
        if (fsElement()) {
            // in full screen - the exam is running
            enteredOnce = true;
            if (trigger !== 'away' || !isAway()) cancelCountdown();
        }
        if (isFullscreenViolation()) {
            if (enteredOnce) startCountdown('fullscreen');
            return;
        }
        if (isAway()) { startCountdown('away'); return; }
        cancelCountdown();
    }

    document.addEventListener('fullscreenchange', evaluate);
    document.addEventListener('webkitfullscreenchange', evaluate);
    document.addEventListener('msfullscreenchange', evaluate);

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') {
            if (enteredOnce) startCountdown('away');
        } else {
            evaluate();
        }
    });

    window.addEventListener('blur', function () {
        // A blur can fire briefly while the page swaps content during an in-app
        // navigation; re-check after a moment so that never trips the guard.
        setTimeout(function () { if (enteredOnce && isAway()) startCountdown('away'); }, 250);
    });

    window.addEventListener('focus', evaluate);

    window.addEventListener('beforeunload', function () { unloading = true; });

    var sppPrevMarkFinished = window.sppMarkExamFinished;
    window.sppMarkExamFinished = function () {
        finished = true;
        cancelCountdown();
        if (typeof sppPrevMarkFinished === 'function') sppPrevMarkFinished();
    };

    function armFirstGestureFs() {
        function onFirst() {
            document.removeEventListener('pointerdown', onFirst, true);
            document.removeEventListener('keydown', onFirst, true);
            document.removeEventListener('touchstart', onFirst, true);
            requestFs().then(evaluate).catch(function () {});
        }
        document.addEventListener('pointerdown', onFirst, true);
        document.addEventListener('keydown', onFirst, true);
        document.addEventListener('touchstart', onFirst, true);
    }

    // No entry popup: the test window opens straight into full screen. A
    // top-level navigation drops the full screen the Start button entered, so
    // we re-request it immediately (works when the browser still holds the
    // Start click's activation) and, failing that, silently on the candidate's
    // very first interaction. The countdown popup appears only on a later
    // violation - leaving full screen or the window - never to begin.
    if (REQUIRE_FS && fsSupported() && !fsElement()) {
        requestFs().then(function () { enteredOnce = true; evaluate(); }).catch(function () {});
        armFirstGestureFs();
    } else if (fsElement()) {
        enteredOnce = true;
    }
})();
