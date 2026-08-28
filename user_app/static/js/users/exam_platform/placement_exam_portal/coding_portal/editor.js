(function (window) {
  "use strict";

  const CJ = window.CJ;

  function Editor(textarea, gutter) {
    this.ta = textarea;
    this.gutter = gutter;
    this._onChange = null;
    this._undo = [];
    this._redo = [];
    this._cur = { v: textarea.value || "", s: 0, e: 0 };
    this._lastPush = 0;
    this._barrier = false;
    this._restoring = false;
    this._bind();
    this.refresh();
  }

  Editor.prototype._bind = function () {
    const self = this;

    this.ta.addEventListener("input", function () {
      self._track();
      self.refresh();
      if (self._onChange) self._onChange(self.getValue());
    });

    this.ta.addEventListener("scroll", function () {
      self.gutter.scrollTop = self.ta.scrollTop;
    });

    this.ta.addEventListener("paste", function (e) {
      const data = e.clipboardData || window.clipboardData;
      const text = data ? data.getData("text") : "";
      if (!text || text.indexOf("\n") === -1) return;
      const ta = self.ta;
      const start = ta.selectionStart, end = ta.selectionEnd;
      if (self.canEdit && !self.canEdit(start, end)) return;

      e.preventDefault();
      self.replaceRange(start, end,
                        window.CJ._reindentPaste(ta.value, start, text));
    });

    this.ta.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && !e.altKey) {
        const k = e.key.toLowerCase();
        if (k === "z" && !e.shiftKey) {
          e.preventDefault(); e.stopImmediatePropagation();
          self.undo(); return;
        }
        if (k === "y" || (k === "z" && e.shiftKey)) {
          e.preventDefault(); e.stopImmediatePropagation();
          self.redo(); return;
        }
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        self._indent(e.shiftKey);
      } else if (e.key === "Enter") {
        self._autoIndent(e);
      } else if (self._autoPair(e)) {
        self._reflowLine(e.key);
      } else if (e.key.length === 1 && e.key !== " " &&
                 !e.ctrlKey && !e.metaKey && !e.altKey) {
        const ta = self.ta;
        const pos = ta.selectionStart;
        if (pos !== ta.selectionEnd) return;
        if (self.canEdit && !self.canEdit(pos, pos)) return;
        const v = ta.value;
        const lineStart = v.lastIndexOf("\n", pos - 1) + 1;
        if (v.slice(lineStart, pos) !== "") return;
        const lineEnd = v.indexOf("\n", pos);
        const rest = v.slice(pos, lineEnd === -1 ? v.length : lineEnd);
        if (rest.trim() !== "") return;
        const indent = window.CJ._smartIndent(v, pos, self.pairLang);
        if (!indent) return;
        self.replaceRange(pos, pos, indent);
      }
      if (!e.defaultPrevented && e.key.length === 1) {
        setTimeout(function () { self._reflowLine(e.key); }, 0);
      }
    });
  };

  Editor.prototype._reflowLine = function (key) {
    if (key !== "}" && key !== ")" && key !== "]" &&
        !/[A-Za-z:]/.test(key)) return;
    const ta = this.ta;
    const pos = ta.selectionStart;
    if (pos !== ta.selectionEnd) return;
    const v = ta.value;
    const ls = v.lastIndexOf("\n", pos - 1) + 1;
    const lead = (v.slice(ls).match(/^[ \t]*/) || [""])[0];
    const token = v.slice(ls + lead.length, pos);
    if (!token || /\s/.test(token)) return;
    const le = v.indexOf("\n", pos);
    const rest = v.slice(pos, le === -1 ? v.length : le);
    if (rest.trim() !== "") return;

    const want = CJ._dedentFor(v, ls, token, this.pairLang);
    if (want === null || want === lead) return;
    if (this.canEdit && !this.canEdit(ls, ls + lead.length)) return;
    this.replaceRange(ls, ls + lead.length, want,
                      pos - lead.length + want.length);
  };

  const PAIR_OPEN = { "(": ")", "[": "]", "{": "}", '"': '"', "'": "'", "`": "`" };
  const PAIR_CLOSE = { ")": "(", "]": "[", "}": "{" };
  const PAIR_SKIP = { python: ["`"], sql: ["`", '"'], html: ["'"], css: ["'", "`"] };

  Editor.prototype._autoPair = function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    const ta = this.ta;
    const start = ta.selectionStart, end = ta.selectionEnd;
    const value = ta.value;

    if (e.key === "Backspace" && start === end) {
      const before = value.charAt(start - 1);
      if (PAIR_OPEN[before] && PAIR_OPEN[before] === value.charAt(start)) {
        if (this.canEdit && !this.canEdit(start - 1, start + 1)) return false;
        e.preventDefault();
        this.replaceRange(start - 1, start + 1, "");
        return true;
      }
      return false;
    }

    if (e.key.length !== 1) return false;
    if (this.canEdit && !this.canEdit(start, end)) return false;

    if (PAIR_CLOSE[e.key] && start === end && value.charAt(start) === e.key) {
      e.preventDefault();
      ta.selectionStart = ta.selectionEnd = start + 1;
      return true;
    }

    if (PAIR_CLOSE[e.key] && start === end) {
      const gap = value.slice(start).match(/^[ \t]*\n[ \t]*/);
      if (gap && value.charAt(start + gap[0].length) === e.key) {
        const ls = value.lastIndexOf("\n", start - 1) + 1;
        if (value.slice(ls, start).trim() === "") {
          e.preventDefault();
          const closerAt = start + gap[0].length;
          const closerLs = value.lastIndexOf("\n", closerAt - 1) + 1;
          const closerIndent = value.slice(closerLs, closerAt);
          if (this.canEdit && !this.canEdit(ls, closerAt + 1)) return false;
          this.replaceRange(ls, closerAt + 1, closerIndent + e.key);
          return true;
        }
      }
    }

    const close = PAIR_OPEN[e.key];
    if (!close) return false;
    if ((PAIR_SKIP[this.pairLang] || []).indexOf(e.key) !== -1) return false;

    if (start !== end) {
      const sel = value.slice(start, end);
      e.preventDefault();
      this.replaceRange(start, end, e.key + sel + close, start + 1 + sel.length);
      return true;
    }

    const prevCh = value.charAt(start - 1);
    const nextCh = value.charAt(start);
    if (e.key === close && nextCh === close) {
      e.preventDefault();
      ta.selectionStart = ta.selectionEnd = start + 1;
      return true;
    }
    if (e.key === close && /[A-Za-z0-9_]/.test(prevCh)) return false;
    if (/[A-Za-z0-9_]/.test(nextCh)) return false;

    e.preventDefault();
    this.replaceRange(start, end, e.key + close, start + 1);
    return true;
  };

  const TAB_W = 4;

  Editor.prototype._indent = function (outdent) {
    const ta = this.ta;
    const start = ta.selectionStart, end = ta.selectionEnd;
    const value = ta.value;

    if (start === end && !outdent) {
      if (this.canEdit && !this.canEdit(start, start)) {
        if (this.onDenied) this.onDenied();
        return;
      }
      const ls = value.lastIndexOf("\n", start - 1) + 1;
      const pad = TAB_W - ((start - ls) % TAB_W);
      this.replaceRange(start, end, new Array(pad + 1).join(" "));
      return;
    }

    if (start === end && outdent) {
      const ls = value.lastIndexOf("\n", start - 1) + 1;
      const lead = (value.slice(ls).match(/^ +/) || [""])[0];
      if (!lead.length) return;
      const cut = ((lead.length - 1) % TAB_W) + 1;
      if (this.canEdit && !this.canEdit(ls, ls + cut)) {
        if (this.onDenied) this.onDenied();
        return;
      }
      this.replaceRange(ls, ls + cut, "", Math.max(ls, start - cut));
      return;
    }

    const from = value.lastIndexOf("\n", start - 1) + 1;
    const to = value.indexOf("\n", end);
    const stop = to === -1 ? value.length : to;

    if (this.canEdit && !this.canEdit(from, stop)) {
      if (this.onDenied) this.onDenied();
      return;
    }

    const lines = value.slice(from, stop).split("\n");
    let replaced;
    if (outdent) {
      let common = null;
      lines.forEach(function (line) {
        if (line.trim() === "") return;
        const n = (line.match(/^ */) || [""])[0].length;
        common = common === null ? n : Math.min(common, n);
      });
      const cut = Math.min(common === null ? 0 : common, TAB_W);
      if (!cut) return;
      replaced = lines.map(function (line) {
        return line.slice(0, cut).trim() === "" ? line.slice(cut) : line;
      }).join("\n");
    } else {
      replaced = lines.map(function (line) {
        return line.trim() === "" ? line : "    " + line;
      }).join("\n");
    }

    this.replaceRange(from, stop, replaced);
    ta.selectionStart = from;
    ta.selectionEnd = from + replaced.length;
  };

  const PY_EXIT = /^[ \t]*(return|pass|break|continue|raise)\b/;

  CJ._smartIndent = function (value, pos, lang) {
    const lineStart = value.lastIndexOf("\n", pos - 1) + 1;
    const before = value.slice(lineStart, pos);
    if (before.trim() !== "") {
      const indent = (before.match(/^[ \t]*/) || [""])[0];
      if (/[{([:]\s*$/.test(before)) return indent + "    ";
      if (lang === "python" && PY_EXIT.test(before)) {
        return indent.slice(0, Math.max(0, indent.length - 4));
      }
      return indent;
    }
    let end = lineStart - 1;
    while (end > 0) {
      const prevStart = value.lastIndexOf("\n", end - 1) + 1;
      const prevLine = value.slice(prevStart, end);
      if (prevLine.trim() !== "") {
        const indent = (prevLine.match(/^[ \t]*/) || [""])[0];
        if (/[{([:]\s*$/.test(prevLine)) return indent + "    ";
        if (lang === "python" && PY_EXIT.test(prevLine)) {
          return indent.slice(0, Math.max(0, indent.length - 4));
        }
        return indent;
      }
      end = prevStart - 1;
    }
    return "";
  };

  const DEDENT_PY = /^(else|elif|except|finally|case|default)\b/;
  const CLOSERS = { "}": "{", ")": "(", "]": "[" };

  CJ._dedentFor = function (value, lineStart, token, lang) {
    if (CLOSERS[token]) {
      const open = CLOSERS[token], close = token;
      let depth = 0;
      for (let i = lineStart - 1; i >= 0; i--) {
        const c = value.charAt(i);
        if (c === close) depth++;
        else if (c === open) {
          if (depth === 0) {
            const ls = value.lastIndexOf("\n", i - 1) + 1;
            return (value.slice(ls).match(/^[ \t]*/) || [""])[0];
          }
          depth--;
        }
      }
      return null;
    }

    if (lang !== "python" || !DEDENT_PY.test(token)) return null;

    const OPENER = {
      else: /^(if|elif|for|while|try)\b/,
      elif: /^(if|elif)\b/,
      except: /^(try|except)\b/,
      finally: /^(try|except|else)\b/,
      case: /^(switch|case|match)\b/,
      default: /^(switch|case|match)\b/,
    };
    const kw = (token.match(/^[a-z]+/) || [""])[0];
    const want = OPENER[kw];
    if (!want) return null;

    const cur = (value.slice(lineStart).match(/^[ \t]*/) || [""])[0];
    let end = lineStart - 1;
    while (end > 0) {
      const prevStart = value.lastIndexOf("\n", end - 1) + 1;
      const prevLine = value.slice(prevStart, end);
      if (prevLine.trim() !== "") {
        const ind = (prevLine.match(/^[ \t]*/) || [""])[0];
        if (ind.length <= cur.length && want.test(prevLine.trim())) return ind;
      }
      end = prevStart - 1;
    }
    return null;
  };

  CJ._reindentPaste = function (value, pos, text) {
    text = text.replace(/\r\n?/g, "\n");
    const lines = text.split("\n");
    if (lines.length === 1) return text;

    const lineStart = value.lastIndexOf("\n", pos - 1) + 1;
    const before = value.slice(lineStart, pos);
    const blockPaste = before.trim() === "";

    const target = blockPaste
      ? (before.length ? before : CJ._smartIndent(value, pos))
      : (before.match(/^[ \t]*/) || [""])[0];

    let common = null;
    for (let i = blockPaste ? 0 : 1; i < lines.length; i++) {
      if (lines[i].trim() === "") continue;
      const n = (lines[i].match(/^[ \t]*/) || [""])[0].length;
      common = common === null ? n : Math.min(common, n);
    }
    if (common === null) common = 0;

    return lines.map(function (line, i) {
      if (line.trim() === "") return "";
      if (i === 0 && !blockPaste) return line;
      const own = (line.match(/^[ \t]*/) || [""])[0].length;
      const rebased = line.slice(Math.min(common, own));
      if (i === 0 && before.length) return rebased;
      return target + rebased;
    }).join("\n");
  };

  Editor.prototype._autoIndent = function (e) {
    const ta = this.ta;
    const start = ta.selectionStart;
    if (start !== ta.selectionEnd) return;
    if (this.canEdit && !this.canEdit(start, start)) return;
    if (this.regionStart && start === this.regionStart() - 1) return;
    const value = ta.value;

    const OPEN = { "{": "}", "(": ")", "[": "]" };
    const prevCh = value.charAt(start - 1);
    if (OPEN[prevCh] && value.charAt(start) === OPEN[prevCh]) {
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      const base = (value.slice(lineStart, start).match(/^[ \t]*/) || [""])[0];
      e.preventDefault();
      e.stopImmediatePropagation();
      const body = "\n" + base + "    ";
      this.replaceRange(start, start, body + "\n" + base,
                        start + body.length);
      return;
    }

    const indent = CJ._smartIndent(value, start, this.pairLang);
    if (!indent) return;

    e.preventDefault();
    e.stopImmediatePropagation();
    this.replaceRange(start, ta.selectionEnd, "\n" + indent);
  };

  Editor.prototype.replaceRange = function (from, to, text, caret) {
    const ta = this.ta;
    ta.focus();
    ta.selectionStart = from;
    ta.selectionEnd = to;

    this._barrier = true;

    let native = false;
    if (text.indexOf("\n") === -1) {
      try {
        native = document.execCommand("insertText", false, text);
      } catch (err) {
        native = false;
      }
    }
    if (!native) {
      this._cur = { v: ta.value, s: from, e: to };
      const v = ta.value;
      ta.value = v.slice(0, from) + text + v.slice(to);
      ta.selectionStart = ta.selectionEnd = from + text.length;
      ta.dispatchEvent(new Event("input", { bubbles: true }));
    }

    this.refresh();

    if (caret !== undefined && caret !== null) {
      const pos = Math.max(0, Math.min(caret, ta.value.length));
      ta.selectionStart = ta.selectionEnd = pos;
    }
    return this;
  };

  Editor.prototype._track = function () {
    if (this._restoring) return;
    const st = { v: this.ta.value, s: this.ta.selectionStart,
                 e: this.ta.selectionEnd };
    if (this._cur === null) {
      this._cur = { v: "", s: 0, e: 0 };
    }
    if (this._cur.v === st.v) {
      this._cur = st;
      return;
    }
    const now = Date.now();
    const grew = st.v.length - this._cur.v.length;
    let boundary = false;
    if (grew === 1) {
      const ch = st.v.charAt(st.s - 1);
      const prev = this._cur.v.charAt(this._cur.s - 1);
      boundary = /[A-Za-z0-9_]/.test(ch) !== /[A-Za-z0-9_]/.test(prev);
      if (!boundary) {
        this._runLen = (this._runLen || 0) + 1;
        if (this._runLen >= 12) boundary = true;
      }
    }
    if (boundary || grew !== 1) this._runLen = 0;

    const structural =
      this._barrier ||
      Math.abs(grew) !== 1 ||
      boundary ||
      now - this._lastPush > 700;
    if (structural) {
      this._pushState(this._cur);
      this._lastPush = now;
    }
    this._barrier = false;
    this._redo.length = 0;
    this._cur = st;
  };

  Editor.prototype._pushState = function (st) {
    const top = this._undo[this._undo.length - 1];
    if (top && top.v === st.v) return;
    this._undo.push(st);
    if (this._undo.length > 200) this._undo.shift();
  };

  Editor.prototype._applyState = function (st) {
    this._restoring = true;
    this.ta.focus();
    this.ta.value = st.v;
    this.ta.selectionStart = st.s;
    this.ta.selectionEnd = st.e;
    this._cur = { v: st.v, s: st.s, e: st.e };
    this._lastPush = Date.now();
    this._lineCount = -1;
    this.refresh();
    this.ta.dispatchEvent(new Event("input", { bubbles: true }));
    this.ta.selectionStart = st.s;
    this.ta.selectionEnd = st.e;
    this._restoring = false;
  };

  Editor.prototype.undo = function () {
    if (!this._undo.length) return;
    const live = { v: this.ta.value, s: this.ta.selectionStart,
                   e: this.ta.selectionEnd };
    while (this._undo.length &&
           this._undo[this._undo.length - 1].v === live.v) {
      this._undo.pop();
    }
    if (!this._undo.length) return;
    this._redo.push(live);
    this._applyState(this._undo.pop());
  };

  Editor.prototype.redo = function () {
    if (!this._redo.length) return;
    this._undo.push({ v: this.ta.value, s: this.ta.selectionStart,
                      e: this.ta.selectionEnd });
    this._applyState(this._redo.pop());
  };

  Editor.prototype.refresh = function () {
    const lines = this.ta.value.split("\n").length;
    if (this._lineCount === lines) return;
    this._lineCount = lines;
    let html = "";
    for (let i = 1; i <= lines; i++) html += i + "<br>";
    this.gutter.innerHTML = html;
    this.gutter.scrollTop = this.ta.scrollTop;
  };

  Editor.prototype.getValue = function () { return this.ta.value; };

  Editor.prototype.setValue = function (v) {
    this.ta.value = v === null || v === undefined ? "" : v;
    this._undo = [];
    this._redo = [];
    this._cur = { v: this.ta.value, s: 0, e: 0 };
    this._lastPush = 0;
    this._barrier = false;
    this._lineCount = -1;
    this.refresh();
  };

  Editor.prototype.onChange = function (fn) { this._onChange = fn; };
  Editor.prototype.focus = function () { this.ta.focus(); };

  CJ.Editor = Editor;

  CJ.mountEditor = function (wrapSel) {
    const wrap = CJ.$(wrapSel);
    if (!wrap) return null;
    return new Editor(CJ.$(".editor-input", wrap), CJ.$(".editor-gutter", wrap));
  };
})(window);

(function (window) {
  "use strict";

  const CJ = window.CJ;

  CJ.initSplitter = function (handleSel, paneSel, signal) {
    const handle = CJ.$(handleSel);
    const pane = CJ.$(paneSel);
    if (!handle || !pane) return;
    const opts = signal ? { signal: signal } : undefined;
    const passiveOpts = signal ? { passive: true, signal: signal } : { passive: true };

    let dragging = false, startY = 0, startH = 0;

    handle.addEventListener("mousedown", function (e) {
      dragging = true;
      startY = e.clientY;
      startH = pane.offsetHeight;
      handle.classList.add("is-dragging");
      document.body.style.userSelect = "none";
      e.preventDefault();
    }, opts);

    window.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      const h = startH + (startY - e.clientY);
      const max = Math.floor(window.innerHeight * 0.72);
      pane.style.height = Math.min(max, Math.max(88, h)) + "px";
    }, opts);

    window.addEventListener("mouseup", function () {
      if (!dragging) return;
      dragging = false;
      handle.classList.remove("is-dragging");
      document.body.style.userSelect = "";
    }, opts);

    handle.addEventListener("touchstart", function (e) {
      dragging = true;
      startY = e.touches[0].clientY;
      startH = pane.offsetHeight;
    }, passiveOpts);
    window.addEventListener("touchmove", function (e) {
      if (!dragging) return;
      const h = startH + (startY - e.touches[0].clientY);
      pane.style.height = Math.min(Math.floor(window.innerHeight * 0.72),
                                   Math.max(88, h)) + "px";
    }, passiveOpts);
    window.addEventListener("touchend", function () { dragging = false; }, opts);
  };
})(window);

(function (window) {
  "use strict";

  const CJ = window.CJ;
  const MAX_ITEMS = 8;

  const SNIPPETS = {
    python: {
      for: "for i in range($0):\n    pass",
      forin: "for item in $0:\n    pass",
      while: "while $0:\n    pass",
      if: "if $0:\n    pass",
      ifelse: "if $0:\n    pass\nelse:\n    pass",
      def: "def $0():\n    pass",
      class: "class $0:\n    def __init__(self):\n        pass",
      try: "try:\n    $0\nexcept Exception as e:\n    pass",
      with: "with open($0) as f:\n    pass",
      main: "if __name__ == \"__main__\":\n    $0",
    },
    java: {
      for: "for ($0) {\n    \n}",
      fori: "for (int i = 0; i < n; i++) {\n    $0\n}",
      forr: "for (int i = $0; i >= 0; i--) {\n    \n}",
      foreach: "for (int x : $0) {\n    \n}",
      while: "while ($0) {\n    \n}",
      if: "if ($0) {\n    \n}",
      ifelse: "if ($0) {\n    \n} else {\n    \n}",
      switch: "switch ($0) {\n    case 1:\n        break;\n    default:\n        break;\n}",
      try: "try {\n    $0\n} catch (Exception e) {\n    \n}",
      sout: "System.out.println($0);",
      main: "public static void main(String[] args) {\n    $0\n}",
    },
    c: {
      for: "for ($0) {\n    \n}",
      fori: "for (int i = 0; i < n; i++) {\n    $0\n}",
      while: "while ($0) {\n    \n}",
      if: "if ($0) {\n    \n}",
      ifelse: "if ($0) {\n    \n} else {\n    \n}",
      switch: "switch ($0) {\n    case 1:\n        break;\n    default:\n        break;\n}",
      printf: "printf(\"$0\\n\");",
      scanf: "scanf(\"%d\", &$0);",
      main: "int main() {\n    $0\n    return 0;\n}",
    },
    cpp: {
      for: "for ($0) {\n    \n}",
      fori: "for (int i = 0; i < n; i++) {\n    $0\n}",
      foreach: "for (auto& x : $0) {\n    \n}",
      while: "while ($0) {\n    \n}",
      if: "if ($0) {\n    \n}",
      ifelse: "if ($0) {\n    \n} else {\n    \n}",
      switch: "switch ($0) {\n    case 1:\n        break;\n    default:\n        break;\n}",
      cout: "cout << $0 << endl;",
      cin: "cin >> $0;",
      vector: "vector<int> $0;",
      main: "int main() {\n    $0\n    return 0;\n}",
    },
    csharp: {
      for: "for ($0) {\n    \n}",
      fori: "for (int i = 0; i < n; i++) {\n    $0\n}",
      foreach: "foreach (var x in $0) {\n    \n}",
      while: "while ($0) {\n    \n}",
      if: "if ($0) {\n    \n}",
      ifelse: "if ($0) {\n    \n} else {\n    \n}",
      switch: "switch ($0) {\n    case 1:\n        break;\n    default:\n        break;\n}",
      try: "try {\n    $0\n} catch (Exception e) {\n    \n}",
      cw: "Console.WriteLine($0);",
      main: "static void Main() {\n    $0\n}",
    },
    javascript: {
      for: "for ($0) {\n    \n}",
      fori: "for (let i = 0; i < n; i++) {\n    $0\n}",
      forof: "for (const x of $0) {\n    \n}",
      while: "while ($0) {\n    \n}",
      if: "if ($0) {\n    \n}",
      ifelse: "if ($0) {\n    \n} else {\n    \n}",
      switch: "switch ($0) {\n    case 1:\n        break;\n    default:\n        break;\n}",
      try: "try {\n    $0\n} catch (e) {\n    \n}",
      function: "function $0() {\n    \n}",
      arrow: "const $0 = () => {\n    \n};",
      log: "console.log($0);",
      map: "$0.map((x) => x);",
    },
    sql: {
      select: "SELECT $0\nFROM \nWHERE ;",
      join: "SELECT $0\nFROM a\nJOIN b ON a.id = b.a_id;",
      groupby: "SELECT $0, COUNT(*)\nFROM \nGROUP BY ;",
      orderby: "SELECT $0\nFROM \nORDER BY  DESC;",
      case: "CASE WHEN $0 THEN  ELSE  END",
    },
    html: {
      div: "<div class=\"$0\">\n    \n</div>",
      ul: "<ul>\n    <li>$0</li>\n</ul>",
      table: "<table>\n    <tr>\n        <td>$0</td>\n    </tr>\n</table>",
      form: "<form>\n    <input type=\"text\" id=\"$0\">\n</form>",
      a: "<a href=\"$0\"></a>",
      img: "<img src=\"$0\" alt=\"\">",
    },
    css: {
      flex: "display: flex;\nalign-items: center;\njustify-content: $0;",
      grid: "display: grid;\ngrid-template-columns: $0;\ngap: 10px;",
      media: "@media (max-width: $0px) {\n    \n}",
      transition: "transition: $0 .15s ease;",
    },
  };

  CJ.attachAutocomplete = function (editor, getWords, getLang) {
    if (!editor) return;
    const ta = editor.ta;
    const wrap = ta.parentElement;

    const pop = document.createElement("div");
    pop.className = "ac-pop";
    wrap.appendChild(pop);

    let items = [], sel = 0, open = false, wordStart = 0;
    let suppress = false;
    let charW = 0;

    function measureCharWidth() {
      const probe = document.createElement("span");
      probe.style.cssText =
        "position:absolute;visibility:hidden;white-space:pre;font:" +
        getComputedStyle(ta).font;
      probe.textContent = "MMMMMMMMMM";
      wrap.appendChild(probe);
      charW = probe.offsetWidth / 10 || 7.5;
      probe.remove();
    }

    function close() {
      open = false;
      pop.style.display = "none";
    }

    function currentWord() {
      const pos = ta.selectionStart;
      const match = ta.value.slice(0, pos).match(/[A-Za-z_][A-Za-z0-9_]*$/);
      if (!match) return null;
      wordStart = pos - match[0].length;
      return match[0];
    }

    function bufferWords() {
      return ta.value.match(/[A-Za-z_][A-Za-z0-9_]{2,}/g) || [];
    }

    function render() {
      pop.innerHTML = "";
      const snips = snippets();
      items.forEach(function (word, i) {
        const row = document.createElement("div");
        row.className = "ac-item" + (i === sel ? " is-sel" : "");
        row.textContent = word;
        if (snips[word]) {
          const prev = document.createElement("span");
          prev.className = "ac-prev";
          let p = snips[word].split("\n")[0].replace("$0", "");
          if (p.length > 32) p = p.slice(0, 31) + "…";
          prev.textContent = p;
          row.appendChild(prev);

          const tag = document.createElement("span");
          tag.className = "ac-tag";
          tag.textContent = "snippet";
          row.appendChild(tag);
        }
        row.addEventListener("mousedown", function (e) {
          e.preventDefault();
          accept(i);
        });
        pop.appendChild(row);
      });
    }

    function position() {
      if (!charW) measureCharWidth();
      const before = ta.value.slice(0, ta.selectionStart);
      const lines = before.split("\n");
      const line = lines.length - 1;
      const col = lines[lines.length - 1].length;
      const lineHeight = 20;
      const gutterW = editor.gutter ? editor.gutter.offsetWidth : 44;

      let top = 10 + (line + 1) * lineHeight - ta.scrollTop;
      let left = gutterW + 12 + col * charW - ta.scrollLeft;
      top = Math.max(4, Math.min(top, wrap.clientHeight - 40));
      left = Math.max(gutterW, Math.min(left, wrap.clientWidth - 170));
      pop.style.top = top + "px";
      pop.style.left = left + "px";
    }

    function show() {
      if (suppress) { suppress = false; close(); return; }
      const word = currentWord();
      if (!word) { close(); return; }

      const lower = word.toLowerCase();
      const snips = snippets();
      const pool = new Set(Object.keys(snips));
      (getWords() || []).forEach(w => pool.add(w));
      bufferWords().forEach(w => pool.add(w));

      items = [];
      pool.forEach(function (w) {
        if (w.toLowerCase().indexOf(lower) !== 0) return;
        if (w === word && !snips[w]) return;
        items.push(w);
      });
      items.sort(function (a, b) {
        const sa = snips[a] ? 0 : 1, sb = snips[b] ? 0 : 1;
        return sa - sb || a.length - b.length || a.localeCompare(b);
      });
      items = items.slice(0, MAX_ITEMS);

      if (!items.length) { close(); return; }
      sel = 0;
      render();
      position();
      open = true;
      pop.style.display = "block";
    }

    function snippets() {
      return (getLang && SNIPPETS[getLang()]) || {};
    }

    function accept(index) {
      const word = items[index === undefined ? sel : index];
      if (!word) return;

      const pos = ta.selectionStart;
      const snip = snippets()[word];
      let insert, caret;

      if (snip) {
        const lineStart = ta.value.lastIndexOf("\n", wordStart - 1) + 1;
        const indent = (ta.value.slice(lineStart, wordStart).match(/^\s*/) || [""])[0];
        insert = snip.split("\n").join("\n" + indent);

        const marker = insert.indexOf("$0");
        if (marker === -1) {
          caret = wordStart + insert.length;
        } else {
          insert = insert.replace("$0", "");
          caret = wordStart + marker;
        }
      } else {
        insert = word;
        caret = wordStart + word.length;
      }

      suppress = true;
      close();
      editor.replaceRange(wordStart, pos, insert, caret);
    }

    ta.addEventListener("input", function () {
      if (editor._restoring) { close(); return; }
      show();
    });
    ta.addEventListener("click", close);
    ta.addEventListener("scroll", close);
    ta.addEventListener("blur", function () { setTimeout(close, 150); });

    wrap.addEventListener("keydown", function (e) {
      if (!open) return;
      if ((e.ctrlKey || e.metaKey) && !e.altKey) { close(); return; }
      if (e.key === "ArrowDown") {
        sel = (sel + 1) % items.length; render();
      } else if (e.key === "ArrowUp") {
        sel = (sel - 1 + items.length) % items.length; render();
      } else if (e.key === "Enter" || e.key === "Tab") {
        accept();
      } else if (e.key === "Escape") {
        close();
      } else {
        return;
      }
      e.preventDefault();
      e.stopImmediatePropagation();
    }, true);
  };
})(window);

(function (window) {
  "use strict";

  const CJ = window.CJ;

  CJ.initVSplitter = function (handleSel, leftSel, storeKey, signal, mins) {
    const handle = CJ.$(handleSel);
    const left = CJ.$(leftSel);
    if (!handle || !left) return;
    const opts = signal ? { signal: signal } : undefined;
    const passiveOpts = signal ? { passive: true, signal: signal } : { passive: true };

    const body = left.parentElement;
    const MIN_LEFT = (mins && mins.left) || 240;
    const MIN_RIGHT = (mins && mins.right) || 320;

    function clamp(px) {
      const total = body.clientWidth - handle.offsetWidth;
      return Math.max(MIN_LEFT, Math.min(px, total - MIN_RIGHT));
    }

    function apply(px) {
      left.style.flex = "0 0 " + clamp(px) + "px";
    }

    if (storeKey) {
      const saved = parseInt(sessionStorage.getItem(storeKey) || "", 10);
      if (saved > 0) apply(saved);
    }

    let dragging = false;

    function move(clientX) {
      if (!dragging) return;
      const px = clamp(clientX - body.getBoundingClientRect().left);
      left.style.flex = "0 0 " + px + "px";
      if (storeKey) sessionStorage.setItem(storeKey, String(px));
    }

    handle.addEventListener("mousedown", function (e) {
      dragging = true;
      handle.classList.add("is-dragging");
      document.body.style.userSelect = "none";
      document.body.style.cursor = "col-resize";
      e.preventDefault();
    }, opts);

    window.addEventListener("mousemove", function (e) { move(e.clientX); }, opts);

    window.addEventListener("mouseup", function () {
      if (!dragging) return;
      dragging = false;
      handle.classList.remove("is-dragging");
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    }, opts);

    handle.addEventListener("touchstart", function () { dragging = true; },
                            passiveOpts);
    window.addEventListener("touchmove", function (e) {
      if (dragging && e.touches.length === 1) move(e.touches[0].clientX);
    }, passiveOpts);
    window.addEventListener("touchend", function () { dragging = false; }, opts);

    handle.addEventListener("dblclick", function () {
      left.style.flex = "";
      if (storeKey) sessionStorage.removeItem(storeKey);
    }, opts);

    window.addEventListener("resize", function () {
      if (left.style.flex) apply(left.getBoundingClientRect().width);
    }, opts);
  };
})(window);

(function (window) {
  "use strict";

  const CJ = window.CJ;

  const START_RE = /^[ \t]*(?:\/\/|#|--)[ \t]*(?:YOUR CODE START|Write code here|WRITE CODE HERE|Your code here)\b.*$/im;
  const END_RE = /^[ \t]*(?:\/\/|#|--)[ \t]*(?:YOUR CODE END|END CODE)\b.*$/im;

  CJ._computeRegion = function (value) {
    const s = value.match(START_RE);
    const e = value.match(END_RE);
    if (!s || !e) return null;
    const from = s.index + s[0].length + 1;
    const to = e.index - 1;
    return to >= from ? { from: from, to: to } : null;
  };

  CJ.attachGuards = function (editor, opts) {
    opts = opts || {};
    const ta = editor.ta;
    let locked = !!opts.readOnlyRegions;
    editor.pairLang = opts.language || "";

    let hadRegion = !!CJ._computeRegion(ta.value);

    const origSetValue = editor.setValue.bind(editor);
    editor.setValue = function (v) {
      origSetValue(v);
      hadRegion = !!CJ._computeRegion(ta.value);
    };

    function region() {
      if (!locked) return null;
      const r = CJ._computeRegion(ta.value);
      if (r) return r;
      if (hadRegion) return { from: -1, to: -1 };
      return null;
    }

    function inRegion(pos, r) {
      return r && pos >= r.from && pos <= r.to;
    }

    function selectionAllowed(r) {
      return inRegion(ta.selectionStart, r) && inRegion(ta.selectionEnd, r);
    }

    function warn() {
      if (warn._t) return;
      warn._t = setTimeout(function () { warn._t = null; }, 1000);
      CJ.toast("This part of the code is read-only", "warn");
    }


    ta.addEventListener("keydown", function (e) {
      const r = region();
      if (!r) return;

      const nav = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home",
                   "End", "PageUp", "PageDown", "Shift", "Control", "Alt",
                   "Meta", "Escape"];
      if (nav.indexOf(e.key) !== -1) return;
      if (e.key === "Tab") return;
      if ((e.ctrlKey || e.metaKey) && !e.altKey &&
          "zy".indexOf(e.key.toLowerCase()) !== -1) {
        return;
      }
      if ((e.ctrlKey || e.metaKey) && "acx".indexOf(e.key.toLowerCase()) !== -1) {
        if (e.key.toLowerCase() === "x" && !selectionAllowed(r)) {
          e.preventDefault(); warn();
        }
        return;
      }

      const start = ta.selectionStart, end = ta.selectionEnd;

      if (e.key === "Enter" && start === end && start === r.from - 1) {
        e.preventDefault();
        const nl = ta.value.indexOf("\n", r.from);
        const lineEnd = nl === -1 ? ta.value.length : nl;
        const lineTxt = ta.value.slice(r.from, lineEnd);
        if (lineTxt.trim() === "") {
          const ind = CJ._smartIndent(ta.value, r.from);
          editor.replaceRange(r.from, lineEnd, ind);
        } else {
          const ws = (lineTxt.match(/^[ \t]*/) || [""])[0];
          ta.selectionStart = ta.selectionEnd = r.from + ws.length;
        }
        return;
      }

      if (e.key === "Backspace" && start === end && start <= r.from) {
        e.preventDefault(); warn(); return;
      }
      if (e.key === "Delete" && start === end && start >= r.to) {
        e.preventDefault(); warn(); return;
      }
      if (!selectionAllowed(r)) {
        e.preventDefault(); warn(); return;
      }

    });

    ta.addEventListener("paste", function (e) {
      const r = region();
      if (r && !selectionAllowed(r)) { e.preventDefault(); warn(); }
    });

    ta.addEventListener("cut", function (e) {
      const r = region();
      if (r && !selectionAllowed(r)) { e.preventDefault(); warn(); }
    });

    ta.addEventListener("drop", function (e) {
      if (region()) { e.preventDefault(); warn(); }
    });

    editor.canEdit = function (start, end) {
      const r = region();
      return !r || (start >= r.from && end <= r.to);
    };

    editor.regionStart = function () {
      const r = region();
      return r ? r.from : -1;
    };

    editor.onDenied = warn;

    return {
      setLanguage: function (l) { editor.pairLang = l; },
      setLocked: function (on) { locked = !!on; },
      region: region,
    };
  };
})(window);

(function (window) {
  "use strict";

  const CJ = window.CJ;

  const KEYWORDS = {
    python: "def return if elif else for while break continue pass import from as class try except finally raise with yield lambda global nonlocal in is not and or None True False assert del print input range len",
    javascript: "function return if else for while do switch case break continue const let var new class extends this typeof instanceof try catch finally throw async await of in null undefined true false import export default delete void",
    java: "public private protected static final void class interface abstract extends implements new return if else for while do switch case break continue try catch finally throw throws import package this super null true false int long double float boolean char byte short enum instanceof",
    c: "int long double float char void unsigned signed short return if else for while do switch case break continue struct typedef sizeof const static extern goto union enum",
    cpp: "int long double float char bool void unsigned signed short return if else for while do switch case break continue struct class public private protected new delete const static template typename namespace using auto virtual override true false nullptr try catch throw enum",
    csharp: "public private protected static void class interface namespace using new return if else for foreach while do switch case break continue int long double float bool char string var try catch finally throw true false null this base readonly enum",
    sql: "select from where order by group having limit offset join inner left right outer on as and or not in between like is null distinct count sum avg min max asc desc union all case when then else end exists with insert update delete values set create table",
    css: "",
    html: "",
  };
  const SETS = {};
  Object.keys(KEYWORDS).forEach(function (k) {
    SETS[k] = new Set(KEYWORDS[k].split(" ").filter(Boolean));
  });

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function span(cls, text) {
    return '<span class="' + cls + '">' + esc(text) + "</span>";
  }

  function word(w, lang) {
    const set = SETS[lang] || SETS.javascript;
    const probe = lang === "sql" ? w.toLowerCase() : w;
    if (set.has(probe)) return span("tk", w);
    if (/^[A-Z]/.test(w) && lang !== "sql") return span("tt", w);
    return esc(w);
  }

  const FAMILY_RE = {
    clike: /(\/\/[^\n]*|\/\*[\s\S]*?(?:\*\/|$))|("(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?|`(?:[^`\\]|\\[\s\S])*`?)|(\b\d[\w.]*)|([A-Za-z_]\w*)(?=\s*\()|([A-Za-z_]\w*)/g,
    python: /((?:"""[\s\S]*?(?:"""|$))|(?:'''[\s\S]*?(?:'''|$))|#[^\n]*)|("(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?)|(\b\d[\w.]*)|([A-Za-z_]\w*)(?=\s*\()|([A-Za-z_]\w*)/g,
    sql: /(--[^\n]*|\/\*[\s\S]*?(?:\*\/|$))|('(?:[^'\\\n]|\\.)*'?|"(?:[^"\\\n]|\\.)*"?|`[^`\n]*`?)|(\b\d[\w.]*)|([A-Za-z_]\w*)(?=\s*\()|([A-Za-z_]\w*)/g,
  };

  function tokenizeCode(src, lang, family) {
    const re = FAMILY_RE[family];
    re.lastIndex = 0;
    let out = "", last = 0, m;
    while ((m = re.exec(src)) !== null) {
      out += esc(src.slice(last, m.index));
      if (m[1] !== undefined) out += span("tc", m[1]);
      else if (m[2] !== undefined) out += span("ts", m[2]);
      else if (m[3] !== undefined) out += span("tn", m[3]);
      else if (m[4] !== undefined) {
        const set = SETS[lang] || SETS.javascript;
        const probe = lang === "sql" ? m[4].toLowerCase() : m[4];
        out += set.has(probe) ? span("tk", m[4]) : span("tf", m[4]);
      } else out += word(m[5], lang);
      last = re.lastIndex;
    }
    return out + esc(src.slice(last));
  }

  function tokenizeHtml(src) {
    let out = "", last = 0, m;
    const re = /(<!--[\s\S]*?(?:-->|$))|(<\/?[A-Za-z][^>]*>?)/g;
    while ((m = re.exec(src)) !== null) {
      out += esc(src.slice(last, m.index));
      if (m[1] !== undefined) {
        out += span("tc", m[1]);
      } else {
        const tag = m[2];
        let inner = "", il = 0, im;
        const ire = /("[^"]*"?|'[^']*'?)|(<\/?[A-Za-z][\w-]*)/g;
        while ((im = ire.exec(tag)) !== null) {
          inner += esc(tag.slice(il, im.index));
          inner += im[1] !== undefined ? span("ts", im[1]) : span("tk", im[2]);
          il = ire.lastIndex;
        }
        out += inner + esc(tag.slice(il));
      }
      last = re.lastIndex;
    }
    return out + esc(src.slice(last));
  }

  function tokenizeCss(src) {
    let out = "", last = 0, m;
    const re = /(\/\*[\s\S]*?(?:\*\/|$))|("[^"\n]*"?|'[^'\n]*'?)|(#[0-9a-fA-F]{3,8}\b|\b\d[\w%.]*)|([-\w]+)(?=\s*:)|([.#]?[-\w]+)(?=[^{}]*\{)/g;
    while ((m = re.exec(src)) !== null) {
      out += esc(src.slice(last, m.index));
      if (m[1] !== undefined) out += span("tc", m[1]);
      else if (m[2] !== undefined) out += span("ts", m[2]);
      else if (m[3] !== undefined) out += span("tn", m[3]);
      else if (m[4] !== undefined) out += span("tk", m[4]);
      else out += span("tt", m[5]);
      last = re.lastIndex;
    }
    return out + esc(src.slice(last));
  }

  CJ._tokenize = function (src, lang) {
    if (lang === "html") return tokenizeHtml(src);
    if (lang === "css") return tokenizeCss(src);
    if (lang === "python") return tokenizeCode(src, "python", "python");
    if (lang === "sql") return tokenizeCode(src, "sql", "sql");
    return tokenizeCode(src, lang, "clike");
  };

  CJ.attachHighlight = function (editor, getLang) {
    if (!editor) return null;
    const ta = editor.ta;
    const wrap = ta.parentElement;
    wrap.classList.add("has-highlight");

    const pre = document.createElement("pre");
    pre.className = "editor-highlight";
    pre.setAttribute("aria-hidden", "true");
    wrap.appendChild(pre);

    function render() {
      pre.innerHTML = CJ._tokenize(ta.value + "\n", getLang ? getLang() : "");
      const gw = editor.gutter ? editor.gutter.offsetWidth : 0;
      if (gw > 0) pre.style.left = gw + "px";
      sync();
    }

    function sync() {
      pre.scrollTop = ta.scrollTop;
      pre.scrollLeft = ta.scrollLeft;
    }

    ta.addEventListener("input", render);
    ta.addEventListener("scroll", sync);

    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(function () {
        if (editor.gutter && editor.gutter.offsetWidth > 0) {
          pre.style.left = editor.gutter.offsetWidth + "px";
          sync();
        }
      });
      ro.observe(wrap);
    }

    const origSetValue = editor.setValue.bind(editor);
    editor.setValue = function (v) {
      origSetValue(v);
      render();
    };

    render();
    return { render: render };
  };
})(window);
