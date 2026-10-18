(function () {
    var HIDE_AFTER_MS = 3000;
    var stack = document.getElementById('appFlashStack');
    if (!stack) return;
    var items = stack.querySelectorAll('.app-flash');

    function dismiss(el) {
        el.classList.add('hide');
        setTimeout(function () { el.remove(); }, 350);
    }

    items.forEach(function (el, i) {
        setTimeout(function () { el.classList.add('show'); }, 60 * i + 40);
        var timer = setTimeout(function () { dismiss(el); }, HIDE_AFTER_MS);
        var close = el.querySelector('.app-flash__close');
        if (close) {
            close.addEventListener('click', function () {
                clearTimeout(timer);
                dismiss(el);
            });
        }
    });
})();
