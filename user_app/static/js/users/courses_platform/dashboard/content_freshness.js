/* The dashboard is a snapshot of the database. While the tab is in use this
   re-checks a tiny fingerprint of the course's content; when it changes, the
   content area is fetched again and swapped in place. Nothing is announced:
   a card that was hidden simply is not there any more, one that was added
   simply is. */
(function () {
  "use strict";

  var cfg = document.getElementById("contentFreshness");
  if (!cfg) return;

  var known = cfg.dataset.version || "";
  var url = cfg.dataset.checkUrl || "";
  if (!known || !url) return;

  var BEAT_MS = 60000;          // while the tab is on screen
  var MIN_GAP_MS = 15000;       // never hammer the endpoint
  var lastCheck = 0;
  var refreshing = false;
  var timer = null;

  function stats() {
    var card = document.querySelector(".stat-card");
    return card ? card.parentElement : null;
  }

  function refresh() {
    if (refreshing) return;
    refreshing = true;
    fetch(window.location.href, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (!html) return;
        var doc = new DOMParser().parseFromString(html, "text/html");
        var freshArea = doc.getElementById("content-area");
        var area = document.getElementById("content-area");
        if (freshArea && area) area.innerHTML = freshArea.innerHTML;

        var freshStats = doc.querySelector(".stat-card");
        var mine = stats();
        if (freshStats && mine) mine.innerHTML = freshStats.parentElement.innerHTML;

        var freshCfg = doc.getElementById("contentFreshness");
        if (freshCfg && freshCfg.dataset.version) known = freshCfg.dataset.version;

        if (typeof window.sppDashboardRebind === "function") window.sppDashboardRebind();
      })
      .catch(function () { /* next check will try again */ })
      .then(function () { refreshing = false; });
  }

  function check() {
    if (document.hidden) return;
    var now = Date.now();
    if (now - lastCheck < MIN_GAP_MS) return;
    lastCheck = now;
    fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && data.version && data.version !== known) refresh();
      })
      .catch(function () { /* offline or a hiccup: try again next time */ });
  }

  function startBeat() {
    if (timer) return;
    timer = setInterval(check, BEAT_MS);
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      if (timer) { clearInterval(timer); timer = null; }
    } else {
      check();
      startBeat();
    }
  });
  window.addEventListener("focus", check);
  startBeat();
})();
