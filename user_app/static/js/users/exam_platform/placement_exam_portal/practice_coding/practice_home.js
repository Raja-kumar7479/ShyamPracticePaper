/* Right-rail calendar for the practice home page. Pure display: it shows the
 * current month with today highlighted, like the reference layout. */
(function () {
    'use strict';

    var host = document.getElementById('pcCal');
    var title = document.getElementById('pcCalTitle');
    if (!host || !title) return;

    var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                  'August', 'September', 'October', 'November', 'December'];
    var today = new Date();
    var view = new Date(today.getFullYear(), today.getMonth(), 1);

    function render() {
        title.textContent = MONTHS[view.getMonth()] + ' ' + view.getFullYear();
        var first = new Date(view.getFullYear(), view.getMonth(), 1).getDay();
        var days = new Date(view.getFullYear(), view.getMonth() + 1, 0).getDate();

        var html = '';
        ['S', 'M', 'T', 'W', 'T', 'F', 'S'].forEach(function (d) {
            html += '<span class="pc-cal__dow">' + d + '</span>';
        });
        for (var i = 0; i < first; i++) html += '<span></span>';
        for (var day = 1; day <= days; day++) {
            var isToday = day === today.getDate() &&
                view.getMonth() === today.getMonth() &&
                view.getFullYear() === today.getFullYear();
            html += '<span class="pc-cal__day' + (isToday ? ' is-today' : '') + '">' + day + '</span>';
        }
        host.innerHTML = html;
    }

    document.getElementById('pcCalPrev').addEventListener('click', function () {
        view.setMonth(view.getMonth() - 1); render();
    });
    document.getElementById('pcCalNext').addEventListener('click', function () {
        view.setMonth(view.getMonth() + 1); render();
    });
    render();
}());

(function () {
    'use strict';
    var ham = document.getElementById('pcHamburger');
    var side = document.getElementById('pcSide');
    var backdrop = document.getElementById('pcBackdrop');
    var closeBtn = document.getElementById('pcSideClose');
    if (!ham || !side) return;

    function open() {
        side.classList.add('is-open');
        if (backdrop) backdrop.classList.add('is-open');
        document.body.classList.add('pc-noscroll');
    }
    function close() {
        side.classList.remove('is-open');
        if (backdrop) backdrop.classList.remove('is-open');
        document.body.classList.remove('pc-noscroll');
    }

    ham.addEventListener('click', open);
    if (backdrop) backdrop.addEventListener('click', close);
    if (closeBtn) closeBtn.addEventListener('click', close);
    side.querySelectorAll('a').forEach(function (a) { a.addEventListener('click', close); });
    window.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
    window.addEventListener('resize', function () { if (window.innerWidth > 768) close(); });
}());
