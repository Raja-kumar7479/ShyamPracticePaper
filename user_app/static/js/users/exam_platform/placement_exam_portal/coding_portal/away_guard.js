/* Leaving the coding exam window ends the attempt.
 *
 * Switching tab, minimising, or moving focus to another window starts a
 * visible countdown. Coming back before it reaches zero cancels it; letting it
 * run out terminates the attempt server-side and lands on the termination
 * page, so returning to the tab cannot resume the test.
 *
 * The server is the authority: it closes the attempt when /terminate is
 * called, and a candidate who kills the request still cannot continue because
 * the attempt row is already expired the next time a page is requested. */
(function () {
    'use strict';

    var CFG = window.CODING_AWAY_GUARD || {};
    if (!CFG.terminateUrl) return;

    var GRACE = Math.max(5, parseInt(CFG.graceSeconds, 10) || 20);
    var CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content ||
               (document.querySelector('input[name="csrf_token"]') || {}).value || '';

    var timerId = null;
    var tickId = null;
    var terminating = false;
    var overlay = null;
    var countEl = null;

    function buildOverlay() {
        if (overlay) return;
        overlay = document.createElement('div');
        overlay.className = 'cag-overlay';
        overlay.setAttribute('role', 'alertdialog');
        overlay.setAttribute('aria-live', 'assertive');
        overlay.innerHTML =
            '<div class="cag-card">' +
              '<div class="cag-icon">!</div>' +
              '<h2 class="cag-title">Return to your assessment</h2>' +
              '<p class="cag-sub">You have left the exam window. Your assessment will be ' +
              'terminated automatically if you do not come back.</p>' +
              '<div class="cag-count"><span id="cagCount">' + GRACE + '</span><small>seconds left</small></div>' +
              '<p class="cag-note">Click anywhere in this window to continue.</p>' +
            '</div>';
        document.body.appendChild(overlay);
        countEl = overlay.querySelector('#cagCount');
    }

    function showOverlay(remaining) {
        buildOverlay();
        if (countEl) countEl.textContent = remaining;
        overlay.classList.add('is-visible');
    }

    function hideOverlay() {
        if (overlay) overlay.classList.remove('is-visible');
    }

    function terminate(reason) {
        if (terminating) return;
        terminating = true;
        clearTimers();
        if (countEl) countEl.textContent = '0';

        fetch(CFG.terminateUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
            body: JSON.stringify({ reason: reason || 'left_exam_window' }),
            keepalive: true
        }).then(function (res) {
            return res.json().catch(function () { return {}; });
        }).then(function (data) {
            window.sppExamLeaving = true; window.location.replace(data.redirect || CFG.terminatedUrl);
        }).catch(function () {
            // Even if the call fails the attempt must not continue here.
            window.sppExamLeaving = true; window.location.replace(CFG.terminatedUrl);
        });
    }

    function clearTimers() {
        if (timerId) { clearTimeout(timerId); timerId = null; }
        if (tickId) { clearInterval(tickId); tickId = null; }
    }

    function startCountdown() {
        if (terminating || timerId) return;
        var remaining = GRACE;
        showOverlay(remaining);

        tickId = setInterval(function () {
            remaining -= 1;
            if (countEl) countEl.textContent = remaining > 0 ? remaining : 0;
        }, 1000);

        timerId = setTimeout(function () { terminate('away_' + GRACE + 's'); }, GRACE * 1000);
    }

    function cancelCountdown() {
        if (terminating) return;
        clearTimers();
        hideOverlay();
    }

    function isAway() {
        return document.visibilityState === 'hidden' || !document.hasFocus();
    }

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') startCountdown();
        else cancelCountdown();
    });

    window.addEventListener('blur', function () {
        // A blur can fire for in-page reasons (an iframe or the code editor
        // taking focus). Only treat it as leaving if focus really left.
        setTimeout(function () { if (isAway()) startCountdown(); }, 150);
    });

    window.addEventListener('focus', cancelCountdown);
    document.addEventListener('mousedown', function () { if (!isAway()) cancelCountdown(); });

    if (isAway()) startCountdown();
})();
