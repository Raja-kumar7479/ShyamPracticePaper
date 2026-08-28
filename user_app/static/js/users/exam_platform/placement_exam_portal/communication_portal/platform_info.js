(function () {
    var bar = document.getElementById('cookieBar');
    var okay = document.getElementById('cookieOkay');
    var manage = document.getElementById('cookieManage');
    var modal = document.getElementById('prefsModal');
    var openBtn = document.getElementById('openPrefs');
    var closeBtn = document.getElementById('closePrefs');
    var saveBtn = document.getElementById('savePrefs');
    var savedMsg = document.getElementById('prefsSaved');
    var payToggle = document.getElementById('prefPayment');

    function hideBar() {
        if (bar) bar.classList.add('is-hidden');
        try { localStorage.setItem('sapmCookieOk', '1'); } catch (e) {}
    }

    function openModal() {
        if (!modal) return;
        try {
            var prefs = JSON.parse(localStorage.getItem('sapmCookiePrefs') || '{}');
            if (payToggle && typeof prefs.payment === 'boolean') payToggle.checked = prefs.payment;
        } catch (e) {}
        if (savedMsg) savedMsg.hidden = true;
        modal.hidden = false;
        document.body.classList.add('mh-noscroll');
    }

    function closeModal() {
        if (!modal) return;
        modal.hidden = true;
        document.body.classList.remove('mh-noscroll');
    }

    try {
        if (bar && localStorage.getItem('sapmCookieOk') === '1') bar.classList.add('is-hidden');
    } catch (e) {}

    if (okay) okay.addEventListener('click', hideBar);
    if (manage) manage.addEventListener('click', openModal);
    if (openBtn) openBtn.addEventListener('click', openModal);
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (modal) modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeModal();
    });

    if (saveBtn) saveBtn.addEventListener('click', function () {
        var prefs = {
            necessary: true,
            analytics: false,
            advertising: false,
            payment: payToggle ? payToggle.checked : true,
            savedAt: new Date().toISOString()
        };
        try { localStorage.setItem('sapmCookiePrefs', JSON.stringify(prefs)); } catch (e) {}
        if (savedMsg) savedMsg.hidden = false;
        hideBar();
        setTimeout(closeModal, 900);
    });

    document.querySelectorAll('.mh-side__link').forEach(function (a) {
        a.addEventListener('click', function (e) {
            var target = document.querySelector(a.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
})();
