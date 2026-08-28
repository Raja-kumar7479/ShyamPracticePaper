(function () {
    history.replaceState(null, '', location.href);
    window.addEventListener('popstate', function () {
        history.replaceState(null, '', location.href);
    });
    window.addEventListener('pageshow', function (e) {
        if (e.persisted) location.reload();
    });

    var btn = document.getElementById('tmClose');
    if (!btn) return;
    btn.addEventListener('click', function (e) {
        if (window.opener && !window.opener.closed) {
            e.preventDefault();
            try { window.opener.location.reload(); window.opener.focus(); } catch (err) {}
            window.close();
        }
    });
})();
