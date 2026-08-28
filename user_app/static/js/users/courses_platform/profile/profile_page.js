(function () {
    var sb = document.getElementById('pfSidebar');
    var bd = document.getElementById('pfBackdrop');
    if (!sb) return;

    document.body.classList.remove('pf-mini');
    var toggleBtn = document.querySelector('.pf-topbar__btn');

    window.pfSidebarOpen = function () {
        sb.classList.add('is-open');
        if (bd) bd.classList.add('is-open');
        if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'true');
    };
    window.pfSidebarClose = function () {
        sb.classList.remove('is-open');
        if (bd) bd.classList.remove('is-open');
        if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'false');
    };
    window.pfSidebarToggle = function () {
        if (sb.classList.contains('is-open')) window.pfSidebarClose();
        else window.pfSidebarOpen();
    };
    window.pfSidebarMini = window.pfSidebarClose;

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') window.pfSidebarClose();
    });

    sb.querySelectorAll('.menu-item, .menu-link').forEach(function (el) {
        el.addEventListener('click', function () {
            window.pfSidebarClose();
        });
    });
})();
