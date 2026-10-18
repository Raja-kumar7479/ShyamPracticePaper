(function () {
    'use strict';

    var SECONDS = 10;

    var button = document.getElementById('btnStart');
    var timerText = document.getElementById('btnTimerText');
    var topTimer = document.getElementById('topTimer');
    var status = document.getElementById('readyStatus');
    var message = document.getElementById('readyMsg');
    var link = document.getElementById('startLink');

    if (!button) return;

    var ready = false;
    var launching = false;
    if (link) {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            if (!ready || launching) return;
            launching = true;
            launch(link.getAttribute('href'));
        });
    }

    function setReady() {
        ready = true;
        button.disabled = false;
        button.classList.add('is-ready');
        if (timerText) timerText.textContent = 'You can start now';
        if (topTimer) topTimer.textContent = 'Ready';
        if (status) status.classList.add('is-ok');
        if (message) message.textContent = 'Your assessment is ready.';
    }

    var left = SECONDS;
    if (message) message.textContent = 'Preparing your assessment...';
    if (status) status.classList.add('is-waiting');

    var tick = setInterval(function () {
        left -= 1;
        if (left <= 0) {
            clearInterval(tick);
            setReady();
            return;
        }
        if (timerText) timerText.textContent = 'Start in ' + left + 's';
        if (topTimer) topTimer.textContent = 'Ready? ' + left + 's';
    }, 1000);

    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && ready && message) {
            message.textContent = 'Your assessment is ready.';
        }
    });

    function enterFullscreen() {
        var el = document.documentElement;
        var fn = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
        if (!fn) return Promise.resolve();
        try {
            var r = fn.call(el);
            return (r && typeof r.then === 'function') ? r : Promise.resolve();
        } catch (e) {
            return Promise.resolve();
        }
    }

    function loadCss(hrefs) {
        return Promise.all(hrefs.map(function (href) {
            return new Promise(function (resolve) {
                var l = document.createElement('link');
                l.rel = 'stylesheet';
                l.href = href;
                l.onload = resolve;
                l.onerror = resolve;
                document.head.appendChild(l);
            });
        }));
    }

    function runInlineScripts(root) {
        if (!root) return;
        Array.prototype.slice.call(root.querySelectorAll('script:not([src])'))
            .forEach(function (old) {
                var s = document.createElement('script');
                s.textContent = old.textContent;
                old.parentNode.replaceChild(s, old);
            });
    }

    function loadScriptsSequentially(srcs) {
        return srcs.reduce(function (chain, src) {
            return chain.then(function () {
                var esc = (window.CSS && CSS.escape) ? CSS.escape(src) : src;
                if (document.querySelector('script[data-exam-src="' + esc + '"]')) return;
                return new Promise(function (resolve, reject) {
                    var s = document.createElement('script');
                    s.src = src;
                    s.dataset.examSrc = src;
                    s.onload = resolve;
                    s.onerror = reject;
                    document.head.appendChild(s);
                });
            });
        }, Promise.resolve());
    }

    function buildExamDocument(cfg, payload) {
        if (!document.querySelector('meta[name="csrf-token"]')) {
            var m = document.createElement('meta');
            m.name = 'csrf-token';
            m.content = cfg.csrf;
            document.head.appendChild(m);
        }
        Array.prototype.slice.call(
            document.querySelectorAll('link[rel="stylesheet"]')
        ).forEach(function (l) { l.parentNode.removeChild(l); });

        document.title = payload.title || document.title;
        document.body.className = '';
        document.body.innerHTML = '<div id="page-root">' + payload.html + '</div>';
        runInlineScripts(document.getElementById('page-root'));
        history.replaceState({ examUrl: payload.url }, '', payload.url);

        return loadCss(cfg.coreCss.concat(payload.css || []))
            .then(function () {
                return loadScriptsSequentially(cfg.coreJs.concat(payload.js || []));
            })
            .then(function () {
                window.CJ.examNav.boot(payload);
            });
    }

    var RETRY_WAITS = [1500, 3000, 6000];

    function fetchStart(href, attempt) {
        return fetch(href, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        }).then(function (res) {
            var busy = res.status >= 500 || res.status === 429 || res.status === 408;
            if (!busy || attempt >= RETRY_WAITS.length) return res;
            throw new Error('busy');
        }).catch(function (err) {
            if (attempt >= RETRY_WAITS.length) throw err;
            button.innerHTML = '<span class="lobby-spin" aria-hidden="true"></span>Server is busy, trying again...';
            return new Promise(function (resolve) {
                setTimeout(resolve, RETRY_WAITS[attempt] + Math.floor(Math.random() * 800));
            }).then(function () { return fetchStart(href, attempt + 1); });
        });
    }

    function startExamInPlace(href) {
        var cfgEl = document.getElementById('examLaunchConfig');
        if (!cfgEl) return Promise.reject(new Error('no launch config'));
        var cfg = JSON.parse(cfgEl.textContent);
        return fetchStart(href, 0).then(function (res) {
            if (!res.ok) throw new Error('start failed (' + res.status + ')');
            var ct = res.headers.get('content-type') || '';
            if (ct.indexOf('application/json') === -1) throw new Error('not a fragment');
            return res.json();
        }).then(function (payload) {
            if (payload.redirect) {
                window.location.href = payload.redirect;
                return;
            }
            return buildExamDocument(cfg, payload);
        });
    }

    function launch(href) {
        clearInterval(tick);
        button.disabled = true;
        button.innerHTML = '<span class="lobby-spin" aria-hidden="true"></span>Starting...';
        enterFullscreen().catch(function () {}).then(function () {
            startExamInPlace(href).catch(function () {
                window.location.href = href;
            });
        });
    }
}());
