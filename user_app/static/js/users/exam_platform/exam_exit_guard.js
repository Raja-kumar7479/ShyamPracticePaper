(function () {
    var cfg = document.getElementById('examExitGuard');
    if (!cfg) return;

    var releaseUrl = cfg.dataset.releaseUrl || '';
    var terminateUrl = cfg.dataset.terminateUrl || '';
    var terminatedUrl = cfg.dataset.terminatedUrl || '';
    var awaySeconds = parseInt(cfg.dataset.awaySeconds || '0', 10);
    var wantConfirm = cfg.dataset.confirm === '1';
    var confirmText = cfg.dataset.confirmText ||
        'Do you want to close the test? Your progress is saved and you can resume it later.';

    var internalNav = false;
    var finished = false;
    var terminated = false;

    function markInternal() { internalNav = true; }
    window.sppMarkInternalNav = markInternal;

    document.addEventListener('click', function (e) {
        var a = e.target.closest && e.target.closest('a[href]');
        if (!a) return;
        var href = a.getAttribute('href') || '';
        if (a.target === '_blank' || href.charAt(0) === '#' ||
            /^(mailto:|tel:|javascript:)/i.test(href)) return;
        markInternal();
    }, true);

    document.addEventListener('submit', markInternal, true);

    ['assign', 'replace'].forEach(function (fn) {
        var orig = window.location[fn];
        if (typeof orig !== 'function') return;
        try {
            window.location[fn] = function () {
                markInternal();
                return orig.apply(window.location, arguments);
            };
        } catch (err) {  }
    });

    try {
        var hrefDesc = Object.getOwnPropertyDescriptor(Location.prototype, 'href');
        if (hrefDesc && hrefDesc.set) {
            Object.defineProperty(window.location, 'href', {
                configurable: true,
                get: function () { return hrefDesc.get.call(window.location); },
                set: function (v) { markInternal(); return hrefDesc.set.call(window.location, v); }
            });
        }
    } catch (err) {  }

    var lastHref = window.location.href;
    setInterval(function () {
        if (window.location.href !== lastHref) { lastHref = window.location.href; markInternal(); }
    }, 250);

    window.sppMarkExamFinished = function () { finished = true; internalNav = true; };
    window.sppExamWillPrompt = function () {
        return wantConfirm && !(finished || terminated || internalNav || window.sppExamLeaving);
    };

    function sendRelease() {
        if (!releaseUrl) return;
        try {
            var blob = new Blob([JSON.stringify({ reason: 'window_closed' })], { type: 'text/plain' });
            if (!navigator.sendBeacon(releaseUrl, blob)) {
                fetch(releaseUrl, { method: 'POST', keepalive: true, body: '{}' }).catch(function () {});
            }
        } catch (e) {
            try { fetch(releaseUrl, { method: 'POST', keepalive: true, body: '{}' }).catch(function () {}); } catch (err) {}
        }
    }

    if (wantConfirm) {
        window.addEventListener('beforeunload', function (e) {
            if (finished || terminated || internalNav || window.sppExamLeaving) return;
            e.preventDefault();
            e.returnValue = confirmText;
            return confirmText;
        });
    }

    function bringOpenerBack() {
        try {
            if (window.opener && !window.opener.closed) window.opener.focus();
        } catch (err) {}
    }

    window.addEventListener('pagehide', function (e) {
        if (e.persisted) return;
        if (finished || terminated) { bringOpenerBack(); return; }
        if (internalNav) { internalNav = false; return; }
        sendRelease();
        bringOpenerBack();
    });

    window.sppCloseExam = function (exitUrl) {
        if (!window.confirm(confirmText)) return false;
        sendRelease();
        finished = true;
        setTimeout(function () {
            if (exitUrl) { window.location.replace(exitUrl); return; }
            window.close();
            setTimeout(function () { window.location.replace(exitUrl || '/'); }, 300);
        }, 120);
        return true;
    };

    if (!awaySeconds || !terminateUrl) return;

    var overlay, countdownEl, timerId, ticks;

    function buildOverlay() {
        overlay = document.createElement('div');
        overlay.className = 'spp-away';
        overlay.innerHTML =
            '<div class="spp-away__box">' +
            '<i class="fas fa-triangle-exclamation"></i>' +
            '<h3>Return to the test window</h3>' +
            '<p>You left the exam window. This is recorded as a proctoring violation.</p>' +
            '<p class="spp-away__count">Auto-terminating in <strong id="sppAwayCount">' + awaySeconds + '</strong>s</p>' +
            '</div>';
        document.body.appendChild(overlay);
        countdownEl = document.getElementById('sppAwayCount');
    }

    function terminate() {
        if (terminated) return;
        terminated = true;
        finished = true;
        fetch(terminateUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify({ reason: 'left_exam_window' })
        })
            .then(function (r) { return r.json().catch(function () { return {}; }); })
            .then(function (d) { window.location.replace((d && d.redirect) || terminatedUrl || '/'); })
            .catch(function () { window.location.replace(terminatedUrl || '/'); });
    }

    function startAway() {
        if (terminated || finished || timerId) return;
        ticks = awaySeconds;
        if (!overlay) buildOverlay();
        overlay.classList.add('is-on');
        if (countdownEl) countdownEl.textContent = ticks;
        timerId = setInterval(function () {
            ticks--;
            if (countdownEl) countdownEl.textContent = ticks;
            if (ticks <= 0) { stopAway(); terminate(); }
        }, 1000);
    }

    function stopAway() {
        if (timerId) { clearInterval(timerId); timerId = null; }
        if (overlay) overlay.classList.remove('is-on');
    }

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) startAway(); else stopAway();
    });
    window.addEventListener('blur', function () {
        if (document.hidden) startAway();
    });
    window.addEventListener('focus', stopAway);
})();
