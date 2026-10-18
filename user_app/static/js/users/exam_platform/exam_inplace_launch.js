(function () {
    'use strict';

    function enterFullscreen() {
        var el = document.documentElement;
        var fn = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
        if (!fn) return Promise.resolve(false);
        try {
            var r = fn.call(el);
            if (r && typeof r.then === 'function') {
                return r.then(function () { return true; }).catch(function () { return false; });
            }
            return Promise.resolve(true);
        } catch (e) {
            return Promise.resolve(false);
        }
    }

    function loadStylesheet(node) {
        return new Promise(function (resolve) {
            var link = document.createElement('link');
            Array.prototype.forEach.call(node.attributes, function (a) { link.setAttribute(a.name, a.value); });
            var timer = setTimeout(resolve, 4000);
            link.onload = link.onerror = function () { clearTimeout(timer); resolve(); };
            document.head.appendChild(link);
        });
    }

    function runScripts(scripts) {
        return scripts.reduce(function (chain, old) {
            return chain.then(function () {
                return new Promise(function (resolve) {
                    var s = document.createElement('script');
                    Array.prototype.forEach.call(old.attributes, function (a) { s.setAttribute(a.name, a.value); });
                    if (old.src) {
                        s.async = false;
                        s.onload = s.onerror = function () { resolve(); };
                        document.body.appendChild(s);
                    } else {
                        s.textContent = old.textContent;
                        document.body.appendChild(s);
                        resolve();
                    }
                });
            });
        }, Promise.resolve());
    }

    function swapDocument(html, url) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var scripts = Array.prototype.slice.call(doc.querySelectorAll('script'));
        scripts.forEach(function (s) { if (s.parentNode) s.parentNode.removeChild(s); });

        try { history.replaceState(null, '', url); } catch (e) {}

        Array.prototype.slice.call(document.querySelectorAll('link[rel="stylesheet"], style'))
            .forEach(function (n) { n.parentNode.removeChild(n); });

        Array.prototype.forEach.call(doc.documentElement.attributes, function (a) {
            document.documentElement.setAttribute(a.name, a.value);
        });
        document.title = doc.title || document.title;

        var pending = [];
        Array.prototype.slice.call(doc.head.children).forEach(function (node) {
            var tag = node.tagName;
            if (tag === 'TITLE') return;
            if (tag === 'LINK' && (node.getAttribute('rel') || '').toLowerCase() === 'stylesheet') {
                pending.push(loadStylesheet(node));
                return;
            }
            if (tag === 'META' && node.getAttribute('name')) {
                var same = document.head.querySelector('meta[name="' + node.getAttribute('name') + '"]');
                if (same) same.parentNode.removeChild(same);
            }
            document.head.appendChild(document.importNode(node, true));
        });

        Array.prototype.slice.call(document.body.attributes).forEach(function (a) {
            document.body.removeAttribute(a.name);
        });
        Array.prototype.forEach.call(doc.body.attributes, function (a) {
            document.body.setAttribute(a.name, a.value);
        });

        return Promise.all(pending).then(function () {
            document.body.innerHTML = doc.body.innerHTML;
            window.scrollTo(0, 0);
            return runScripts(scripts);
        }).then(function () {
            document.dispatchEvent(new Event('DOMContentLoaded', { bubbles: true }));
            window.dispatchEvent(new Event('load'));
        });
    }

    var RETRY_WAITS = [1500, 3000, 6000];

    function pause(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    function fetchPage(opts, attempt) {
        return fetch(opts.url, {
            method: opts.method || 'GET',
            body: opts.body || undefined,
            credentials: 'same-origin',
            redirect: 'follow'
        }).then(function (res) {
            var busy = res.status >= 500 || res.status === 429 || res.status === 408;
            if (!busy || attempt >= RETRY_WAITS.length) return res;
            throw new Error('busy');
        }).catch(function (err) {
            if (attempt >= RETRY_WAITS.length) throw err;
            if (typeof opts.onRetry === 'function') opts.onRetry(attempt + 1);
            return pause(RETRY_WAITS[attempt] + Math.floor(Math.random() * 800)).then(function () {
                return fetchPage(opts, attempt + 1);
            });
        });
    }

    window.sppLaunchExam = function (opts) {
        opts = opts || {};
        var url = opts.url;
        var html = null;
        var finalUrl = url;
        return enterFullscreen().then(function () {
            return fetchPage(opts, 0);
        }).then(function (res) {
            finalUrl = res.url || url;
            if (!res.ok && (res.status >= 500 || res.status === 429 || res.status === 408) && typeof opts.onBusy === 'function') {
                opts.onBusy();
                return null;
            }
            if (opts.expect && finalUrl.indexOf(opts.expect) === -1) {
                window.location.href = finalUrl;
                return null;
            }
            return res.text();
        }).then(function (text) {
            if (text === null) return;
            html = text;
            return swapDocument(text, finalUrl);
        }).catch(function () {
            if (html !== null) {
                document.open();
                document.write(html);
                document.close();
                return;
            }
            if (typeof opts.onBusy === 'function') opts.onBusy();
            else if (typeof opts.fallback === 'function') opts.fallback();
            else window.location.href = url;
        });
    };
}());
