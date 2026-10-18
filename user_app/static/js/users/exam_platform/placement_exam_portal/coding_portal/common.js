(function (window) {
  "use strict";

  const CJ = {};

  CJ.csrfToken = function () {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  };

  CJ.api = async function (url, options) {
    options = options || {};
    const headers = Object.assign(
      { "Content-Type": "application/json", "X-CSRFToken": CJ.csrfToken() },
      options.headers || {}
    );
    const res = await fetch(url, {
      method: options.method || "GET",
      headers: headers,
      credentials: "same-origin",
      body: options.body ? JSON.stringify(options.body) : undefined,
    });

    if (res.status === 401) {
      window.location.href = "/user_login";
      throw new Error("Session expired");
    }

    let data = null;
    const ctype = res.headers.get("content-type") || "";
    if (ctype.indexOf("application/json") !== -1) {
      data = await res.json();
    }
    if (!res.ok) {
      throw new Error((data && data.error) || "Request failed (" + res.status + ")");
    }
    return data;
  };

  CJ.$ = (sel, root) => (root || document).querySelector(sel);
  CJ.$$ = (sel, root) => Array.prototype.slice.call((root || document).querySelectorAll(sel));

  CJ.el = function (tag, attrs, children) {
    const node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "class") node.className = attrs[k];
      else if (k === "text") node.textContent = attrs[k];
      else if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== null && attrs[k] !== undefined) node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) {
      if (c) node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  };

  CJ.escape = function (s) {
    const d = document.createElement("div");
    d.textContent = s === null || s === undefined ? "" : String(s);
    return d.innerHTML;
  };

  CJ.debounce = function (fn, wait) {
    let t = null;
    return function () {
      const args = arguments, ctx = this;
      clearTimeout(t);
      t = setTimeout(() => fn.apply(ctx, args), wait);
    };
  };

  CJ.toast = function (message, kind) {
    let host = CJ.$("#cj-toasts");
    if (!host) {
      host = CJ.el("div", { id: "cj-toasts" });
      host.style.cssText =
        "position:fixed;left:18px;top:18px;z-index:200;display:flex;" +
        "flex-direction:column;gap:8px;max-width:340px";
      document.body.appendChild(host);
    }
    const bg = kind === "error" ? "#d43f3f" : kind === "warn" ? "#d98b0a" : "#1a9c5b";
    const node = CJ.el("div", { text: message });
    node.style.cssText =
      "background:" + bg + ";color:#fff;padding:10px 14px;border-radius:4px;" +
      "font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.2);opacity:0;" +
      "transition:opacity .18s";
    host.appendChild(node);
    requestAnimationFrame(() => { node.style.opacity = "1"; });
    setTimeout(function () {
      node.style.opacity = "0";
      setTimeout(() => node.remove(), 220);
    }, 3000);
  };

  CJ.initTabs = function (barSel, panelsSel, onSwitch) {
    const bar = CJ.$(barSel);
    const panels = CJ.$(panelsSel);
    if (!bar || !panels) return null;

    function activate(name) {
      CJ.$$("[data-tab]", bar).forEach(function (b) {
        b.classList.toggle("is-active", b.dataset.tab === name);
      });
      CJ.$$("[data-panel]", panels).forEach(function (p) {
        p.classList.toggle("is-active", p.dataset.panel === name);
      });
      if (onSwitch) onSwitch(name);
    }

    bar.addEventListener("click", function (e) {
      const btn = e.target.closest("[data-tab]");
      if (btn) activate(btn.dataset.tab);
    });

    return { activate: activate };
  };

  CJ.confirm = function (title, message, onYes, yesLabel) {
    const backdrop = CJ.el("div", { class: "modal-backdrop" });
    const modal = CJ.el("div", { class: "modal" }, [
      CJ.el("h3", { text: title }),
      CJ.el("p", { class: "muted", text: message }),
    ]);
    const actions = CJ.el("div", { class: "modal-actions" }, [
      CJ.el("button", {
        class: "btn btn-ghost", text: "Cancel",
        onclick: () => backdrop.remove(),
      }),
      CJ.el("button", {
        class: "btn btn-primary", text: yesLabel || "Confirm",
        onclick: function () { backdrop.remove(); onYes(); },
      }),
    ]);
    modal.appendChild(actions);
    backdrop.appendChild(modal);
    backdrop.addEventListener("click", function (e) {
      if (e.target === backdrop) backdrop.remove();
    });
    document.body.appendChild(backdrop);
  };

  CJ.confirmSwitch = function (title, message, actions) {
    const backdrop = CJ.el("div", { class: "modal-backdrop" });
    const modal = CJ.el("div", { class: "modal" }, [
      CJ.el("h3", { text: title }),
      CJ.el("p", { class: "muted", text: message }),
    ]);

    function run(fn) {
      backdrop.remove();
      if (fn) fn();
    }

    modal.appendChild(CJ.el("div", { class: "modal-actions" }, [
      CJ.el("button", {
        class: "btn btn-ghost", text: "Cancel",
        onclick: function () { run(actions.cancel); },
      }),
      CJ.el("button", {
        class: "btn btn-ghost", text: "Discard",
        onclick: function () { run(actions.discard); },
      }),
      CJ.el("button", {
        class: "btn btn-ghost", text: "Save draft",
        onclick: function () { run(actions.save); },
      }),
      CJ.el("button", {
        class: "btn btn-primary", text: "Submit & switch",
        onclick: function () { run(actions.submit); },
      }),
    ]));

    backdrop.appendChild(modal);
    backdrop.addEventListener("click", function (e) {
      if (e.target === backdrop) run(actions.cancel);
    });
    document.body.appendChild(backdrop);
  };

  window.CJ = CJ;
})(window);
