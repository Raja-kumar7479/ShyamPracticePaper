document.addEventListener('DOMContentLoaded', function () {
        const toggle = document.getElementById('toggle-password');
        const input = document.getElementById('password');
        if (toggle && input) {
            toggle.addEventListener('click', () => {
                const show = input.type === 'password';
                input.type = show ? 'text' : 'password';
                toggle.querySelector('i').className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
                toggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
            });
        }
    });
