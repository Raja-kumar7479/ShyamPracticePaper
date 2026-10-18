document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.ra-toast').forEach(function (box) {
        var btn = box.querySelector('.ra-toast__close');
        if (btn) {
            btn.addEventListener('click', function () { box.remove(); });
        }
        setTimeout(function () {
            box.classList.add('is-out');
            setTimeout(function () { box.remove(); }, 250);
        }, 3000);
    });

    function toast(message) {
        var stack = document.querySelector('.ra-toasts');
        if (!stack) {
            stack = document.createElement('div');
            stack.className = 'ra-toasts';
            document.body.appendChild(stack);
        }
        var box = document.createElement('div');
        box.className = 'ra-toast';
        box.setAttribute('role', 'alert');
        var icon = document.createElement('i');
        icon.className = 'fas fa-circle-exclamation';
        var text = document.createElement('span');
        text.textContent = message;
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'ra-toast__close';
        close.innerHTML = '&times;';
        close.addEventListener('click', function () { box.remove(); });
        box.appendChild(icon);
        box.appendChild(text);
        box.appendChild(close);
        stack.appendChild(box);
        setTimeout(function () { box.remove(); }, 5000);
    }

    var examWindow = null;

    document.querySelectorAll('.ra-launch').forEach(function (link) {
        link.addEventListener('click', function (e) {
            e.preventDefault();

            if (examWindow && !examWindow.closed) {
                examWindow.focus();
                toast('Already another test running. First close it, then proceed.');
                return;
            }

            examWindow = window.open(link.href, 'sppAssessmentWindow');

            if (!examWindow) {
                toast('Your browser blocked the assessment window. Allow pop-ups and try again.');
                return;
            }

            try {
                examWindow.moveTo(0, 0);
                examWindow.resizeTo(screen.availWidth, screen.availHeight);
            } catch (err) {}
            examWindow.focus();

            var watcher = setInterval(function () {
                if (examWindow.closed) {
                    clearInterval(watcher);
                    window.location.reload();
                }
            }, 1500);
        });
    });

    var sidebar = document.getElementById('raSidebar');
    var backdrop = document.getElementById('raSidebarBackdrop');
    var toggle = document.getElementById('raSidebarToggle');
    var closeBtn = document.getElementById('raSidebarClose');

    if (sidebar && backdrop && toggle && closeBtn) {
        var lastFocus = null;

        function focusables() {
            return Array.prototype.slice.call(
                sidebar.querySelectorAll('a[href], button:not([disabled])')
            ).filter(function (el) { return el.offsetParent !== null; });
        }

        function isDocked() {
            return false;
        }

        function isOpen() {
            return isDocked()
                ? !document.body.classList.contains('ra-sb-mini')
                : sidebar.classList.contains('is-open');
        }

        function setOpen(open) {
            var docked = isDocked();

            if (docked) {
                document.body.classList.toggle('ra-sb-mini', !open);
                sidebar.classList.remove('is-open');
                backdrop.classList.remove('is-open');
                document.body.classList.remove('ra-sidebar-open');
            } else {
                document.body.classList.remove('ra-sb-mini');
                sidebar.classList.toggle('is-open', open);
                backdrop.classList.toggle('is-open', open);
                document.body.classList.toggle('ra-sidebar-open', open);
            }

            sidebar.setAttribute('aria-hidden', docked ? 'false' : (open ? 'false' : 'true'));
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            toggle.setAttribute('aria-label', open ? 'Close assessments menu' : 'Open assessments menu');

            if (open && !docked) {
                lastFocus = document.activeElement;
                var f = focusables();
                if (f.length) f[0].focus();
            } else if (!open && !docked && lastFocus) {
                lastFocus.focus();
                lastFocus = null;
            }
        }

        function syncToViewport() {
            document.body.classList.remove('ra-sb-mini');
            sidebar.setAttribute('aria-hidden',
                sidebar.classList.contains('is-open') ? 'false' : 'true');
            toggle.setAttribute('aria-expanded',
                sidebar.classList.contains('is-open') ? 'true' : 'false');
        }

        syncToViewport();
        window.addEventListener('resize', syncToViewport);

        toggle.addEventListener('click', function () {
            setOpen(!isOpen());
        });
        closeBtn.addEventListener('click', function () { setOpen(false); });
        backdrop.addEventListener('click', function () { setOpen(false); });

        sidebar.querySelectorAll('[data-close]').forEach(function (a) {
            a.addEventListener('click', function () {
                sidebar.querySelectorAll('.ra-sidebar__test').forEach(function (x) {
                    x.classList.remove('is-active');
                });
                a.classList.add('is-active');
                if (!isDocked()) setOpen(false);
            });
        });

        document.addEventListener('keydown', function (e) {
            if (!sidebar.classList.contains('is-open')) return;

            if (e.key === 'Escape') {
                setOpen(false);
                return;
            }

            if (e.key === 'Tab') {
                var f = focusables();
                if (!f.length) return;
                var first = f[0];
                var last = f[f.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        });
    }
    var filterBtns = document.querySelectorAll('.ra-filter');
    var cards = document.querySelectorAll('.test-card[data-status]');
    var grid = document.querySelector('.ra-grid');
    var emptyMsg = null;

    function applyFilter(which) {
        var shown = 0;
        cards.forEach(function (card) {
            var match = (which === 'all') || (card.dataset.status === which);
            card.style.display = match ? '' : 'none';
            if (match) shown++;
        });
        if (!emptyMsg && grid) {
            emptyMsg = document.createElement('div');
            emptyMsg.className = 'ra-empty';
            emptyMsg.innerHTML = '<i class="fas fa-inbox fa-3x"></i><h5>Nothing here yet</h5><p>No assessments in this category.</p>';
            emptyMsg.style.display = 'none';
            grid.appendChild(emptyMsg);
        }
        if (emptyMsg) emptyMsg.style.display = shown ? 'none' : '';
    }

    filterBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            filterBtns.forEach(function (b) { b.classList.toggle('is-active', b === btn); });
            applyFilter(btn.dataset.filter);
            var sb = document.getElementById('raSidebar');
            var bd = document.getElementById('raSidebarBackdrop');
            if (sb) sb.classList.remove('is-open');
            if (bd) bd.classList.remove('is-open');
            document.body.classList.remove('ra-sidebar-open');
        });
    });
});
