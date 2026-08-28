(function (window) {
  "use strict";

  const CJ = window.CJ;

  CJ.initSql = function (cfg) {
    const editor = CJ.mountEditor("#sql-editor");
    if (!editor) return;

    const runBtn = CJ.$("#btn-run-query");
    const checkBtn = CJ.$("#btn-check-query");
    const outputPanel = CJ.$("#panel-output");
    const casesPanel = CJ.$("#panel-cases");

    const tabs = CJ.initTabs("#response-tabs", "#response-panels");
    new CJ.SchemaViewer("#schema-panel", cfg.signal);

    const schemaClose = CJ.$("#schema-close");
    if (schemaClose) {
      schemaClose.addEventListener("click", function () {
        tabs.activate("query");
      });
    }

    const autosave = new CJ.Autosave({
      url: cfg.saveUrl,
      signal: cfg.signal,
      getPayload: function () {
        return {
          question_id: cfg.questionId,
          code: editor.getValue(),
          attempted: true,
        };
      },
    });

    editor.setValue(cfg.savedCode || "");
    editor.onChange(function () { autosave.touch(); });

    const SQL_KEYWORDS = ["SELECT", "FROM", "WHERE", "ORDER", "BY", "GROUP",
      "HAVING", "LIMIT", "OFFSET", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER",
      "ON", "AS", "AND", "OR", "NOT", "IN", "BETWEEN", "LIKE", "IS", "NULL",
      "DISTINCT", "COUNT", "SUM", "AVG", "MIN", "MAX", "ASC", "DESC", "UNION",
      "ALL", "CASE", "WHEN", "THEN", "ELSE", "END", "EXISTS", "WITH",
      "CONCAT", "SUBSTRING", "UPPER", "LOWER", "ROUND", "COALESCE", "IFNULL",
      "DATE", "YEAR", "MONTH", "DAY", "NOW"];
    CJ.attachAutocomplete(editor, function () { return SQL_KEYWORDS; },
                          function () { return "sql"; });
    CJ.attachHighlight(editor, function () { return "sql"; });
    editor.pairLang = "sql";

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

    function renderGrid(host, result) {
      host.innerHTML = "";

      host.appendChild(CJ.el("div", { class: "result-meta" }, [
        CJ.el("span", {
          text: result.row_count + " row" + (result.row_count === 1 ? "" : "s") +
                " · " + result.columns.length + " column" +
                (result.columns.length === 1 ? "" : "s"),
        }),
        result.truncated
          ? CJ.el("span", { class: "badge badge-warn", text: "Preview truncated" })
          : null,
      ]));

      if (!result.columns.length) {
        host.appendChild(CJ.el("div", { class: "console console-empty",
                                        text: "Query returned no columns." }));
        return;
      }

      const thead = CJ.el("thead", {}, [
        CJ.el("tr", {}, result.columns.map(c => CJ.el("th", { text: c }))),
      ]);
      const tbody = CJ.el("tbody", {}, result.rows.map(function (row) {
        return CJ.el("tr", {}, row.map(function (v) {
          const isNull = v === null || v === undefined;
          return CJ.el("td", {
            class: isNull ? "is-null" : null,
            text: isNull ? "NULL" : String(v),
          });
        }));
      }));

      host.appendChild(CJ.el("div", { class: "grid-scroll" }, [
        CJ.el("table", { class: "result-grid" }, [thead, tbody]),
      ]));
    }

    function renderError(host, message) {
      host.innerHTML = "";
      host.appendChild(CJ.el("div", { class: "sql-error", text: message }));
    }

    async function runQuery() {
      busy(runBtn, true, "Running…");
      try {
        const data = await CJ.api(cfg.runUrl, {
          method: "POST",
          body: { question_id: cfg.questionId, query: editor.getValue() },
        });
        renderGrid(outputPanel, data.result);
        tabs.activate("output");
      } catch (e) {
        renderError(outputPanel, e.message);
        tabs.activate("output");
      } finally {
        busy(runBtn, false, "Run Query");
      }
    }

    async function checkQuery() {
      busy(checkBtn, true, "Checking…");
      try {
        const data = await CJ.api(cfg.checkUrl, {
          method: "POST",
          body: { question_id: cfg.questionId, query: editor.getValue() },
        });

        casesPanel.innerHTML = "";
        casesPanel.appendChild(CJ.el("div", { class: "tc-banner",
                                              text: "Test Case Results" }));

        const card = CJ.el("div", { class: "tc-card is-open" });
        card.appendChild(CJ.el("div", { class: "tc-card-head" }, [
          CJ.el("span", { class: "tc-check" + (data.correct ? "" : " is-fail"),
                          text: data.correct ? "✓" : "✕" }),
          CJ.el("span", { text: "Test Case 1" }),
          CJ.el("span", { class: "tc-chev", text: "▾" }),
        ]));

        const body = CJ.el("div", { class: "tc-card-body" });
        if (!data.correct && data.reason) {
          body.appendChild(CJ.el("div", { class: "tc-sec" }, [
            CJ.el("div", { class: "tc-sec-title", text: "Why it failed" }),
            CJ.el("div", { class: "tc-kv" }, [
              CJ.el("pre", { text: data.reason }),
            ]),
          ]));
        }
        if (data.result) {
          const gridHost = CJ.el("div", { class: "tc-sec" });
          gridHost.appendChild(CJ.el("div", { class: "tc-sec-title",
                                              text: "Your Query Output" }));
          renderGrid(gridHost, data.result);
          body.appendChild(gridHost);
        }
        card.appendChild(body);
        CJ.$(".tc-card-head", card).addEventListener("click", function () {
          card.classList.toggle("is-open");
        });

        const list = CJ.el("div", { class: "tc-list" });
        list.appendChild(card);
        casesPanel.appendChild(list);
        tabs.activate("cases");

        CJ.toast(data.correct ? "Query is correct" : "Query output does not match",
                 data.correct ? "ok" : "warn");

        const btn = CJ.$('.qnav-btn[data-qid="' + cfg.questionId + '"]');
        if (btn) btn.classList.add("is-attempted");
      } catch (e) {
        renderError(casesPanel, e.message);
        tabs.activate("cases");
      } finally {
        busy(checkBtn, false, "Check Query");
      }
    }

    if (runBtn) runBtn.addEventListener("click", runQuery);
    if (checkBtn) checkBtn.addEventListener("click", checkQuery);

    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        runQuery();
      }
    }, cfg.signal ? { signal: cfg.signal } : false);
  };
})(window);
