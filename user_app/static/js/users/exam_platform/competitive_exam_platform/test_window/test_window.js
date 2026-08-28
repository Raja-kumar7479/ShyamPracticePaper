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
});

(function () {
    var el = document.getElementById('pageData');
    if (!el || !el.dataset.testKey) return;
    var key = el.dataset.testKey;
    var hbUrl = '/test-heartbeat/' + encodeURIComponent(key);
    var byeUrl = '/release-test-window/' + encodeURIComponent(key);
    var finished = false;

    function beat() {
        if (finished) return;
        fetch(hbUrl, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) {
                if (r.status === 403) finished = true;
            })
            .catch(function () {});
    }
    beat();
    setInterval(beat, 10000);

    window.markTestFinished = function () { finished = true; };

    function release() {
        if (finished) return;
        finished = true;
        try {
            if (!navigator.sendBeacon(byeUrl, new Blob([], { type: 'text/plain' }))) {
                throw new Error('beacon refused');
            }
        } catch (e) {
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('POST', byeUrl, false);
                xhr.send();
            } catch (err) {}
        }
    }

    window.addEventListener('pagehide', release);
    window.addEventListener('beforeunload', release);
    window.addEventListener('unload', release);
})();
