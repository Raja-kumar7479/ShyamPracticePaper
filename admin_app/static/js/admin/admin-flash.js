(function () {
    var stack = document.getElementById('appFlashStack');
    if (!stack) return;
    var items = stack.querySelectorAll('.app-flash');
    function dismiss(el) {
        el.classList.add('hide');
        setTimeout(function () { el.remove(); }, 350);
    }
    items.forEach(function (el, i) {
        setTimeout(function () { el.classList.add('show'); }, 60 * i + 40);
        var timer = setTimeout(function () { dismiss(el); }, 5200 + 500 * i);
        el.querySelector('.app-flash__close').addEventListener('click', function () {
            clearTimeout(timer);
            dismiss(el);
        });
    });
})();
