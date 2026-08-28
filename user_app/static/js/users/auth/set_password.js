document.getElementById("new_password").addEventListener("input", function () {
        const value = this.value;
        document.getElementById("upper-check").style.color = /[A-Z]/.test(value) ? "green" : "red";
        document.getElementById("number-check").style.color = /[0-9]/.test(value) ? "green" : "red";
        document.getElementById("special-check").style.color = /[^A-Za-z0-9]/.test(value) ? "green" : "red";
    });

    function togglePassword(id, toggleId) {
        const input = document.getElementById(id);
        const toggle = document.getElementById(toggleId);
        toggle.addEventListener("click", function () {
            const type = input.type === "password" ? "text" : "password";
            input.type = type;
            this.querySelector("i").className = type === "password" ? "fas fa-eye" : "fas fa-eye-slash";
            this.setAttribute("aria-label", type === "password" ? "Show password" : "Hide password");
        });
    }

    togglePassword("new_password", "toggle-password-new");
    togglePassword("confirm_password", "toggle-password-confirm");
