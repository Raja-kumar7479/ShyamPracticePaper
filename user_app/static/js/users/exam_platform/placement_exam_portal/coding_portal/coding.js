(function (window) {
  "use strict";

  const CJ = window.CJ;

  CJ.initCoding = function (cfg) {
    const editor = CJ.mountEditor("#code-editor");
    if (!editor) return;

    const langSelect = CJ.$("#lang-select");
    const compilerNote = CJ.$("#compiler-note");
    const runBtn = CJ.$("#btn-run");
    const submitBtn = CJ.$("#btn-submit");
    const resetBtn = CJ.$("#btn-reset");
    const customToggle = CJ.$("#custom-input-toggle");
    const customBox = CJ.$("#custom-input-box");
    const customText = CJ.$("#custom-input-text");
    const outputPanel = CJ.$("#panel-output");
    const casesPanel = CJ.$("#panel-cases");

    const tabs = CJ.initTabs("#response-tabs", "#response-panels");

    const drafts = Object.assign({}, cfg.templates || {});
    if (cfg.savedCode && cfg.savedLanguage) drafts[cfg.savedLanguage] = cfg.savedCode;

    let language = cfg.savedLanguage || cfg.languages[0];

    const autosave = new CJ.Autosave({
      url: cfg.saveUrl,
      signal: cfg.signal,
      getPayload: function () {
        return {
          question_id: cfg.questionId,
          language: language,
          code: editor.getValue(),
          attempted: editor.getValue().trim().length > 0,
        };
      },
    });

    const COMPILER_LABEL = {
      python: "Python 3.11", java: "Java - 17", c: "GCC 12",
      cpp: "G++ 12", csharp: "Mono C# 6.8", javascript: "Node 18",
    };

    const KEYWORDS = {
      python: ["print", "input", "def", "return", "if", "elif", "else", "for",
        "while", "break", "continue", "pass", "import", "from", "as", "class",
        "self", "True", "False", "None", "and", "or", "not", "in", "is",
        "lambda", "try", "except", "finally", "raise", "with", "yield",
        "range", "len", "int", "float", "str", "list", "dict", "set", "tuple",
        "enumerate", "sorted", "reversed", "sum", "min", "max", "abs", "map",
        "filter", "zip", "append", "split", "join", "strip", "global"],
      java: ["public", "private", "protected", "static", "final", "void",
        "class", "interface", "extends", "implements", "new", "return", "if",
        "else", "for", "while", "do", "switch", "case", "break", "continue",
        "int", "long", "double", "float", "boolean", "char", "byte", "short",
        "String", "System", "out", "println", "print", "Scanner", "nextInt",
        "nextLine", "import", "package", "this", "super", "try", "catch",
        "finally", "throw", "throws", "true", "false", "null", "Integer",
        "ArrayList", "HashMap", "HashSet", "Math", "length", "abstract"],
      c: ["printf", "scanf", "include", "return", "int", "long", "double",
        "float", "char", "void", "if", "else", "for", "while", "do", "switch",
        "case", "break", "continue", "struct", "typedef", "sizeof", "malloc",
        "calloc", "realloc", "free", "const", "static", "unsigned", "signed",
        "NULL", "true", "false", "strlen", "strcpy", "strcmp", "memset"],
      cpp: ["cout", "cin", "endl", "include", "iostream", "vector", "string",
        "using", "namespace", "std", "return", "int", "long", "double",
        "float", "char", "bool", "void", "if", "else", "for", "while", "do",
        "switch", "case", "break", "continue", "class", "struct", "public",
        "private", "protected", "new", "delete", "const", "static", "true",
        "false", "nullptr", "push_back", "size", "begin", "end", "sort",
        "map", "set", "pair", "auto", "template", "typename"],
      csharp: ["public", "private", "protected", "static", "void", "class",
        "interface", "namespace", "using", "new", "return", "if", "else",
        "for", "foreach", "while", "do", "switch", "case", "break",
        "continue", "int", "long", "double", "float", "bool", "char",
        "string", "var", "Console", "WriteLine", "ReadLine", "Parse", "true",
        "false", "null", "this", "base", "try", "catch", "finally", "throw",
        "List", "Dictionary", "Length", "Split", "Select", "ToArray"],
      javascript: ["console", "log", "function", "return", "const", "let",
        "var", "if", "else", "for", "while", "do", "switch", "case", "break",
        "continue", "true", "false", "null", "undefined", "new", "class",
        "extends", "this", "typeof", "instanceof", "try", "catch", "finally",
        "throw", "async", "await", "Promise", "require", "readFileSync",
        "parseInt", "parseFloat", "Number", "String", "Array", "Object",
        "Math", "JSON", "map", "filter", "reduce", "forEach", "push", "split",
        "join", "trim", "length", "toString"],
    };
    CJ.attachAutocomplete(editor,
      function () { return KEYWORDS[language] || []; },
      function () { return language; });
    CJ.attachHighlight(editor, function () { return language; });

    const guards = CJ.attachGuards(editor, {
      language: language,
      readOnlyRegions: true,
    });

    const submitted = {};
    function isDirty(lang) {
      const cur = lang === language ? editor.getValue() : drafts[lang];
      if (cur === undefined) return false;
      const base = (cfg.templates || {})[lang];
      if (base !== undefined && cur === base) return false;
      return !submitted[lang] || submitted[lang] !== cur;
    }

    function applyLanguage(lang) {
      drafts[language] = editor.getValue();
      language = lang;
      const next = drafts[lang] !== undefined
        ? drafts[lang]
        : ((cfg.templates || {})[lang] || "");
      editor.setValue(next);
      guards.setLanguage(lang);
      if (compilerNote) {
        compilerNote.textContent = "Compiler: " + (COMPILER_LABEL[lang] || lang);
      }
      if (langSelect) langSelect.value = lang;
      outputPanel.innerHTML =
        '<div class="console console-empty">Custom-input output appears here.</div>';
      casesPanel.innerHTML =
        '<div class="console console-empty">Compile and Test to see the testcase results here.</div>';
      autosave.touch();
    }

    if (langSelect) {
      langSelect.value = language;
      langSelect.addEventListener("change", function () {
        const target = this.value;
        const from = language;
        if (target === from || !isDirty(from)) { applyLanguage(target); return; }

        this.value = from;
        CJ.confirmSwitch(
          "Switch to " + target.toUpperCase() + "?",
          "Your " + from.toUpperCase() + " code has not been submitted. " +
          "Save it as a draft, or submit it for grading before switching.",
          {
            save: function () {
              drafts[from] = editor.getValue();
              autosave.save(true).then(function (ok) {
                if (!ok) return;
                submitted[from] = drafts[from];
                CJ.toast("Draft saved for " + from.toUpperCase(), "ok");
                applyLanguage(target);
              });
            },
            submit: function () {
              doSubmit(function () { applyLanguage(target); });
            },
            discard: function () { applyLanguage(target); },
          }
        );
      });
    }

    editor.setValue(drafts[language] !== undefined ? drafts[language] : "");
    if (compilerNote) {
      compilerNote.textContent = "Compiler: " + (COMPILER_LABEL[language] || language);
    }
    editor.onChange(function () { autosave.touch(); });

    if (customToggle) {
      customToggle.addEventListener("change", function () {
        customBox.classList.toggle("hidden", !this.checked);
      });
    }

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

    function renderConsole(html) {
      outputPanel.innerHTML = html;
      tabs.activate("output");
    }

    function tcSection(title, rows) {
      const body = [CJ.el("div", { class: "tc-sec-title", text: title })];
      rows.forEach(function (pair) {
        if (pair[1] === null || pair[1] === undefined) return;
        body.push(CJ.el("div", { class: pair[2] ? "tc-kv inline" : "tc-kv" }, [
          CJ.el("span", { class: "k", text: pair[0] }),
          CJ.el("pre", { text: String(pair[1]) }),
        ]));
      });
      return CJ.el("div", { class: "tc-sec" }, body);
    }

    function renderCases(data, graded) {
      casesPanel.innerHTML = "";

      const failed = data.total - data.passed;
      const kind = graded ? "Graded" : "Sample";
      let bannerText, bannerClass;
      if (data.verdict === "CE") {
        bannerText = "Compilation Error";
        bannerClass = "is-fail";
      } else if (failed > 0) {
        bannerText = failed + "/" + data.total + " - " + kind + " Test Cases Failed";
        bannerClass = "is-fail";
      } else {
        bannerText = data.passed + "/" + data.total + " - " + kind + " Test Cases Passed";
        bannerClass = "is-pass";
      }
      casesPanel.appendChild(CJ.el("div", {
        class: "tc-banner " + bannerClass, text: bannerText,
      }));

      if (data.verdict === "CE") {
        casesPanel.appendChild(CJ.el("div", { class: "console console-error",
                                              text: data.error || "Compilation failed" }));
        tabs.activate("cases");
        return;
      }

      const list = CJ.el("div", { class: "tc-list" });
      let opened = false;

      (data.cases || []).forEach(function (c, i) {
        const pass = c.status === "PASS";
        const card = CJ.el("div", { class: "tc-card" });

        const head = CJ.el("div", { class: "tc-card-head" }, [
          CJ.el("span", { class: "tc-check" + (pass ? "" : " is-fail"),
                          text: pass ? "✓" : "✕" }),
          CJ.el("span", { text: "Default Test Case " + (i + 1) }),
          CJ.el("span", { class: "tc-chev", text: "▾" }),
        ]);

        const body = CJ.el("div", { class: "tc-card-body" });
        body.appendChild(tcSection("⏱ Code Execution Details", [
          ["Time:", Math.round((c.execution_time || 0) * 1000) + " ms", true],
        ]));

        if (c.is_hidden) {
          body.appendChild(tcSection("</> Test Case Information", [
            ["", "Hidden testcase - input and expected output are not shown."],
          ]));
        } else {
          body.appendChild(tcSection("</> Test Case Information", [
            ["Input", c.input],
            ["Expected Output", c.expected],
            ["Actual Output", c.output],
          ]));
          body.appendChild(tcSection(">_ Console Output", [
            ["", c.output || "None"],
          ]));
        }
        body.appendChild(tcSection("⚠ Standard Error/Warning", [
          ["", c.error || "None"],
        ]));

        head.addEventListener("click", function () {
          card.classList.toggle("is-open");
        });
        card.appendChild(head);
        card.appendChild(body);

        if (!pass && !opened) { card.classList.add("is-open"); opened = true; }
        list.appendChild(card);
      });

      casesPanel.appendChild(list);
      tabs.activate("cases");
    }

    async function run() {
      busy(runBtn, true, "Running…");
      try {
        const useCustom = customToggle && customToggle.checked;
        const data = await CJ.api(cfg.runUrl, {
          method: "POST",
          body: {
            question_id: cfg.questionId,
            language: language,
            code: editor.getValue(),
            custom_input: useCustom ? customText.value : null,
          },
        });

        if (!data.compiled) {
          renderConsole('<div class="console console-error">' +
            CJ.escape(data.error || "Compilation failed") + "</div>");
          CJ.toast("Compilation error", "error");
        } else if (useCustom) {
          renderConsole('<div class="console">' +
            CJ.escape(data.output || "(no output)") +
            (data.error ? '\n<span class="console-error">' + CJ.escape(data.error) + "</span>" : "") +
            "</div>");
        } else {
          renderCases(data);
        }
      } catch (e) {
        CJ.toast(e.message, "error");
      } finally {
        busy(runBtn, false, "Compile and Test");
      }
    }

    async function doSubmit(after) {
      busy(submitBtn, true, "Submitting…");
      const sentLang = language, sentCode = editor.getValue();
      try {
        const data = await CJ.api(cfg.submitUrl, {
          method: "POST",
          body: {
            question_id: cfg.questionId,
            language: sentLang,
            code: sentCode,
          },
        });
        renderCases(data, true);
        submitted[sentLang] = sentCode;
        CJ.toast(
          data.verdict === "AC"
            ? "Accepted - all testcases passed"
            : "Submitted: " + data.passed + "/" + data.total + " passed",
          data.verdict === "AC" ? "ok" : "warn"
        );
        CJ.markSubmitted(cfg.questionId);
        if (after) after();
      } catch (e) {
        CJ.toast(e.message, "error");
      } finally {
        busy(submitBtn, false, "Submit Code");
      }
    }

    function submit() {
      CJ.confirm("Submit this question?",
        "Your latest code will be graded against all testcases, including hidden ones.",
        function () { doSubmit(); }, "Submit");
    }

    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        CJ.confirm("Reset your code?",
          "This replaces your " + language.toUpperCase() +
          " code with the original starter template. This cannot be undone.",
          function () {
            const base = (cfg.templates || {})[language] || "";
            editor.setValue(base);
            drafts[language] = base;
            delete submitted[language];
            autosave.touch();
            editor.focus();
            CJ.toast("Code reset to the starter template", "ok");
          }, "Reset");
      });
    }

    if (runBtn) runBtn.addEventListener("click", run);
    if (submitBtn) submitBtn.addEventListener("click", submit);

    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        run();
      }
    }, cfg.signal ? { signal: cfg.signal } : false);
  };
})(window);
