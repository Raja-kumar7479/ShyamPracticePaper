(function () {
    var btn = document.getElementById('qpClose');
    if (!btn) return;
    btn.addEventListener('click', function () {
        if (window.opener && !window.opener.closed) {
            window.close();
            return;
        }
        history.back();
    });

    document.addEventListener('contextmenu', function (e) { e.preventDefault(); });
    document.addEventListener('keydown', function (e) {
        var k = (e.key || '').toLowerCase();
        if ((e.ctrlKey || e.metaKey) && (k === 's' || k === 'u' || k === 'p')) {
            e.preventDefault();
        }
    });
})();
