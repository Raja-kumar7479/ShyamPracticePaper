(function () {
    var ICONS = {
        success: 'fa-check-circle',
        danger: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };
    var HIDE_AFTER_MS = 5000;
    var SKIP = /alert-info|alert-light|alert-inline|admin-toast/;

    function stack() {
        var s = document.getElementById('adminToastStack');
        if (!s) {
            s = document.createElement('div');
            s.id = 'adminToastStack';
            s.className = 'admin-toasts';
            document.body.appendChild(s);
        }
        return s;
    }

    window.adminToast = function (message, type) {
        var text = message == null ? '' : String(message);
        if (!text.replace(/<[^>]*>/g, '').trim()) return null;
        var t = ['success', 'danger', 'warning', 'info'].indexOf(type) >= 0 ? type : 'info';
        var el = document.createElement('div');
        el.className = 'admin-toast admin-toast--' + t;
        el.setAttribute('role', 'alert');
        el.innerHTML = '<i class="fas ' + ICONS[t] + ' admin-toast__icon"></i>' +
            '<div class="admin-toast__msg"></div>' +
            '<button type="button" class="admin-toast__close" aria-label="Close">&times;</button>';
        el.querySelector('.admin-toast__msg').innerHTML = text;
        stack().appendChild(el);
        requestAnimationFrame(function () { el.classList.add('show'); });
        var timer = setTimeout(close, HIDE_AFTER_MS);
        function close() {
            clearTimeout(timer);
            el.classList.add('hide');
            setTimeout(function () { el.remove(); }, 320);
        }
        el.querySelector('.admin-toast__close').addEventListener('click', close);
        return el;
    };

    function typeFromClasses(className) {
        if (/success/.test(className)) return 'success';
        if (/danger|error|fail/.test(className)) return 'danger';
        if (/warn/.test(className)) return 'warning';
        return 'info';
    }

    function harvestServerFlashes() {
        var sels = ['#flash-messages .alert', '.cc-flash-wrap .alert', '.flash-message',
                    '.app-flash', '#alert-container .alert', '.alert-container .alert'];
        document.querySelectorAll(sels.join(',')).forEach(function (el) {
            var msgNode = el.querySelector('.app-flash__msg');
            var msg = (msgNode || el).textContent.replace(/×\s*$/, '').trim();
            el.remove();
            if (msg) window.adminToast(msg, typeFromClasses(el.className));
        });
    }

    function isShown(el) {
        if (!document.body.contains(el)) return false;
        if (el.style.display === 'none') return false;
        return window.getComputedStyle(el).display !== 'none';
    }

    function hijack(el) {
        if (!el.classList || !el.classList.contains('alert')) return;
        if (SKIP.test(el.className)) return;
        if (el.dataset.toastDone === '1') return;
        if (!isShown(el)) return;
        var html = el.innerHTML;
        if (!el.textContent.trim()) return;
        el.dataset.toastDone = '1';
        window.adminToast(html, typeFromClasses(el.className));
        el.classList.add('is-hidden');
        el.style.display = 'none';
        setTimeout(function () { delete el.dataset.toastDone; }, 400);
    }

    var attrObserver = new MutationObserver(function (muts) {
        muts.forEach(function (m) { hijack(m.target); });
    });

    function watch(el) {
        attrObserver.observe(el, { attributes: true, attributeFilter: ['class', 'style'], childList: true });
        hijack(el);
    }

    document.addEventListener('DOMContentLoaded', function () {
        harvestServerFlashes();
        document.querySelectorAll('.alert').forEach(watch);
        new MutationObserver(function (muts) {
            muts.forEach(function (m) {
                m.addedNodes.forEach(function (n) {
                    if (n.nodeType !== 1) return;
                    if (n.classList && n.classList.contains('alert')) watch(n);
                    if (n.querySelectorAll) n.querySelectorAll('.alert').forEach(watch);
                });
            });
        }).observe(document.body, { childList: true, subtree: true });
    });
})();
