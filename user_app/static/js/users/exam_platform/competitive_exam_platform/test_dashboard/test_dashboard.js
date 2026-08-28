document.addEventListener('DOMContentLoaded', () => {
        const btnAll = document.getElementById('btnAll');
        const btnUnperformed = document.getElementById('btnUnperformed');
        const btnResults = document.getElementById('btnResults');
        const testGrid = document.getElementById('testGrid');
        const resultsList = document.getElementById('resultsList');
        const testCards = document.querySelectorAll('.test-card');

        function activateTab(btn) {
            [btnAll, btnUnperformed, btnResults].forEach(b => {
                if(b) b.classList.remove('active');
            });
            if(btn) btn.classList.add('active');
        }

        if(btnAll) {
            btnAll.addEventListener('click', () => {
                activateTab(btnAll);
                testGrid.style.display = 'grid';
                resultsList.style.display = 'none';
                testCards.forEach(card => card.style.display = 'flex');
            });
        }

        if(btnUnperformed) {
            btnUnperformed.addEventListener('click', () => {
                activateTab(btnUnperformed);
                testGrid.style.display = 'grid';
                resultsList.style.display = 'none';
                testCards.forEach(card => {
                    card.style.display = 'flex';
                });
            });
        }

        if(btnResults) {
            btnResults.addEventListener('click', () => {
                activateTab(btnResults);
                testGrid.style.display = 'none';
                resultsList.style.display = 'block';
            });
        }
    });

(function () {
    var sb = document.getElementById('sidebar');
    var ov = document.getElementById('overlay');
    if (!sb) return;

    var toggles = document.querySelectorAll('[data-sb-toggle]');

    function setAria(open) {
        sb.setAttribute('aria-hidden', open ? 'false' : 'true');
        toggles.forEach(function (b) {
            b.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    }

    function openDrawer() {
        sb.classList.add('show');
        if (ov) { ov.classList.add('show'); ov.classList.add('active'); }
        setAria(true);
    }
    function closeDrawer() {
        sb.classList.remove('show');
        if (ov) { ov.classList.remove('show'); ov.classList.remove('active'); }
        setAria(false);
    }

    window.sbOpen = openDrawer;
    window.sbClose = closeDrawer;
    window.toggleSidebar = function () {
        if (sb.classList.contains('show')) closeDrawer();
        else openDrawer();
    };

    try { localStorage.removeItem('mockSbMini'); } catch (e) {}
    document.body.classList.remove('sidebar-mini');
    closeDrawer();

    toggles.forEach(function (b) {
        b.addEventListener('click', function (e) { e.preventDefault(); window.toggleSidebar(); });
    });
    document.querySelectorAll('[data-sb-close]').forEach(function (b) {
        b.addEventListener('click', function (e) { e.preventDefault(); closeDrawer(); });
    });

    if (ov) ov.addEventListener('click', closeDrawer);
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeDrawer();
    });
    sb.querySelectorAll('a.nav-link').forEach(function (a) {
        a.addEventListener('click', function () { setTimeout(closeDrawer, 60); });
    });
})();
