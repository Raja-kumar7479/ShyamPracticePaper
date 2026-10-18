document.addEventListener('DOMContentLoaded', function () {

    const navItems = document.querySelectorAll('.as-view[data-view]');
    const testSelect = document.getElementById('testIdSelect');
    const noTestHint = document.getElementById('mtNoTest');
    const selectedLabel = document.getElementById('mtSelectedTest');

    const views = {
        upload: document.getElementById('mtView-existing')
    };

    function closeSidebar() {
        if (window.matchMedia('(max-width: 991px)').matches && window.asClose) {
            window.asClose();
        }
    }

    function adjustTable() {
        if (window.jQuery && jQuery.fn.dataTable &&
            jQuery.fn.dataTable.isDataTable('#testDescriptionsTable')) {
            jQuery('#testDescriptionsTable').DataTable().columns.adjust().draw(false);
        }
    }

    function showView(name) {
        navItems.forEach(function (btn) {
            btn.classList.toggle('is-active', btn.dataset.view === name);
        });
        Object.keys(views).forEach(function (key) {
            if (views[key]) views[key].classList.toggle('is-active', key === name);
        });
        closeSidebar();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        if (name === 'upload') setTimeout(adjustTable, 60);
    }

    navItems.forEach(function (btn) {
        btn.addEventListener('click', function () {
            showView(btn.dataset.view);
        });
    });

    function syncTestState() {
        const hasTest = !!(testSelect && testSelect.value);
        if (noTestHint) noTestHint.style.display = hasTest ? 'none' : '';
        if (selectedLabel) {
            let text = 'No test selected';
            if (hasTest) {
                const opt = testSelect.options[testSelect.selectedIndex];
                text = opt ? opt.textContent.trim() : testSelect.value;
            }
            selectedLabel.textContent = text;
        }
        navItems.forEach(function (btn) { btn.disabled = !hasTest; });
        if (hasTest) setTimeout(adjustTable, 120);
    }

    if (testSelect) {
        testSelect.addEventListener('change', syncTestState);
    }
    syncTestState();

    document.addEventListener('click', function (e) {
        const btn = e.target.closest ? e.target.closest('.load-questions-btn') : null;
        if (btn) showView('upload');
    });
});
