document.addEventListener('DOMContentLoaded', function () {

    const navItems = document.querySelectorAll('.as-view[data-view]');
    const views = {
        format: document.getElementById('ppView-format'),
        csv: document.getElementById('ppView-csv'),
        manual: document.getElementById('ppView-manual'),
        image: document.getElementById('ppView-image'),
        search: document.getElementById('ppView-search'),
        notes: document.getElementById('ppView-notes')
    };

    function closeSidebar() {
        if (window.matchMedia('(max-width: 991px)').matches && window.asClose) {
            window.asClose();
        }
    }

    function showView(name) {
        if (!views[name]) return;
        console.log('[PRACTICE] switching view ->', name);
        navItems.forEach(function (btn) {
            btn.classList.toggle('is-active', btn.dataset.view === name);
        });
        Object.keys(views).forEach(function (key) {
            if (views[key]) views[key].classList.toggle('is-active', key === name);
        });
        closeSidebar();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        try {
            localStorage.setItem('ppView', name);
        } catch (e) {}
    }

    navItems.forEach(function (btn) {
        btn.addEventListener('click', function () {
            showView(btn.dataset.view);
        });
    });

    window.ppShowView = showView;

    let start = 'format';
    try {
        const saved = localStorage.getItem('ppView');
        if (saved && views[saved]) start = saved;
    } catch (e) {}
    showView(start);
});
