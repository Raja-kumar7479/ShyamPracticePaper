(function () {
    var exit = document.exitFullscreen || document.webkitExitFullscreen || document.msExitFullscreen;
    if (exit && (document.fullscreenElement || document.webkitFullscreenElement)) {
        try { exit.call(document); } catch (e) {}
    }
})();

let rating = 0;
        function rate(n) { rating = n; document.querySelectorAll('.star').forEach((s, i) => s.classList.toggle('active', i < n)); }

        async function submitFeedback() {
            if (rating === 0) return alert("Please select a rating.");

            const fd = new FormData();
            fd.append('rating', rating);
            fd.append('comments', document.getElementById('comments').value);
            fd.append('test_key', document.getElementById('testKey').value);
            fd.append('round_name', document.getElementById('roundName').value);
            fd.append('course_code', document.getElementById('courseCode').value);
            fd.append('unique_code', document.getElementById('uniqueCode').value);

            try {
                const res = await fetch('/submit-feedback', {
                    method: 'POST',
                    body: fd,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                if (res.status === 401) {
                    let loginUrl = '/user_login';
                    try { const b = await res.clone().json(); if (b && b.login_url) loginUrl = b.login_url; } catch (e) {}
                    window.location.replace(loginUrl);
                    return;
                }
                const data = await res.json();
                if (data.redirect) {
                    window.location.replace(data.redirect);
                }
            } catch(e) {
                alert("Error submitting feedback");
            }
        }
