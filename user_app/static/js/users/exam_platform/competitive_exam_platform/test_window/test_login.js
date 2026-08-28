document.addEventListener('DOMContentLoaded', function() {
            function generateRandomString(length) {
                const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
                let result = '';
                const charactersLength = characters.length;
                for (let i = 0; i < length; i++) {
                    result += characters.charAt(Math.floor(Math.random() * charactersLength));
                }
                return result;
            }
            document.getElementById('fake_login_id').value = generateRandomString(8);
            document.getElementById('fake_test_key').value = generateRandomString(6);
        });

        (function () {
            const form = document.getElementById('test-login-form');
            if (!form) {
                console.error('TEST LOGIN: form #test-login-form not found.');
                return;
            }

            const signInButton = form.querySelector('.sign-in-box');
            const flashContainer = document.getElementById('flash-container');

            function showMessage(message, type) {
                console.log('TEST LOGIN: ' + (type || 'info') + ' - ' + message);
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
                setTimeout(function () { toast.remove(); }, 5000);
            }

            function resetButton() {
                if (!signInButton) return;
                signInButton.disabled = false;
                signInButton.textContent = 'Sign In';
            }

            form.addEventListener('submit', async function (event) {
                event.preventDefault();
                console.log('TEST LOGIN 1: submit intercepted');

                if (signInButton) {
                    signInButton.disabled = true;
                    signInButton.textContent = 'Signing In...';
                }
                if (flashContainer) flashContainer.innerHTML = '';

                try {
                    console.log('TEST LOGIN 2: posting to ' + form.action);
                    const response = await fetch(form.action, {
                        method: 'POST',
                        body: new FormData(form),
                        headers: { 'X-Requested-With': 'XMLHttpRequest' },
                        credentials: 'same-origin'
                    });
                    console.log('TEST LOGIN 3: status ' + response.status);

                    const contentType = response.headers.get('content-type') || '';
                    if (!contentType.includes('application/json')) {
                        console.error('TEST LOGIN: expected JSON, got ' + contentType);
                        showMessage('Your session may have expired. Please reload the page and log in again.');
                        resetButton();
                        return;
                    }

                    const result = await response.json();
                    console.log('TEST LOGIN 4: parsed response', result);

                    if (!response.ok || !result.success) {
                        showMessage(result.message || 'Could not start the test. Please try again.');
                        resetButton();
                        return;
                    }

                    console.log('TEST LOGIN 5: opening the secure exam window');
                    const examWindow = window.open(result.instructionUrl, 'sppExamWindow');

                    if (!examWindow) {
                        showMessage('Your browser blocked the exam window. Please allow pop-ups for this site and sign in again.');
                        resetButton();
                        return;
                    }

                    try { examWindow.moveTo(0, 0); examWindow.resizeTo(screen.availWidth, screen.availHeight); } catch (e) {}
                    examWindow.focus();

                    document.body.classList.add('tl-handedoff');
                    const holder = document.getElementById('loginCard') || document.body;
                    holder.innerHTML =
                        '<div class="tl-handoff">' +
                        '<h3>Your assessment is open in the secure exam window</h3>' +
                        '<p>Please continue there. Do not close that window until you submit.</p>' +
                        '</div>';

                    const watcher = setInterval(function () {
                        if (examWindow.closed) {
                            clearInterval(watcher);
                            window.location.reload();
                        }
                    }, 1500);

                } catch (error) {
                    console.error('TEST LOGIN FAILED:', error);
                    showMessage('An unexpected error occurred. Please check your connection and try again.');
                    resetButton();
                }
            });
        })();
