const PAGE_DATA = document.getElementById('pageData').dataset;

    const sectionId = PAGE_DATA.sectionId;
    const testKey = PAGE_DATA.testKey;
    const courseCode = PAGE_DATA.courseCode;
    const uniqueCode = PAGE_DATA.uniqueCode;
    const userEmail = PAGE_DATA.email;
    const initialDurationSeconds = PAGE_DATA.durationSeconds;
    const sectionsData = JSON.parse(PAGE_DATA.sectionsData);

document.addEventListener("DOMContentLoaded", function () {
    testManager.init(testKey, courseCode, uniqueCode);

    const proctor = new ProctoringSystem(sectionId, testKey, userEmail, courseCode, uniqueCode);

    window.addEventListener('message', function (event) {
        const data = event.data;
        if (event.origin !== window.location.origin || !data || data.type !== 'tcs-coding-violation') return;
        if (typeof data.violationType !== 'string' || !/^(context_menu|clipboard_(copy|paste|cut))$/.test(data.violationType)) return;
        proctor.sendViolation(data.violationType, String(data.details || '').slice(0, 200));
    });
});

(function () {
    var el = document.getElementById('pageData');
    if (!el || !el.dataset.testKey) return;
    var key = el.dataset.testKey;
    var hbUrl = '/test-heartbeat/' + encodeURIComponent(key);
    var byeUrl = '/release-test-window/' + encodeURIComponent(key);
    var finished = false;
    var lastKey = { chord: 'none', at: 0 };
    window.addEventListener('keydown', function (e) {
        var parts = [];
        if (e.metaKey) parts.push('cmd');
        if (e.ctrlKey) parts.push('ctrl');
        if (e.altKey) parts.push('alt');
        if (e.shiftKey) parts.push('shift');
        parts.push((e.key || '').toLowerCase());
        lastKey = { chord: parts.join('+'), at: Date.now() };
    }, true);

    function exitInfo() {
        return JSON.stringify({
            reason: 'window_closed',
            last_key: lastKey.chord,
            key_age_ms: lastKey.at ? Date.now() - lastKey.at : -1,
            fullscreen: !!document.fullscreenElement,
            opener: !!(window.opener && !window.opener.closed),
            visibility: document.visibilityState,
            agent: navigator.userAgent
        });
    }

    function beat() {
        if (finished) return;
        fetch(hbUrl, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) {
                if (r.status === 403) finished = true;
            })
            .catch(function () {});
    }
    beat();
    setInterval(beat, 15000);

    window.markTestFinished = function () { finished = true; };

    function release() {
        if (finished) return;
        finished = true;
        try {
            if (!navigator.sendBeacon(byeUrl, new Blob([exitInfo()], { type: 'text/plain' }))) {
                throw new Error('beacon refused');
            }
        } catch (e) {
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('POST', byeUrl, false);
                xhr.send(exitInfo());
            } catch (err) {}
        }
    }

    window.addEventListener('pagehide', function (e) { if (!e.persisted) release(); });
    window.addEventListener('unload', release);
})();
