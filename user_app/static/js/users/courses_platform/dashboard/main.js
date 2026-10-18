(function () {
  "use strict";

  var currentTab = "all";

  function getEl(id) {
    var el = document.getElementById(id);
    if (!el) {
      console.warn("[Dashboard] Element not found: #" + id);
    }
    return el;
  }

  function setupSidebar() {
    var toggle = getEl("mobileToggle");
    var sidebar = getEl("sidebar");
    var overlay = getEl("overlay");

    if (!toggle || !sidebar || !overlay) return;

    function openSidebar() {
      sidebar.classList.add("open");
      overlay.classList.add("active");
      document.body.style.overflow = "hidden";
      toggle.setAttribute("aria-expanded", "true");
    }

    function closeSidebar() {
      sidebar.classList.remove("open");
      overlay.classList.remove("active");
      document.body.style.overflow = "";
      toggle.setAttribute("aria-expanded", "false");
    }

    toggle.addEventListener("click", function () {
      if (sidebar.classList.contains("open")) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });

    overlay.addEventListener("click", closeSidebar);

    var closeBtn = document.getElementById("sidebarToggle");
    if (closeBtn) closeBtn.addEventListener("click", closeSidebar);

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && sidebar.classList.contains("open")) {
        closeSidebar();
      }
    });
  }

  function setupMoreCards() {
    var moreCards = document.querySelectorAll(".js-more-card");
    if (!moreCards.length) return;

    moreCards.forEach(function (card) {
      card.style.cursor = "pointer";

      card.addEventListener("click", function () {
        var href = card.getAttribute("data-href");
        if (href) {
          window.location.href = href;
        }
      });

      card.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          var href = card.getAttribute("data-href");
          if (href) {
            window.location.href = href;
          }
        }
      });
    });
  }

  function applyIconColors() {
    var iconMap = [
      { selector: ".card-icon-practice", color: "var(--primary)" },
      { selector: ".card-icon-owned",    color: "var(--success)" },
      { selector: ".card-icon-premium",  color: "var(--accent)"  },
      { selector: ".card-icon-free",     color: "var(--success)" }
    ];

    iconMap.forEach(function (entry) {
      var els = document.querySelectorAll(entry.selector);
      els.forEach(function (el) {
        el.style.color = entry.color;
      });
    });
  }

  function showTabEmptyState(show, tabLabel) {
    var host = getEl("content-area");
    if (!host) return;
    var box = getEl("tab-empty");
    if (!box) {
      box = document.createElement("div");
      box.id = "tab-empty";
      box.className = "no-content";
      host.appendChild(box);
    }
    box.innerHTML =
      '<div class="no-results-icon"><i class="far fa-folder-open"></i></div>' +
      "<h5>Nothing under " + (tabLabel || "this tab") + " yet</h5>" +
      "<p>Resources appear here as soon as they are added to this course.</p>";
    box.style.display = show ? "" : "none";
  }

  function setupTabFilters() {
    var pills = document.querySelectorAll(".tab-pill");
    if (!pills.length) return;

    pills.forEach(function (pill) {
      pill.addEventListener("click", function () {
        var filter = pill.getAttribute("data-filter");
        if (!filter) return;

        currentTab = filter;
        pills.forEach(function (p) { p.classList.remove("active"); });
        pill.classList.add("active");

        var sections = document.querySelectorAll(".view-section");
        var shown = 0;
        sections.forEach(function (section) {
          var visible = filter === "all" || section.id === "view-" + filter;
          section.style.display = visible ? "block" : "none";
          if (visible) shown++;
        });

        // A course can legitimately have nothing in one tab (all practice and
        // no reading material, say). Saying so beats an empty page.
        showTabEmptyState(shown === 0, pill.textContent.trim());

        var noResults = getEl("no-results");
        if (noResults) noResults.style.display = "none";
      });
    });
  }

  function bindClearButton() {
    var input = getEl("searchInput");
    var clearBtn = getEl("clearSearchBtn");
    if (!input || !clearBtn || clearBtn.dataset.bound) return;
    clearBtn.dataset.bound = "1";
    clearBtn.addEventListener("click", function () {
      input.value = "";
      runFilter("");
    });
  }

  function setupSearch() {
    var input = getEl("searchInput");
    if (!input) return;

    input.addEventListener("input", function () {
      runFilter(input.value);
    });
    bindClearButton();
  }

  // The content area can be replaced in place when the course changes in the
  // database (see content_freshness.js). Everything bound inside it is bound
  // again here, and the reader's current tab and search are kept.
  window.sppDashboardRebind = function () {
    try { setupMoreCards(); } catch (err) { console.error("[Dashboard] rebind cards:", err); }
    try { applyIconColors(); } catch (err) { console.error("[Dashboard] rebind icons:", err); }
    try { bindClearButton(); } catch (err) { console.error("[Dashboard] rebind clear:", err); }
    var input = getEl("searchInput");
    try { runFilter(input ? input.value : ""); } catch (err) { console.error("[Dashboard] rebind filter:", err); }
  };

  function runFilter(rawQuery) {
    var query = (rawQuery || "").toLowerCase().trim();
    var sections = document.querySelectorAll(".view-section");
    var total = 0;
    var noResults = getEl("no-results");

    sections.forEach(function (section) {
      var cards = section.querySelectorAll(".filter-item");
      var hits = 0;

      cards.forEach(function (card) {
        var titleEl = card.querySelector(".card-title");
        var descEl  = card.querySelector(".card-desc");
        var titleText = titleEl ? titleEl.textContent.toLowerCase() : "";
        var descText  = descEl  ? descEl.textContent.toLowerCase()  : "";
        var match = !query || titleText.indexOf(query) !== -1 || descText.indexOf(query) !== -1;

        card.style.display = match ? "" : "none";
        if (match) { hits++; total++; }
      });

      if (query.length > 0) {
        section.style.display = hits > 0 ? "block" : "none";
      } else {
        if (currentTab === "all") {
          section.style.display = "block";
        } else {
          section.style.display = section.id === "view-" + currentTab ? "block" : "none";
        }
      }
    });

    if (noResults) {
      noResults.style.display = (query.length > 0 && total === 0) ? "block" : "none";
    }
  }

  function init() {
    try {
      setupSidebar();
    } catch (err) {
      console.error("[Dashboard] setupSidebar error:", err);
    }

    try {
      setupMoreCards();
    } catch (err) {
      console.error("[Dashboard] setupMoreCards error:", err);
    }

    try {
      applyIconColors();
    } catch (err) {
      console.error("[Dashboard] applyIconColors error:", err);
    }

    try {
      setupTabFilters();
    } catch (err) {
      console.error("[Dashboard] setupTabFilters error:", err);
    }

    try {
      setupSearch();
    } catch (err) {
      console.error("[Dashboard] setupSearch error:", err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();