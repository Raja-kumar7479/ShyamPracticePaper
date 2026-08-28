(function () {
    var cfg = document.getElementById('commTabGuard');
    if (!cfg) return;

    var testKey = cfg.dataset.testKey;
    var busyUrl = cfg.dataset.busyUrl;
    if (!testKey) return;

    var tabId;
    try {
        tabId = sessionStorage.getItem('sapmTabId');
        if (!tabId) {
            tabId = 'tab_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
            sessionStorage.setItem('sapmTabId', tabId);
        }
    } catch (e) {
        return;
    }

    var blocked = false;

    function claim() {
        if (blocked) return;
        fetch('/api/comm-claim/' + encodeURIComponent(testKey), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tab_id: tabId })
        })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d && d.ok === false) {
                    blocked = true;
                    if (window.opener && !window.opener.closed) {
                        try {
                            if (busyUrl) window.opener.location.replace(busyUrl);
                            window.opener.focus();
                        } catch (err) {}
                        window.close();
                        return;
                    }
                    if (busyUrl) {
                        window.sppExamLeaving = true;
                        window.location.replace(busyUrl);
                    } else {
                        document.body.innerHTML =
                            '<div style="padding:60px;text-align:center;font-family:Segoe UI,sans-serif">' +
                            '<h2>Assessment already open</h2><p>' + (d.message || '') + '</p></div>';
                    }
                }
            })
            .catch(function () {});
    }

    claim();
    setInterval(claim, 10000);

    window.addEventListener('pagehide', function () {
        try {
            navigator.sendBeacon(
                '/api/comm-tab-release/' + encodeURIComponent(testKey),
                JSON.stringify({ tab_id: tabId })
            );
        } catch (e) {}
    });
})();
