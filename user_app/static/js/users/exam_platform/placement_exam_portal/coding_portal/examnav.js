(function (window) {
  "use strict";

  const CJ = window.CJ;
  const ROOT_SEL = "#page-root";
  const EXAM_PATH_RE = /^\/coding\/attempt\/\d+\/(question|section)\/\d+(?:[/?]|$)/;

  let pageAbort = null;

  function isExamPath(path) {
    return EXAM_PATH_RE.test(path);
  }

  async function fetchFragment(url) {
    const res = await fetch(url, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    });
    if (res.status === 401) { window.location.href = "/user_login"; throw new Error("Session expired"); }
    if (res.redirected && !isExamPath(new URL(res.url).pathname)) {
      window.location.href = res.url;
      throw new Error("redirecting");
    }
    if (!res.ok) throw new Error("Failed to load (" + res.status + ")");
    const data = await res.json();
    if (data.redirect) {
      window.location.href = data.redirect;
      throw new Error("redirecting");
    }
    return data;
  }

  function ensureAssets(list, selector, make) {
    (list || []).forEach(function (href) {
      if (document.querySelector(selector(href))) return;
      document.head.appendChild(make(href));
    });
  }

  function loadScriptsSequentially(srcs) {
    return srcs.reduce(function (chain, src) {
      return chain.then(function () {
        if (document.querySelector('script[data-exam-src="' + CSS.escape(src) + '"]')) return;
        return new Promise(function (resolve, reject) {
          const s = document.createElement("script");
          s.src = src;
          s.dataset.examSrc = src;
          s.onload = resolve;
          s.onerror = reject;
          document.head.appendChild(s);
        });
      });
    }, Promise.resolve());
  }

  async function render(payload, push) {
    if (pageAbort) pageAbort.abort();
    pageAbort = new AbortController();

    ensureAssets(payload.css, function (h) { return 'link[href="' + h + '"]'; },
      function (h) {
        const l = document.createElement("link");
        l.rel = "stylesheet"; l.href = h;
        return l;
      });

    document.title = payload.title;
    const rootEl = CJ.$(ROOT_SEL);
    rootEl.innerHTML = payload.html;
    Array.prototype.slice.call(rootEl.querySelectorAll("script:not([src])"))
      .forEach(function (old) {
        const s = document.createElement("script");
        s.textContent = old.textContent;
        old.parentNode.replaceChild(s, old);
      });

    if (push) history.pushState({ examUrl: payload.url }, "", payload.url);

    await loadScriptsSequentially(payload.js || []);

    window.CJ.examInit.page(payload, pageAbort.signal);

    window.scrollTo(0, 0);
  }

  async function go(url, push) {
    CJ.toast.dismissAll && CJ.toast.dismissAll();
    try {
      const payload = await fetchFragment(url);
      await render(payload, push !== false);
    } catch (e) {
      if (e.message !== "redirecting") {
        CJ.toast("Could not load the next page: " + e.message, "error");
      }
    }
  }

  document.addEventListener("click", function (e) {
    const a = e.target.closest("a[href]");
    if (!a || a.host !== location.host) return;
    const url = new URL(a.href, location.href);
    if (!isExamPath(url.pathname)) return;
    e.preventDefault();
    go(url.pathname + url.search);
  });

  window.addEventListener("popstate", function (e) {
    const url = (e.state && e.state.examUrl) || location.pathname + location.search;
    go(url, false);
  });

  function boot(cfg) {
    pageAbort = new AbortController();
    history.replaceState({ examUrl: location.pathname + location.search },
                         "", location.pathname + location.search);
    window.CJ.examInit.page(cfg, pageAbort.signal);
  }

  CJ.examNav = { go: go, boot: boot };
})(window);
