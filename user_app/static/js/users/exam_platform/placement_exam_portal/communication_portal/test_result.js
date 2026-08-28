document.addEventListener('DOMContentLoaded', function () {
    var sidebar = document.getElementById('trSidebar');
    var backdrop = document.getElementById('trSidebarBackdrop');
    var toggles = Array.prototype.slice.call(document.querySelectorAll('.tr-sb-toggle'));

    function isSidebarOpen() {
        return !!sidebar && sidebar.classList.contains('is-open');
    }

    function setSidebar(open) {
        if (!sidebar) return;
        sidebar.classList.toggle('is-open', open);
        if (backdrop) backdrop.classList.toggle('is-open', open);
        document.body.classList.toggle('tr-sb-open', open);
        sidebar.setAttribute('aria-hidden', open ? 'false' : 'true');
        toggles.forEach(function (t) {
            t.setAttribute('aria-expanded', open ? 'true' : 'false');
            t.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
        });
    }

    toggles.forEach(function (t) {
        t.addEventListener('click', function () { setSidebar(!isSidebarOpen()); });
    });
    var closeBtn = document.getElementById('trSidebarClose');
    if (closeBtn) closeBtn.addEventListener('click', function () { setSidebar(false); });
    if (backdrop) backdrop.addEventListener('click', function () { setSidebar(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setSidebar(false); });

    function showPanel(id) {
        var target = document.getElementById(id);
        if (!target) return;
        document.querySelectorAll('.tr-panel').forEach(function (p) {
            p.classList.toggle('is-active', p === target);
        });
        document.querySelectorAll('.tr-nav[data-goto]').forEach(function (b) {
            b.classList.toggle('is-active', b.dataset.goto === id);
        });
        window.scrollTo({ top: 0, behavior: 'smooth' });
        setSidebar(false);
        try { history.replaceState(null, '', '#' + id); } catch (e) {}
    }

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-goto]');
        if (!btn) return;
        showPanel(btn.dataset.goto);
    });

    if (window.location.hash && document.getElementById(window.location.hash.slice(1))) {
        showPanel(window.location.hash.slice(1));
    }

    var printBtn = document.getElementById('trPrintBtn');
    if (printBtn) {
        printBtn.addEventListener('click', function () {
            document.querySelectorAll('.tr-panel').forEach(function (p) { p.classList.add('is-print'); });
            setTimeout(function () {
                window.print();
                setTimeout(function () {
                    document.querySelectorAll('.tr-panel').forEach(function (p) { p.classList.remove('is-print'); });
                }, 400);
            }, 120);
        });
    }

    if (typeof Chart === 'undefined') return;
    var el = document.getElementById('overallChart');
    if (!el || window.TR_OVERALL == null) return;
    var pct = Math.max(0, Math.min(100, window.TR_OVERALL));
    var color = pct >= 80 ? '#1e7b34' : pct >= 60 ? '#992c25' : pct >= 40 ? '#f0ae06' : '#c0392b';
    new Chart(el, {
        type: 'doughnut',
        data: { datasets: [{ data: [pct, 100 - pct], backgroundColor: [color, '#edf1f5'], borderWidth: 0 }] },
        options: {
            cutout: '76%', responsive: false, animation: { duration: 700 },
            plugins: { legend: { display: false }, tooltip: { enabled: false } }
        }
    });
});

(function () {
    var btn = document.getElementById('trCopyLink');
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
