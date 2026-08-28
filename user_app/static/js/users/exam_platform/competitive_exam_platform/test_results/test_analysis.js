        function switchSection(element, sectionId) {
            document.querySelectorAll('.section-trigger').forEach(el => el.classList.remove('active'));
            element.classList.add('active');

            document.querySelectorAll('.section-wrapper').forEach(el => el.style.display = 'none');

            const target = document.getElementById('wrapper-' + sectionId);
            if(target) target.style.display = 'block';

            if (window.sbClose) window.sbClose();
        }


        function filterList(type, sectionId, btn) {
            const wrapper = document.getElementById('wrapper-' + sectionId);

            wrapper.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const items = wrapper.querySelectorAll('.q-card');
            let visibleCount = 0;

            items.forEach(item => {
                if(type === 'all' || item.dataset.status === type) {
                    item.style.display = 'block';
                    visibleCount++;
                } else {
                    item.style.display = 'none';
                }
            });

            const emptyDiv = document.getElementById('empty-' + sectionId);
            const emptyMsg = document.getElementById('empty-msg-' + sectionId);

            if(visibleCount === 0) {
                emptyDiv.style.display = 'block';
                const msgs = {
                    'correct': 'Good effort! But no correct answers here yet.',
                    'incorrect': 'Great job! No incorrect answers found.',
                    'skipped': 'You attempted everything! No skipped questions.',
                    'all': 'No questions available.'
                };
                emptyMsg.innerText = msgs[type] || 'No questions found.';
            } else {
                emptyDiv.style.display = 'none';
            }
        }


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

    function openSb() {
        sb.classList.add('show');
        if (ov) { ov.classList.add('show'); ov.classList.add('active'); }
        setAria(true);
    }
    function closeSb() {
        sb.classList.remove('show');
        if (ov) { ov.classList.remove('show'); ov.classList.remove('active'); }
        setAria(false);
    }
    function toggleSb() {
        if (sb.classList.contains('show')) closeSb(); else openSb();
    }

    window.sbOpen = openSb;
    window.sbClose = closeSb;
    window.toggleSidebar = toggleSb;

    closeSb();

    toggles.forEach(function (b) {
        b.addEventListener('click', function (e) { e.preventDefault(); toggleSb(); });
    });
    document.querySelectorAll('[data-sb-close]').forEach(function (b) {
        b.addEventListener('click', function (e) { e.preventDefault(); closeSb(); });
    });
    if (ov) ov.addEventListener('click', closeSb);
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeSb();
    });
    sb.querySelectorAll('a.nav-link').forEach(function (a) {
        a.addEventListener('click', function () { setTimeout(closeSb, 60); });
    });
})();
