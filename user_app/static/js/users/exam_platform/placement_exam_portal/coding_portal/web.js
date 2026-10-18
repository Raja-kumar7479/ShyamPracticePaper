(function (window) {
  "use strict";

  const CJ = window.CJ;

  CJ.initWeb = function (cfg) {
    const editors = {
      html: CJ.mountEditor("#editor-html"),
      css: CJ.mountEditor("#editor-css"),
      js: CJ.mountEditor("#editor-js"),
    };
    if (!editors.html) return;

    const frame = CJ.$("#preview-frame");
    const runBtn = CJ.$("#btn-preview");
    const submitBtn = CJ.$("#btn-submit-web");
    const casesPanel = CJ.$("#panel-cases");

    const tabs = CJ.initTabs("#response-tabs", "#response-panels");
    CJ.initTabs("#web-editor-tabs", "#web-editor-panels", function (name) {
      if (editors[name]) editors[name].focus();
    });

    editors.html.setValue(cfg.savedHtml || cfg.starterHtml || "");
    editors.css.setValue(cfg.savedCss || cfg.starterCss || "");
    editors.js.setValue(cfg.savedJs || cfg.starterJs || "");

    const WEB_WORDS = {
      html: ["div", "span", "h1", "h2", "h3", "h4", "p", "ul", "ol", "li",
        "table", "thead", "tbody", "tr", "td", "th", "form", "input", "button",
        "label", "select", "option", "textarea", "img", "a", "href", "src",
        "class", "id", "style", "section", "header", "footer", "nav", "main",
        "article", "strong", "em", "br", "hr", "placeholder", "type", "value"],
      css: ["color", "background", "background-color", "border", "margin",
        "padding", "width", "height", "display", "flex", "grid", "block",
        "inline-block", "none", "position", "absolute", "relative", "fixed",
        "top", "left", "right", "bottom", "font-size", "font-family",
        "font-weight", "text-align", "center", "justify-content",
        "align-items", "gap", "border-radius", "box-shadow", "overflow",
        "cursor", "pointer", "hover", "transition", "transform", "opacity",
        "line-height", "max-width", "min-height", "z-index"],
      js: ["document", "getElementById", "querySelector", "querySelectorAll",
        "addEventListener", "createElement", "appendChild", "textContent",
        "innerHTML", "classList", "add", "remove", "toggle", "function",
        "return", "const", "let", "var", "if", "else", "for", "while",
        "forEach", "map", "filter", "length", "console", "log", "true",
        "false", "null", "style", "value", "setAttribute", "getAttribute"],
    };
    Object.keys(editors).forEach(function (k) {
      CJ.attachAutocomplete(editors[k], function () { return WEB_WORDS[k]; },
                            function () { return k; });
      const hlLang = k === "js" ? "javascript" : k;
      CJ.attachHighlight(editors[k], function () { return hlLang; });
      editors[k].pairLang = k;
    });

    const autosave = new CJ.Autosave({
      url: cfg.saveUrl,
      signal: cfg.signal,
      getPayload: function () {
        return {
          question_id: cfg.questionId,
          code_html: editors.html.getValue(),
          code_css: editors.css.getValue(),
          code_js: editors.js.getValue(),
          attempted: true,
        };
      },
    });

    function compose() {
      return (
        "<!doctype html><html><head><meta charset='utf-8'><style>" +
        editors.css.getValue() +
        "</style></head><body>" +
        editors.html.getValue() +
        "<" + "script>try{" + editors.js.getValue() + "}catch(e){" +
        "document.body.insertAdjacentHTML('beforeend'," +
        "'<pre style=\"color:#d43f3f;font:12px monospace\">JS error: '+e.message+'</pre>')}" +
        "<" + "/script></body></html>"
      );
    }

    const rerender = CJ.debounce(function () {
      frame.srcdoc = compose();
    }, 450);

    Object.keys(editors).forEach(function (k) {
      editors[k].onChange(function () {
        autosave.touch();
        rerender();
      });
    });

    frame.srcdoc = compose();

    function busy(btn, on, label) {
      if (btn.dataset.label === undefined) btn.dataset.label = btn.textContent;
      btn.disabled = on;
      if (on) {
        btn.innerHTML = "";
        btn.appendChild(CJ.el("span", { class: "spinner" }));
        btn.appendChild(document.createTextNode(" " + label));
      } else {
        btn.textContent = btn.dataset.label || label;
      }
    }

    function renderAssertions(data) {
      casesPanel.innerHTML = "";
      casesPanel.appendChild(CJ.el("div", {
        class: "result-banner " + (data.passed === data.total ? "is-pass" : "is-fail"),
      }, [
        CJ.el("span", { text: data.passed === data.total ? "All checks passed" : "Some checks failed" }),
        CJ.el("span", { class: "score", text: data.passed + " / " + data.total + " checks" }),
      ]));

      const list = CJ.el("div", { class: "assert-list" });
      (data.results || []).forEach(function (r) {
        list.appendChild(CJ.el("div", {
          class: "assert " + (r.status === "PASS" ? "is-pass" : "is-fail"),
        }, [
          CJ.el("span", { class: "mark", text: r.status === "PASS" ? "✓" : "✕" }),
          CJ.el("div", {}, [
            CJ.el("span", { text: r.message }),
            r.detail ? CJ.el("span", { class: "detail", text: r.detail }) : null,
          ]),
        ]));
      });
      casesPanel.appendChild(list);
      tabs.activate("cases");
    }

    let checking = false;

    async function check(url, btn, label) {
      if (checking) return null;
      checking = true;
      busy(btn, true, label);
      try {
        const data = await CJ.api(url, {
          method: "POST",
          body: {
            question_id: cfg.questionId,
            code_html: editors.html.getValue(),
            code_css: editors.css.getValue(),
            code_js: editors.js.getValue(),
          },
        });
        renderAssertions(data);
        return data;
      } catch (e) {
        CJ.toast(e.message, "error");
        return null;
      } finally {
        checking = false;
        busy(btn, false, label);
      }
    }

    if (runBtn) {
      runBtn.addEventListener("click", function () {
        frame.srcdoc = compose();
        check(cfg.runUrl, runBtn, "Checking…");
      });
    }

    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        CJ.confirm("Submit this question?",
          "Your HTML, CSS and JavaScript will be graded against all checks.",
          async function () {
            const data = await check(cfg.submitUrl, submitBtn, "Submitting…");
            if (data) {
              CJ.toast(
                data.passed === data.total
                  ? "All checks passed"
                  : "Submitted: " + data.passed + "/" + data.total + " checks passed",
                data.passed === data.total ? "ok" : "warn"
              );
              CJ.markSubmitted(cfg.questionId);
            }
          }, "Submit");
      });
    }
  };
})(window);
