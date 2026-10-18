function togglePassword(id, el) {
    const input = document.getElementById(id || 'password');
    const toggle = el || document.getElementById('toggle-password');
    if (!input || !toggle) return;
    const icon = toggle.querySelector('i');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    if (icon) icon.className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
    toggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
}
