(function () {
    var form = document.getElementById('readinessForm');
    var button = document.getElementById('ready_to_begin_button');
    if (!form || !button || typeof window.sppLaunchExam !== 'function') return;
    var launching = false;
    form.addEventListener('submit', function (e) {
        if (launching) { e.preventDefault(); return; }
        if (!form.checkValidity()) return;
        e.preventDefault();
        launching = true;
        button.disabled = true;
        button.innerHTML = '<span class="ins-spin" aria-hidden="true"></span>Starting...';
        window.sppLaunchExam({
            url: form.getAttribute('action'),
            method: 'POST',
            body: new FormData(form),
            expect: '/start-test/',
            onRetry: function () {
                button.innerHTML = '<span class="ins-spin" aria-hidden="true"></span>Server is busy, trying again...';
            },
            onBusy: function () {
                launching = false;
                button.disabled = false;
                button.textContent = 'I am ready to begin';
                var note = document.getElementById('readinessBusy');
                if (!note) {
                    note = document.createElement('p');
                    note.id = 'readinessBusy';
                    note.className = 'ins-busy';
                    note.setAttribute('role', 'alert');
                    form.appendChild(note);
                }
                note.textContent = 'The server is busy right now. Please press "I am ready to begin" again.';
            }
        });
    });
}());
