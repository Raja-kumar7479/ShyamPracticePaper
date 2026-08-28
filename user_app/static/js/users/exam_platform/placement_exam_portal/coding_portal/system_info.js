(function () {
    'use strict';

    var track = document.getElementById('slider-track');
    var dots = Array.prototype.slice.call(document.querySelectorAll('.slider-dot-custom'));
    var slides = track ? track.children.length : 0;
    var index = 0;
    var auto = null;

    function show(i) {
        if (!track || !slides) return;
        index = (i + slides) % slides;
        track.style.transform = 'translateX(' + (-index * 100) + '%)';
        dots.forEach(function (d, n) { d.classList.toggle('active', n === index); });
    }
    function startAuto() {
        stopAuto();
        auto = setInterval(function () { show(index + 1); }, 6000);
    }
    function stopAuto() { if (auto) { clearInterval(auto); auto = null; } }

    var prev = document.getElementById('slider-prev');
    var next = document.getElementById('slider-next');
    if (prev) prev.addEventListener('click', function () { show(index - 1); startAuto(); });
    if (next) next.addEventListener('click', function () { show(index + 1); startAuto(); });
    dots.forEach(function (d, n) {
        d.addEventListener('click', function () { show(n); startAuto(); });
    });
    show(0);
    startAuto();

    function mark(name, ok, label) {
        var row = document.querySelector('.sys-check__row[data-check="' + name + '"]');
        if (!row) return;
        row.classList.remove('is-pending');
        row.classList.add(ok ? 'is-ok' : 'is-bad');
        if (label) {
            var text = row.querySelector('.sys-check__label');
            if (text) text.textContent = label;
        }
    }

    function checkBrowser() {
        var ok = typeof window.fetch === 'function' &&
                 typeof window.Promise === 'function' &&
                 typeof document.querySelector === 'function';
        mark('browser', ok, ok ? 'Browser support' : 'Browser is too old - please use a recent Chrome, Edge or Firefox');
        return ok;
    }

    function checkStorage() {
        var ok = false;
        try {
            window.localStorage.setItem('cj-check', '1');
            window.localStorage.removeItem('cj-check');
            ok = true;
        } catch (e) { ok = false; }
        mark('storage', ok, ok ? 'Local storage (autosave)'
                               : 'Storage is blocked - turn off private mode so your code can be saved');
        return ok;
    }

    function checkScreen() {
        var ok = window.innerWidth >= 900;
        mark('screen', ok, ok ? 'Screen size for the code editor'
                              : 'Screen is narrow - use a laptop or desktop for the code editor');
        return ok;
    }

    function checkNetwork() {
        if (!navigator.onLine) {
            mark('network', false, 'No internet connection');
            return Promise.resolve(false);
        }
        return fetch(window.location.pathname, { method: 'HEAD', cache: 'no-store' })
            .then(function (res) {
                var ok = res.ok;
                mark('network', ok, ok ? 'Connection to the exam server'
                                       : 'Cannot reach the exam server');
                return ok;
            })
            .catch(function () {
                mark('network', false, 'Cannot reach the exam server');
                return false;
            });
    }

    var button = document.getElementById('btnProceed');
    var note = document.getElementById('proceedNote');

    function finish(results) {
        var blocking = results.browser && results.storage && results.network;
        if (!button) return;
        if (blocking) {
            button.classList.remove('disabled');
            button.removeAttribute('aria-disabled');
            if (note) {
                note.textContent = results.screen
                    ? 'All checks passed. You can proceed.'
                    : 'You can proceed, but a bigger screen is strongly recommended.';
                note.classList.toggle('is-warn', !results.screen);
            }
        } else if (note) {
            note.textContent = 'Please fix the items marked in red, then refresh this page.';
            note.classList.add('is-bad');
        }
    }

    var results = {
        browser: checkBrowser(),
        storage: checkStorage(),
        screen: checkScreen()
    };
    checkNetwork().then(function (ok) {
        results.network = ok;
        finish(results);
    });

    if (button) {
        button.addEventListener('click', function (e) {
            if (button.classList.contains('disabled')) {
                e.preventDefault();
                if (note) note.textContent = 'Some checks have not passed yet. Please wait or fix the items above.';
            }
        });
    }
}());
