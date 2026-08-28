const body = document.body;
const menuBtn = document.getElementById('menuToggle');
const overlay = document.getElementById('sidebarOverlay');
const sidebarEl = document.getElementById('sidebar');
const sidebarCloseBtn = document.getElementById('sidebarClose');

function setPqSidebar(open) {
    body.classList.toggle('sidebar-open', open);
    if (sidebarEl) sidebarEl.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (menuBtn) {
        menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
        menuBtn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    }
}

if (menuBtn) {
    menuBtn.addEventListener('click', function () {
        setPqSidebar(!body.classList.contains('sidebar-open'));
    });
}

if (sidebarCloseBtn) {
    sidebarCloseBtn.addEventListener('click', function () {
        setPqSidebar(false);
    });
}

if (overlay) {
    overlay.addEventListener('click', function () {
        setPqSidebar(false);
    });
}

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') setPqSidebar(false);
});

(function () {
    var SESSION_PREFIX = 'pq_v3_';

    function clearAllPracticeSessions() {
        try {
            Object.keys(localStorage).forEach(function (key) {
                if (key.indexOf(SESSION_PREFIX) === 0) {
                    localStorage.removeItem(key);
                }
            });
        } catch (e) {}
    }

    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
        return match ? decodeURIComponent(match[1]) : null;
    }

    function deleteCookie(name) {
        document.cookie = name + '=; Max-Age=0; path=/';
    }

    if (getCookie('pq_logout_trigger') === '1') {
        clearAllPracticeSessions();
        deleteCookie('pq_logout_trigger');
    }
})();
