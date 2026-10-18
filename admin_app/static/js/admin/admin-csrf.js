(function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    var token = meta ? meta.getAttribute('content') : '';
    if (!token) {
        console.warn('[CSRF] no token meta tag found on this page');
        return;
    }
    window.CSRF_TOKEN = token;

    function isSameOrigin(url) {
        if (!url) return true;
        if (/^https?:\/\//i.test(url)) return url.indexOf(window.location.origin + '/') === 0 || url === window.location.origin;
        if (url.indexOf('//') === 0) return url.indexOf('//' + window.location.host) === 0;
        return true;
    }

    var origFetch = window.fetch;
    if (origFetch) {
        window.fetch = function (input, init) {
            var url = typeof input === 'string' ? input : (input && input.url) || '';
            var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
            if (isSameOrigin(url) && method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
                init = init || {};
                var headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined) || {});
                if (!headers.has('X-CSRFToken')) headers.set('X-CSRFToken', token);
                init.headers = headers;
            }
            return origFetch.call(this, input, init);
        };
    }

    var origOpen = XMLHttpRequest.prototype.open;
    var origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
        this._csrfMethod = (method || 'GET').toUpperCase();
        this._csrfUrl = url || '';
        return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
        if (isSameOrigin(this._csrfUrl) && this._csrfMethod &&
            this._csrfMethod !== 'GET' && this._csrfMethod !== 'HEAD' && this._csrfMethod !== 'OPTIONS') {
            try { this.setRequestHeader('X-CSRFToken', token); } catch (e) {}
        }
        return origSend.apply(this, arguments);
    };

    function protectForm(form) {
        if (!form || !form.tagName || form.tagName !== 'FORM') return;
        if ((form.getAttribute('method') || 'get').toLowerCase() !== 'post') return;
        if (form.querySelector('input[name="_csrf_token"]')) return;
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = '_csrf_token';
        input.value = token;
        form.appendChild(input);
    }

    function protectAllForms() {
        document.querySelectorAll('form').forEach(protectForm);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', protectAllForms);
    } else {
        protectAllForms();
    }
    document.addEventListener('submit', function (e) {
        protectForm(e.target);
    }, true);
})();
