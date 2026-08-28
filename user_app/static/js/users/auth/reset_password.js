(function () {
    function bindToggle(toggle) {
        var targetId = toggle.getAttribute('data-target');
        var input = document.getElementById(targetId);
        if (!input) return;

        function flip() {
            var show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            var icon = toggle.querySelector('i');
            if (icon) {
                icon.className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
            }
            toggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
            toggle.setAttribute('aria-pressed', show ? 'true' : 'false');
        }

        toggle.addEventListener('click', function (e) {
            e.preventDefault();
            flip();
        });

        toggle.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
                e.preventDefault();
                flip();
            }
        });
    }

    function init() {
        var toggles = document.querySelectorAll('.toggle-password[data-target]');
        for (var i = 0; i < toggles.length; i++) {
            bindToggle(toggles[i]);
        }

        var pwd = document.getElementById('new_password');
        var confirm = document.getElementById('confirm_password');
        if (!pwd || !confirm) return;

        function checkMatch() {
            if (confirm.value && pwd.value !== confirm.value) {
                confirm.setCustomValidity('Passwords do not match.');
            } else {
                confirm.setCustomValidity('');
            }
        }

        pwd.addEventListener('input', checkMatch);
        confirm.addEventListener('input', checkMatch);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
