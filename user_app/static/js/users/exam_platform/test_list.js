(function () {
    var busy = false;
    var restoreTimer = null;

    function restore() {
        busy = false;
        if (restoreTimer) { clearTimeout(restoreTimer); restoreTimer = null; }
        document.body.classList.remove('tl-busy');
        document.querySelectorAll('a.btn-action.is-loading').forEach(function (link) {
            link.classList.remove('is-loading');
            link.removeAttribute('aria-busy');
            if (link.dataset.label) link.innerHTML = link.dataset.label;
        });
    }

    function spin(link, text) {
        if (!link.dataset.label) link.dataset.label = link.innerHTML;
        link.classList.add('is-loading');
        link.setAttribute('aria-busy', 'true');
        link.innerHTML = '<span class="tl-spin" aria-hidden="true"></span><span>' + text + '</span>';
        document.body.classList.add('tl-busy');
    }

    function openExamWindow(link) {
        var href = link.getAttribute('href');
        var w = window.open(href, 'sppExamWindow');
        if (!w) {
            window.location.href = href;
            return;
        }
        try { w.moveTo(0, 0); w.resizeTo(screen.availWidth, screen.availHeight); } catch (err) {}
        try { w.focus(); } catch (err) {}
        setTimeout(function () {
            link.classList.remove('is-loading');
            link.removeAttribute('aria-busy');
            link.classList.add('is-open');
            link.innerHTML = '<i class="fas fa-circle-check"></i> Exam window is open';
        }, 900);
        var poll = setInterval(function () {
            if (w.closed) { clearInterval(poll); window.location.reload(); }
        }, 1500);
    }

    document.querySelectorAll('.test-card .card-footer a.btn-action').forEach(function (link) {
        link.addEventListener('click', function (e) {
            if (busy || link.classList.contains('is-open')) {
                e.preventDefault();
                return;
            }
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1) {
                e.preventDefault();
            }
            busy = true;
            spin(link, 'Opening...');
            if (link.classList.contains('tl-launch')) {
                e.preventDefault();
                openExamWindow(link);
                return;
            }
            if (e.defaultPrevented) window.location.href = link.getAttribute('href');
            restoreTimer = setTimeout(restore, 30000);
        });
    });

    window.addEventListener('pageshow', function (e) {
        if (e.persisted) restore();
    });
}());
