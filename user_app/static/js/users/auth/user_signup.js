const usernameInput = document.getElementById('username');
    const feedback = document.getElementById('usernameFeedback');
    const btn = document.getElementById('usernameSubmitBtn');
    let timer;

    if (usernameInput) {
        usernameInput.addEventListener('input', function() {
            clearTimeout(timer);
            const val = this.value.trim();

            if (val.length < 3) {
                feedback.style.display = 'none';
                btn.disabled = false;
                return;
            }

            btn.disabled = true;
            feedback.style.display = 'block';
            feedback.style.color = '#6c757d';
            feedback.innerText = 'Checking...';

            timer = setTimeout(() => {
                fetch('/api/auth/check-username', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: val})
                })
                .then(r => r.json())
                .then(data => {
                    if(data.status === 'available') {
                        feedback.style.color = '#198754';
                        feedback.innerText = '✓ ' + data.message;
                        btn.disabled = false;
                    } else if (data.status === 'taken') {
                        feedback.style.color = '#dc3545';
                        feedback.innerText = '✗ ' + data.message;
                        btn.disabled = true;
                    } else {
                        feedback.style.color = '#dc3545';
                        feedback.innerText = data.message;
                        btn.disabled = true;
                    }
                });
            }, 500);
        });
    }

    const passwordInput = document.getElementById("password");
    const toggle = document.getElementById("toggle-password");
    if (passwordInput && toggle) {
        toggle.addEventListener("click", () => {
            const type = passwordInput.type === "password" ? "text" : "password";
            passwordInput.type = type;
            toggle.querySelector("i").className = type === "password" ? "fas fa-eye" : "fas fa-eye-slash";
            toggle.setAttribute("aria-label", type === "password" ? "Show password" : "Hide password");
        });
    }
