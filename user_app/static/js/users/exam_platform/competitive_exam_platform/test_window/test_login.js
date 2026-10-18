document.addEventListener('DOMContentLoaded', function () {
    function randomText(length) {
        const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        let result = '';
        for (let i = 0; i < length; i++) {
            result += characters.charAt(Math.floor(Math.random() * characters.length));
        }
        return result;
    }
    const loginId = document.getElementById('fake_login_id');
    const key = document.getElementById('fake_test_key');
    if (loginId) loginId.value = randomText(8);
    if (key) key.value = randomText(6);
});

(function () {
    const form = document.getElementById('test-login-form');
    if (!form) return;

    const signInButton = form.querySelector('.sign-in-box');
    const flashContainer = document.getElementById('flash-container');
    const RETRY_WAITS = [1500, 3000, 6000];
    let signing = false;

    function pause(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    function showMessage(message, type) {
        let stack = document.getElementById('tlToasts');
        if (!stack) {
            stack = document.createElement('div');
            stack.id = 'tlToasts';
            stack.className = 'tl-toasts';
            document.body.appendChild(stack);
        }
        const toast = document.createElement('div');
        toast.className = 'tl-toast' + (type === 'success' ? ' tl-toast--ok' : '');
        toast.setAttribute('role', 'alert');

        const icon = document.createElement('i');
        icon.className = 'fas ' + (type === 'success' ? 'fa-circle-check' : 'fa-circle-exclamation');
        const text = document.createElement('span');
        text.textContent = message;
        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'tl-toast__close';
        close.setAttribute('aria-label', 'Close');
        close.innerHTML = '&times;';
        close.addEventListener('click', function () { toast.remove(); });

        toast.appendChild(icon);
        toast.appendChild(text);
        toast.appendChild(close);
        stack.appendChild(toast);
        setTimeout(function () { toast.remove(); }, 3000);
    }

    function setBusy(label) {
        if (!signInButton) return;
        signInButton.disabled = true;
        signInButton.classList.add('is-loading');
        signInButton.innerHTML = '';
        const spinner = document.createElement('span');
        spinner.className = 'tl-login-spin';
        spinner.setAttribute('aria-hidden', 'true');
        signInButton.appendChild(spinner);
        signInButton.appendChild(document.createTextNode(label));
    }

    function resetButton() {
        signing = false;
        if (!signInButton) return;
        signInButton.disabled = false;
        signInButton.classList.remove('is-loading');
        signInButton.textContent = 'Sign In';
    }

    function openExamWindow() {
        let examWindow = null;
        try { examWindow = window.open('', 'sppExamWindow'); } catch (e) { examWindow = null; }
        if (!examWindow) return null;
        let blank = false;
        try { blank = examWindow.location.href === 'about:blank'; } catch (e) { blank = false; }
        if (blank) {
            try {
                examWindow.document.write(
                    '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Opening your test</title><style>' +
                    'body{margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;' +
                    'font:600 17px/1.5 "Segoe UI",system-ui,sans-serif;color:#5c1a15;background:#fdf8f3}' +
                    '.s{width:46px;height:46px;border:4px solid #ead9d2;border-top-color:#992c25;border-radius:50%;' +
                    'animation:r .8s linear infinite;margin-bottom:18px}@keyframes r{to{transform:rotate(360deg)}}' +
                    'small{font-weight:400;color:#7a5a52;margin-top:6px}</style></head><body>' +
                    '<div class="s"></div><div>Opening your test</div><small>Please wait. Do not close this window.</small>' +
                    '</body></html>');
                examWindow.document.close();
            } catch (e) {}
        }
        try { examWindow.moveTo(0, 0); examWindow.resizeTo(screen.availWidth, screen.availHeight); } catch (e) {}
        return { win: examWindow, blank: blank };
    }

    async function signIn() {
        for (let attempt = 0; ; attempt++) {
            let response = null;
            try {
                response = await fetch(form.action, {
                    method: 'POST',
                    body: new FormData(form),
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    credentials: 'same-origin'
                });
            } catch (error) {
                response = null;
            }
            const busy = !response || response.status >= 500 || response.status === 429 || response.status === 408;
            if (busy && attempt < RETRY_WAITS.length) {
                setBusy('Server is busy, trying again...');
                await pause(RETRY_WAITS[attempt] + Math.floor(Math.random() * 800));
                setBusy('Signing In...');
                continue;
            }
            if (!response) {
                return { ok: false, message: 'Could not reach the server. Please check your connection and try again.' };
            }
            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                return { ok: false, message: busy
                    ? 'The server is busy right now. Please try again in a moment.'
                    : 'Your session may have expired. Please reload the page and log in again.' };
            }
            const result = await response.json();
            if (!response.ok || !result.success) {
                return { ok: false, message: result.message || 'Could not start the test. Please try again.' };
            }
            return { ok: true, url: result.instructionUrl };
        }
    }

    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        if (signing) return;
        signing = true;
        setBusy('Signing In...');
        if (flashContainer) flashContainer.innerHTML = '';

        const opened = openExamWindow();
        if (!opened) {
            showMessage('Your browser blocked the exam window. Please allow pop-ups for this site and sign in again.');
            resetButton();
            return;
        }

        let outcome;
        try {
            outcome = await signIn();
        } catch (error) {
            outcome = { ok: false, message: 'An unexpected error occurred. Please check your connection and try again.' };
        }

        if (!outcome.ok) {
            if (opened.blank) {
                try { opened.win.close(); } catch (e) {}
            }
            showMessage(outcome.message);
            resetButton();
            return;
        }

        try {
            opened.win.location.replace(outcome.url);
            opened.win.focus();
        } catch (e) {
            const again = window.open(outcome.url, 'sppExamWindow');
            if (!again) {
                showMessage('Your browser blocked the exam window. Please allow pop-ups for this site and sign in again.');
                resetButton();
                return;
            }
            opened.win = again;
        }

        document.body.classList.add('tl-handedoff');
        const holder = document.getElementById('loginCard') || document.body;
        holder.innerHTML =
            '<div class="tl-handoff">' +
            '<h3>Your assessment is open in the secure exam window</h3>' +
            '<p>Please continue there. Do not close that window until you submit.</p>' +
            '</div>';

        const watcher = setInterval(function () {
            if (opened.win.closed) {
                clearInterval(watcher);
                window.location.reload();
            }
        }, 1500);
    });
})();
