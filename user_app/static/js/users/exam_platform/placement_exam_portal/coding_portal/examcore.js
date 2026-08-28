(function (window) {
  "use strict";

  const CJ = window.CJ;
  let activeTimer = null;


  function wireTheme(root, signal) {
    const btn = CJ.$("#btn-theme", root);
    if (!btn) return;
    function apply(theme) {
      if (theme === "dark") document.documentElement.dataset.theme = "dark";
      else delete document.documentElement.dataset.theme;
      btn.textContent = theme === "dark" ? "☀" : "🌙";
    }
    let theme = "light";
    try { theme = localStorage.getItem("cj-theme") || "light"; } catch (e) {}
    apply(theme);
    btn.addEventListener("click", function () {
      theme = theme === "dark" ? "light" : "dark";
      try { localStorage.setItem("cj-theme", theme); } catch (e) {}
      apply(theme);
    }, { signal: signal });
  }

  function wireFullscreen(root, signal) {
    const btn = CJ.$("#btn-fullscreen", root);
    if (!btn) return;

    const el = document.documentElement;
    const request = el.requestFullscreen || el.webkitRequestFullscreen;
    if (!request) { btn.style.display = "none"; return; }

    const inIcon = btn.querySelector(".fs-in");
    const outIcon = btn.querySelector(".fs-out");

    function isFull() {
      return !!(document.fullscreenElement || document.webkitFullscreenElement);
    }

    function paint() {
      const on = isFull();
      if (inIcon) inIcon.style.display = on ? "none" : "";
      if (outIcon) outIcon.style.display = on ? "" : "none";
      btn.title = on ? "Leave full window (Esc)" : "Full window";
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.classList.toggle("is-on", on);
    }

    btn.addEventListener("click", function () {
      if (isFull()) {
        (document.exitFullscreen || document.webkitExitFullscreen).call(document);
        return;
      }
      const out = request.call(el);
      if (out && typeof out.catch === "function") out.catch(function () { paint(); });
    }, { signal: signal });

    // Esc and F11 leave fullscreen without touching the button, so the icon
    // follows the event rather than the click.
    document.addEventListener("fullscreenchange", paint, { signal: signal });
    document.addEventListener("webkitfullscreenchange", paint, { signal: signal });
    paint();
  }

  function wireLeaveGuard(cfg, signal) {
    // The browser "Leave site? Changes may not be saved" prompt was removed:
    // it fired whenever the candidate exited full screen or moved away, sitting
    // on top of the proctoring guard's own "Return to full screen" countdown
    // and letting a candidate cancel and freeze it. The attempt is autosaved
    // and stays resumable, and leaving full screen / the window is already
    // handled by the proctoring guard, so no browser prompt is needed here.
    return;
  }

  function wireClock(cfg, signal) {
    // Server-side active-time clock. The timer must count only time the exam
    // is actually on screen: pause when the tab hides or unloads (beacon -
    // survives tab close), resume when it is visible again. The question page
    // itself also resumes on load, so this only has to cover the gaps.
    if (!cfg.pauseUrl || !cfg.resumeUrl) return;

    function pause() {
      try {
        navigator.sendBeacon(cfg.pauseUrl + "?csrf=" + encodeURIComponent(CJ.csrfToken()),
                             new Blob([], { type: "application/json" }));
      } catch (e) {}
    }
    function resume() {
      fetch(cfg.resumeUrl, {
        method: "POST",
        headers: { "X-CSRFToken": CJ.csrfToken(), "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      }).catch(function () {});
    }

    window.addEventListener("pagehide", pause, { signal: signal });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") pause();
      else resume();
    }, { signal: signal });
    window.addEventListener("focus", resume, { signal: signal });
  }

  function wireNetwork(signal) {
    const net = CJ.$("#net-icon");
    if (!net) return;
    function update() { net.style.color = navigator.onLine ? "" : "#8b96a3"; }
    window.addEventListener("online", function () {
      update(); CJ.toast("Back online", "ok");
    }, { signal: signal });
    window.addEventListener("offline", function () {
      update(); CJ.toast("You are offline. Answers cannot be saved", "error");
    }, { signal: signal });
    update();
  }

  function wireQGrid(signal) {
    const toggle = CJ.$("#qgrid-toggle");
    const pop = CJ.$("#qgrid-pop");
    if (!toggle || !pop) return;
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      pop.classList.toggle("is-open");
      toggle.classList.toggle("is-open", pop.classList.contains("is-open"));
    }, { signal: signal });
    document.addEventListener("click", function (e) {
      if (!pop.contains(e.target)) {
        pop.classList.remove("is-open");
        toggle.classList.remove("is-open");
      }
    }, { signal: signal });
  }

  function wireSectionDropdown(signal) {
    const toggle = CJ.$("#section-dd-toggle");
    const dd = CJ.$("#section-dd");
    if (!toggle || !dd) return;
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      dd.classList.toggle("is-open");
    }, { signal: signal });
    document.addEventListener("click", function (e) {
      if (!dd.contains(e.target)) dd.classList.remove("is-open");
    }, { signal: signal });
  }

  function wireRevisit(cfg, signal) {
    const key = "cj-revisit-" + cfg.attemptId;
    const btn = CJ.$("#btn-revisit");
    if (!btn) return;
    let marks = {};
    try { marks = JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) {}

    function paint(qid, on) {
      CJ.$$('.qnav-btn[data-qid="' + qid + '"], .qgrid-item[data-qid="' + qid + '"]')
        .forEach(function (el) { el.classList.toggle("is-review", on); });
    }

    Object.keys(marks).forEach(function (qid) { if (marks[qid]) paint(qid, true); });
    if (marks[cfg.questionId]) btn.classList.add("is-marked");

    btn.addEventListener("click", function () {
      const on = !marks[cfg.questionId];
      marks[cfg.questionId] = on;
      btn.classList.toggle("is-marked", on);
      paint(cfg.questionId, on);
      try { localStorage.setItem(key, JSON.stringify(marks)); } catch (e) {}
      CJ.toast(on ? "Marked for review" : "Review mark removed", on ? "warn" : "ok");
    }, { signal: signal });
  }

  function fmtClock(secs) {
    secs = Math.max(0, parseInt(secs, 10) || 0);
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }

  function buildFinishModal() {
    let overlay = document.getElementById("cfin-overlay");
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.id = "cfin-overlay";
    overlay.className = "cfin-overlay";
    overlay.innerHTML =
      '<div class="cfin-card">' +
        '<div class="cfin-head">' +
          '<div class="cfin-head-left">Finish Test</div>' +
          '<div class="cfin-head-right">Remaining Time: <span id="cfin-time">--:--</span>' +
            '<button type="button" class="cfin-x" id="cfin-close" aria-label="Close">&times;</button></div>' +
        '</div>' +
        '<div class="cfin-body">' +
          '<div class="cfin-stats">' +
            '<div class="cfin-donut-wrap">' +
              '<div class="cfin-donut" id="cfin-donut"></div>' +
              '<div class="cfin-hole"></div>' +
            '</div>' +
            '<div class="cfin-text">' +
              '<h4>Your Test Summary</h4>' +
              '<div class="cfin-total" id="cfin-total">0</div>' +
              '<div class="cfin-total-label">Total Questions</div>' +
              '<ul class="cfin-legend">' +
                '<li><span class="cfin-dot cfin-dot--blue"></span> Attempted: <strong id="cfin-att">0</strong></li>' +
                '<li><span class="cfin-dot cfin-dot--orange"></span> Marked for Revisit: <strong id="cfin-rev">0</strong></li>' +
                '<li><span class="cfin-dot cfin-dot--grey"></span> Unattempted: <strong id="cfin-una">0</strong></li>' +
              '</ul>' +
            '</div>' +
          '</div>' +
          '<div class="cfin-sec-title">Section Summary</div>' +
          '<table class="cfin-table">' +
            '<thead><tr><th style="width:6%">#</th><th style="width:46%">Section name</th>' +
            '<th style="width:48%;text-align:right">Status</th></tr></thead>' +
            '<tbody id="cfin-tbody"></tbody>' +
          '</table>' +
        '</div>' +
        '<div class="cfin-foot">' +
          '<button type="button" class="cfin-btn-final" id="cfin-final">Finish Test</button>' +
          '<button type="button" class="cfin-btn-back" id="cfin-back">No, Back to Test</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);
    function close() { overlay.classList.remove("is-on"); }
    overlay.querySelector("#cfin-close").addEventListener("click", close);
    overlay.querySelector("#cfin-back").addEventListener("click", close);
    overlay.querySelector("#cfin-final").addEventListener("click", function () {
      const form = CJ.$("#finish-form");
      if (form) form.submit();
    });
    return overlay;
  }

  function openFinishSummary(cfg) {
    const overlay = buildFinishModal();
    fetch(cfg.summaryUrl, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    }).then(function (res) { return res.json(); }).then(function (sum) {
      if (sum.redirect) { window.location.href = sum.redirect; return; }
      let rev = 0;
      try {
        const marks = JSON.parse(localStorage.getItem("cj-revisit-" + cfg.attemptId) || "{}");
        rev = Object.keys(marks).filter(function (k) { return marks[k]; }).length;
      } catch (e) {}
      const total = sum.total || 0;
      const att = sum.attempted || 0;
      const pct = total ? (att / total) * 100 : 0;
      overlay.querySelector("#cfin-time").textContent = fmtClock(sum.remainingSeconds);
      overlay.querySelector("#cfin-total").textContent = total;
      overlay.querySelector("#cfin-att").textContent = att;
      overlay.querySelector("#cfin-rev").textContent = rev;
      overlay.querySelector("#cfin-una").textContent = total - att;
      overlay.querySelector("#cfin-donut").style.background =
        "conic-gradient(#1668dc 0% " + pct + "%, #d9dee5 " + pct + "% 100%)";
      let tbody = "";
      (sum.sections || []).forEach(function (sec, i) {
        const spct = sec.total ? (sec.attempted / sec.total) * 100 : 0;
        tbody += "<tr><td>" + (i + 1) + ".</td>" +
          "<td><div class='cfin-sec-name'>" + CJ.escape(sec.title || sec.type) + "</div>" +
          "<div class='cfin-sec-sub'>" + CJ.escape((sec.type || "").toUpperCase()) + "</div></td>" +
          "<td><div class='cfin-prog-wrap'><div class='cfin-prog-bg'>" +
          "<div class='cfin-prog-fill' style='width:" + spct + "%'>" + sec.attempted + "</div></div>" +
          "<div class='cfin-prog-text'>Total: " + sec.total + " Questions</div></div></td></tr>";
      });
      overlay.querySelector("#cfin-tbody").innerHTML = tbody;
      overlay.classList.add("is-on");
    }).catch(function () {
      CJ.confirm("Finish this test?",
        "You will not be able to change your answers after finishing.",
        function () { CJ.$("#finish-form").submit(); },
        "Finish Test");
    });
  }

  function wireFinish(cfg, signal) {
    const btn = CJ.$("#btn-finish");
    if (!btn) return;
    btn.addEventListener("click", function () {
      openFinishSummary(cfg);
    }, { signal: signal });
  }

  const SECTION_INIT = {
    coding: { fn: "initCoding", splitter: ["#run-splitter", "#bottom-pane"] },
    sql: { fn: "initSql", splitter: null },
    web: { fn: "initWeb", splitter: ["#web-splitter", "#web-bottom"] },
  };

  function page(cfg, signal) {
    signal = signal || undefined;
    if (activeTimer) { activeTimer.stop(); activeTimer = null; }

    wireTheme(document, signal);
    wireFullscreen(document, signal);
    wireLeaveGuard(cfg, signal);
    wireClock(cfg, signal);
    wireNetwork(signal);
    wireQGrid(signal);
    wireSectionDropdown(signal);
    wireRevisit(cfg, signal);
    wireFinish(cfg, signal);

    activeTimer = new CJ.Timer({
      selector: ".js-timer",
      remainingSeconds: cfg.remainingSeconds,
      onExpire: function () {
        CJ.toast("Section time is over. Submitting your test.", "warn");
        setTimeout(function () { CJ.$("#finish-form").submit(); }, 1500);
      },
    });

    CJ.initVSplitter("#pane-splitter", ".pane-question", "cj-panew-" + cfg.attemptId, signal);

    const section = SECTION_INIT[cfg.sectionType];
    if (section) {
      if (section.splitter) {
        CJ.initSplitter(section.splitter[0], section.splitter[1], signal);
      }
      if (cfg.sectionType === "web") {
        CJ.initVSplitter("#web-pane-splitter", ".web-editors",
                         "cj-webw-" + cfg.attemptId, signal,
                         { left: 220, right: 200 });
      }
      if (CJ[section.fn]) {
        CJ[section.fn](Object.assign({ signal: signal }, cfg.section));
      }
    }
  }

  CJ.examInit = { page: page };
})(window);
