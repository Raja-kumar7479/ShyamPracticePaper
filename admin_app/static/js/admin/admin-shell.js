(function () {
    var sb = document.getElementById('asSidebar');
    var bd = document.getElementById('asBackdrop');
    if (!sb) return;

    var isDesktop = function () { return window.matchMedia('(min-width: 992px)').matches; };

    window.asOpen = function () {
        sb.classList.add('is-open');
        if (bd) bd.classList.add('is-open');
    };
    window.asClose = function () {
        sb.classList.remove('is-open');
        if (bd) bd.classList.remove('is-open');
    };
    window.asToggle = function () {
        if (isDesktop()) {
            document.body.classList.toggle('as-mini');
            try {
                localStorage.setItem('asMini', document.body.classList.contains('as-mini') ? '1' : '0');
            } catch (e) {}
        } else if (sb.classList.contains('is-open')) {
            window.asClose();
        } else {
            window.asOpen();
        }
    };

    try {
        if (localStorage.getItem('asMini') === '1' && isDesktop()) {
            document.body.classList.add('as-mini');
        }
    } catch (e) {}

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') window.asClose();
    });
    window.addEventListener('resize', function () { if (isDesktop()) window.asClose(); });
})();
