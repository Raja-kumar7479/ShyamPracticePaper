(function () {
    'use strict';
    if (window.sppExamSecureLoaded) return;
    window.sppExamSecureLoaded = true;

    var EMBEDDED = window.parent !== window;
    var coverTimer = null;
    var lastReport = {};
    var leaveHold = false;
    var watchArmAt = Date.now() + 2500;

    function cfg() {
        var el = document.getElementById('examSecure');
        return el ? el.dataset : null;
    }

    function injectStyle() {
        if (document.getElementById('sppSecureStyle')) return;
        var style = document.createElement('style');
        style.id = 'sppSecureStyle';
        style.textContent =
            '@media print { html, body { display: none !important; } }' +
            '.spp-secure-cover { position: fixed; inset: 0; z-index: 99990; display: none; background: rgba(27, 15, 13, .9);' +
            ' backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px); }' +
            '.spp-secure-cover.is-on { display: block; }' +
            '.spp-secure-watch { position: fixed; inset: 0; z-index: 99985; display: block; pointer-events: none; opacity: 0; will-change: opacity;' +
            ' background: rgba(27, 15, 13, .9); backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px);' +
            ' animation: sppSecureWatch 1000ms linear forwards; }' +
            '@keyframes sppSecureWatch { 0%, 60% { opacity: 0; } 100% { opacity: 1; } }' +
            '.spp-secure-mark { position: fixed; inset: 0; z-index: 99980; pointer-events: none; opacity: .07; background-repeat: repeat; }' +
            '.spp-secure-toasts { position: fixed; top: 16px; left: 16px; z-index: 100001; display: flex; flex-direction: column; gap: 8px; max-width: min(340px, calc(100vw - 32px)); }' +
            '.spp-secure-toast { background: #7a231d; color: #fff; padding: 10px 14px; border-radius: 8px; font: 600 13px/1.4 "Segoe UI", system-ui, sans-serif; box-shadow: 0 8px 22px rgba(0,0,0,.25); }' +
            'body.spp-secure-noselect { -webkit-user-select: none; user-select: none; }' +
            'body.spp-secure-noselect input, body.spp-secure-noselect textarea, body.spp-secure-noselect [contenteditable="true"], body.spp-secure-noselect .ql-editor { -webkit-user-select: text; user-select: text; }';
        document.head.appendChild(style);
    }

    function toast(message) {
        if (!document.body) return;
        var stack = document.querySelector('.spp-secure-toasts');
        if (!stack) {
            stack = document.createElement('div');
            stack.className = 'spp-secure-toasts';
            document.body.appendChild(stack);
        }
        if (stack.lastChild && stack.lastChild.textContent === message) return;
        var node = document.createElement('div');
        node.className = 'spp-secure-toast';
        node.setAttribute('role', 'alert');
        node.textContent = message;
        stack.appendChild(node);
        setTimeout(function () { node.remove(); }, 3000);
    }

    function cover(holdMs) {
        if (EMBEDDED || !document.body) return;
        var el = document.getElementById('sppSecureCover');
        if (!el) {
            el = document.createElement('div');
            el.id = 'sppSecureCover';
            el.className = 'spp-secure-cover';
            el.setAttribute('aria-hidden', 'true');
            document.body.appendChild(el);
        }
        el.classList.add('is-on');
        if (coverTimer) { clearTimeout(coverTimer); coverTimer = null; }
        if (holdMs) coverTimer = setTimeout(uncover, holdMs);
    }

    function uncover() {
        if (coverTimer) { clearTimeout(coverTimer); coverTimer = null; }
        var el = document.getElementById('sppSecureCover');
        if (el) el.classList.remove('is-on');
    }

    function report(type, details) {
        var now = Date.now();
        if (lastReport[type] && now - lastReport[type] < 1500) return;
        lastReport[type] = now;
        if (EMBEDDED) {
            try {
                window.parent.postMessage({ type: 'tcs-coding-violation', violationType: type, details: details },
                                          window.location.origin);
            } catch (e) {}
            return;
        }
        var c = cfg();
        if (!c || !c.reportUrl) return;
        fetch(c.reportUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ violationType: type, details: details })
        }).then(function (r) {
            if (r.status === 403 && c.terminatedUrl) {
                window.sppExamLeaving = true;
                if (typeof window.sppMarkExamFinished === 'function') window.sppMarkExamFinished();
                window.location.replace(c.terminatedUrl.replace('__TYPE__', encodeURIComponent(type)));
            }
        }).catch(function () {});
    }

    function blocksClipboard() {
        var c = cfg();
        return !!c && c.blockClipboard === '1';
    }

    ['copy', 'cut', 'paste'].forEach(function (name) {
        window.addEventListener(name, function (e) {
            if (!blocksClipboard()) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            toast('Copy, cut and paste are disabled during the test.');
            report('clipboard_' + name, 'Attempted to ' + name + ' content during the test.');
        }, true);
    });

    ['drop', 'dragstart'].forEach(function (name) {
        window.addEventListener(name, function (e) {
            if (!blocksClipboard()) return;
            e.preventDefault();
            e.stopImmediatePropagation();
        }, true);
    });

    window.addEventListener('contextmenu', function (e) {
        if (!cfg()) return;
        e.preventDefault();
    }, true);

    function screenshotAttempt(how) {
        cover(6000);
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText('Screenshots are not allowed during the test.').catch(function () {});
            }
        } catch (e) {}
        toast('Screenshots are not allowed. This attempt is recorded.');
        report('screenshot_attempt', 'Screenshot shortcut pressed (' + how + ').');
    }

    window.addEventListener('keyup', function (e) {
        if (!cfg()) return;
        if (e.key === 'PrintScreen' || e.code === 'PrintScreen') screenshotAttempt('PrintScreen');
    }, true);

    window.addEventListener('keydown', function (e) {
        if (!cfg()) return;
        var key = (e.key || '').toLowerCase();
        var mod = e.ctrlKey || e.metaKey;
        if (e.key === 'PrintScreen' || e.code === 'PrintScreen') {
            e.preventDefault();
            screenshotAttempt('PrintScreen');
            return;
        }
        if (e.metaKey && e.shiftKey && /^[3456s]$/.test(key)) {
            e.preventDefault();
            screenshotAttempt('system capture shortcut');
            return;
        }
        if (mod && (key === 'p' || key === 's' || key === 'u')) {
            e.preventDefault();
            e.stopImmediatePropagation();
            toast(key === 'p' ? 'Printing is disabled during the test.' : 'This shortcut is disabled during the test.');
            return;
        }
        if (e.key === 'F12' || (mod && e.shiftKey && (key === 'i' || key === 'j' || key === 'c'))) {
            e.preventDefault();
            e.stopImmediatePropagation();
            return;
        }
        if (blocksClipboard() && ((mod && (key === 'c' || key === 'x' || key === 'v')) ||
                                  (e.shiftKey && key === 'insert') || (e.ctrlKey && key === 'insert'))) {
            e.preventDefault();
            e.stopImmediatePropagation();
            toast('Copy, cut and paste are disabled during the test.');
            report('clipboard_' + (key === 'c' ? 'copy' : key === 'x' ? 'cut' : 'paste'),
                   'Clipboard shortcut pressed during the test.');
        }
    }, true);

    function privacyCheck() {
        if (EMBEDDED || !cfg()) return;
        if (document.visibilityState === 'hidden' || !document.hasFocus()) {
            cover(0);
        } else if (!coverTimer && !leaveHold) {
            uncover();
        }
    }

    function watchdog() {
        if (EMBEDDED || !cfg() || !document.body || Date.now() < watchArmAt) return;
        if (document.getElementById('sppSecureWatch')) return;
        if (typeof Element.prototype.getAnimations !== 'function') return;
        var el = document.createElement('div');
        el.id = 'sppSecureWatch';
        el.className = 'spp-secure-watch';
        el.setAttribute('aria-hidden', 'true');
        document.body.appendChild(el);
    }

    function feedWatchdog() {
        var el = document.getElementById('sppSecureWatch');
        if (!el || typeof el.getAnimations !== 'function') return;
        var list = el.getAnimations();
        for (var i = 0; i < list.length; i++) {
            try { list[i].currentTime = 0; } catch (e) {}
        }
    }

    setInterval(feedWatchdog, 200);
    window.addEventListener('focus', feedWatchdog);
    document.addEventListener('visibilitychange', feedWatchdog);

    window.addEventListener('beforeunload', function () {
        if (EMBEDDED || !cfg()) return;
        if (typeof window.sppExamWillPrompt !== 'function' || !window.sppExamWillPrompt()) return;
        leaveHold = true;
        cover(0);
        setTimeout(function () {
            feedWatchdog();
            setTimeout(function () {
                leaveHold = false;
                privacyCheck();
            }, 1500);
        }, 50);
    });

    window.addEventListener('blur', function () { setTimeout(privacyCheck, 120); });
    window.addEventListener('focus', function () { setTimeout(privacyCheck, 60); });
    document.addEventListener('visibilitychange', privacyCheck);

    function watermark() {
        if (EMBEDDED) return;
        var c = cfg();
        if (!c || !c.watermark || document.getElementById('sppSecureMark')) return;
        var text = String(c.watermark).replace(/[<>&"']/g, '');
        var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="360" height="200">' +
                  '<text x="20" y="110" font-family="Arial, sans-serif" font-size="15" fill="#000" transform="rotate(-24 180 100)">' +
                  text + '</text></svg>';
        var mark = document.createElement('div');
        mark.id = 'sppSecureMark';
        mark.className = 'spp-secure-mark';
        mark.style.backgroundImage = 'url("data:image/svg+xml;utf8,' + encodeURIComponent(svg) + '")';
        document.body.appendChild(mark);
    }

    function boot() {
        if (!cfg() || !document.body) return;
        injectStyle();
        if (!document.body.classList.contains('spp-secure-noselect')) document.body.classList.add('spp-secure-noselect');
        watermark();
        watchdog();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
    document.addEventListener('DOMContentLoaded', boot);
    setInterval(boot, 2000);
    window.sppExamSecureBoot = boot;
}());
