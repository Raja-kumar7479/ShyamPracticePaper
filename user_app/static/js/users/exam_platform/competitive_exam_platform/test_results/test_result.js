document.addEventListener('DOMContentLoaded', () => {
            const toggleBtn = document.getElementById('sidebarToggle');
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('overlay');


            const circles = document.querySelectorAll('.circular-progress');
            circles.forEach(circle => {
                const pct = circle.getAttribute('data-pct');
                const color = circle.getAttribute('data-color');
                const deg = pct * 3.6;

                setTimeout(() => {
                    circle.style.background = `conic-gradient(${color} ${deg}deg, var(--bg-body) 0deg)`;
                }, 300);
            });

            document.querySelectorAll('.progress-fill').forEach(fill => {
                const width = fill.getAttribute('data-width');
                setTimeout(() => { fill.style.width = width + '%'; }, 400);
            });
        });


(function () {
    var sb = document.getElementById('sidebar');
    var ov = document.getElementById('overlay');
    if (!sb) return;

    var toggles = document.querySelectorAll('[data-sb-toggle]');

    function setAria(open) {
        sb.setAttribute('aria-hidden', open ? 'false' : 'true');
        toggles.forEach(function (b) {
            b.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    }

    function openSb() {
        sb.classList.add('show');
        if (ov) { ov.classList.add('show'); ov.classList.add('active'); }
        setAria(true);
    }
    function closeSb() {
        sb.classList.remove('show');
        if (ov) { ov.classList.remove('show'); ov.classList.remove('active'); }
        setAria(false);
    }
    function toggleSb() {
        if (sb.classList.contains('show')) closeSb(); else openSb();
    }

    window.sbOpen = openSb;
    window.sbClose = closeSb;
    window.toggleSidebar = toggleSb;

    closeSb();

    toggles.forEach(function (b) {
        b.addEventListener('click', function (e) { e.preventDefault(); toggleSb(); });
    });
    document.querySelectorAll('[data-sb-close]').forEach(function (b) {
        b.addEventListener('click', function (e) { e.preventDefault(); closeSb(); });
    });
    if (ov) ov.addEventListener('click', closeSb);
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeSb();
    });
    sb.querySelectorAll('a.nav-link').forEach(function (a) {
        a.addEventListener('click', function () { setTimeout(closeSb, 60); });
    });
})();
