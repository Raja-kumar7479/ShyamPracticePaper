(function () {
    var btn = document.getElementById('tcClose');
    if (!btn) return;
    if (window.opener && !window.opener.closed) {
        btn.textContent = 'Close Window';
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            try {
                window.opener.location.reload();
                window.opener.focus();
            } catch (err) {}
            window.close();
        });
    }
})();
