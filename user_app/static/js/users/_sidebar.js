(function () {
    var sb = document.getElementById('appSb');
    var bd = document.getElementById('appSbBackdrop');
    if (!sb) return;

    window.appSidebarMini = function () {
        window.appSidebarClose();
    };
    window.appSidebarOpen = function () {
        sb.classList.add('is-open');
        if (bd) bd.classList.add('is-open');
    };
    window.appSidebarClose = function () {
        sb.classList.remove('is-open');
        if (bd) bd.classList.remove('is-open');
    };

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') window.appSidebarClose();
    });
})();
