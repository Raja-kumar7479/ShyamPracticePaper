(function () {
    var cfg = document.getElementById('examWindowGuard');
    if (!cfg) return;

    var testKey = cfg.dataset.testKey;
    var exitUrl = cfg.dataset.exitUrl || '/';
    if (!testKey) return;

    var tabId;
    try {
        tabId = sessionStorage.getItem('sppExamTabId');
        if (!tabId) {
            tabId = 'w_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
            sessionStorage.setItem('sppExamTabId', tabId);
        }
    } catch (e) {
        return;
    }

    var blocked = false;
    var claimed = false;
    var payload = JSON.stringify({ test_key: testKey, tab_id: tabId });

    function claim() {
        if (blocked) return;
        // The first claim of this window declares itself fresh: a newly
        // opened window takes the test over from a dead holder instead of
        // being bounced. Heartbeats are never fresh, so a window that has
        // lost the claim to a newer one is closed by its own next beat.
        fetch('/api/exam-window/claim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: claimed ? payload
                          : JSON.stringify({ test_key: testKey, tab_id: tabId, fresh: true })
        })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d && d.ok !== false) claimed = true;
                if (d && d.ok === false) {
                    blocked = true;
                    if (window.opener && !window.opener.closed) {
                        try { window.opener.focus(); } catch (err) {}
                        window.close();
                        setTimeout(function () { window.location.replace(exitUrl); }, 400);
                        return;
                    }
                    window.location.replace(exitUrl);
                }
            })
            .catch(function () {});
    }

    claim();
    setInterval(claim, 8000);

    window.addEventListener('pagehide', function () {
        if (blocked) return;
        try {
            navigator.sendBeacon('/api/exam-window/release',
                new Blob([payload], { type: 'application/json' }));
        } catch (e) {}
    });
})();
