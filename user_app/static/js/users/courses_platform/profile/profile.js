document.addEventListener('DOMContentLoaded', () => {
    window.switchTab = function(tabId) {
        document.querySelectorAll('.menu-item').forEach(btn => {
            btn.classList.remove('active');
        });

        document.querySelectorAll('.tab-section').forEach(section => {
            section.classList.remove('active');
        });

        const activeBtn = document.querySelector(`button[onclick="switchTab('${tabId}')"]`);
        if (activeBtn) activeBtn.classList.add('active');

        const activeSection = document.getElementById(tabId);
        if (activeSection) activeSection.classList.add('active');

        if (history.pushState) {
            history.pushState(null, null, `#${tabId}`);
        } else {
            location.hash = tabId;
        }
    };

    const hash = window.location.hash.replace('#', '');
    if (hash && document.getElementById(hash)) {
        switchTab(hash);
    }

    const toggleButtons = document.querySelectorAll('.toggle-password');
    toggleButtons.forEach(button => {
        button.addEventListener('click', function() {
            const input = this.previousElementSibling;
            const icon = this.querySelector('i');

            if (input.type === 'password') {
                input.type = 'text';
                icon.classList.remove('fa-eye');
                icon.classList.add('fa-eye-slash');
            } else {
                input.type = 'password';
                icon.classList.remove('fa-eye-slash');
                icon.classList.add('fa-eye');
            }
        });
    });

    const usernameInput = document.getElementById('usernameInput');
    const usernameFeedback = document.getElementById('usernameFeedback');
    const usernameSubmitBtn = document.getElementById('usernameSubmitBtn');
    let typingTimer;

    if (usernameInput) {
        usernameInput.addEventListener('input', () => {
            clearTimeout(typingTimer);
            usernameFeedback.textContent = '';
            usernameSubmitBtn.disabled = true;

            typingTimer = setTimeout(async () => {
                const username = usernameInput.value.trim();
                if (username.length < 3) return;

                try {
                    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
                    const response = await fetch('/api/profile/check-username', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfMeta ? csrfMeta.getAttribute('content') : ''
                        },
                        body: JSON.stringify({username})
                    });
                    const data = await response.json();

                    if (data.status === 'available') {
                        usernameFeedback.style.color = '#10b981';
                        usernameFeedback.textContent = '✓ Username is available';
                        usernameSubmitBtn.disabled = false;
                    } else if (data.status === 'taken') {
                        usernameFeedback.style.color = '#ef4444';
                        usernameFeedback.textContent = '✗ Username is already taken';
                    }
                } catch (e) {
                    console.error("Check error", e);
                }
            }, 500);
        });
    }

    async function syncLastActive() {
        const activeTimeEl = document.getElementById('lastActiveTime');
        if (!activeTimeEl) return;

        try {
            const response = await fetch('/api/profile/last-active');
            const data = await response.json();

            if (data.last_active) {
                activeTimeEl.setAttribute('data-time', data.last_active);
                updateRelativeTime(data.last_active);
            }
        } catch (e) {
            console.error("Sync error", e);
        }
    }

    function updateRelativeTime(dateString) {
        const activeTimeEl = document.getElementById('lastActiveTime');
        if (!activeTimeEl || !dateString) return;

        const date = new Date(dateString.replace(/-/g, '/'));
        const now = new Date();
        const seconds = Math.floor((now - date) / 1000);

        let text = "Just now";
        if (seconds > 60) {
            const minutes = Math.floor(seconds / 60);
            text = minutes + " min" + (minutes > 1 ? "s" : "") + " ago";
        }
        if (seconds > 3600) {
            const hours = Math.floor(seconds / 3600);
            text = hours + " hour" + (hours > 1 ? "s" : "") + " ago";
        }

        activeTimeEl.textContent = text;
    }

    const initialTime = document.getElementById('lastActiveTime')?.getAttribute('data-time');
    if (initialTime) updateRelativeTime(initialTime);

    setInterval(syncLastActive, 30000);

    const toasts = document.querySelectorAll('.flash-toast');
    toasts.forEach(toast => {
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(50px)';
            setTimeout(() => {
                if (toast.parentElement) toast.remove();
            }, 400);
        }, 4000);

        const btn = toast.querySelector('.toast-close');
        if(btn) {
            btn.addEventListener('click', () => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(50px)';
                setTimeout(() => {
                    if (toast.parentElement) toast.remove();
                }, 400);
            });
        }
    });

    const confirmModalEl = document.getElementById('confirmUpdateModal');
    let confirmModal;
    if (confirmModalEl) {
        confirmModal = new bootstrap.Modal(confirmModalEl);
    }

    const confirmSubmitBtn = document.getElementById('confirmSubmitBtn');
    let pendingForm = null;

    const changePasswordForm = document.getElementById('changePasswordForm');
    if (changePasswordForm) {
        changePasswordForm.addEventListener('submit', function(e) {
            e.preventDefault();
            pendingForm = this;
            if (confirmModal) confirmModal.show();
        });
    }

    const setPasswordForm = document.getElementById('setPasswordForm');
    if (setPasswordForm) {
        setPasswordForm.addEventListener('submit', function(e) {
            e.preventDefault();
            pendingForm = this;
            if (confirmModal) confirmModal.show();
        });
    }

    if (confirmSubmitBtn) {
        confirmSubmitBtn.addEventListener('click', function() {
            if (pendingForm) {
                pendingForm.submit();
            }
            if (confirmModal) confirmModal.hide();
        });
    }
});