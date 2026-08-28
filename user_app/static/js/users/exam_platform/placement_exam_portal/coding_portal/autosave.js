(function (window) {
  "use strict";

  const CJ = window.CJ;

  function Autosave(opts) {
    this.url = opts.url;
    this.getPayload = opts.getPayload;
    this.label = CJ.$("#save-state-text");
    this.lastSaved = null;
    this.pending = false;

    const self = this;
    this.schedule = CJ.debounce(function () { self.save(); }, opts.delay || 1200);

    const tickId = setInterval(function () { self._tick(); }, 1000);
    if (opts.signal) {
      opts.signal.addEventListener("abort", function () { clearInterval(tickId); });
    }

    window.addEventListener("beforeunload", function () {
      if (!self.pending) return;
      try {
        const body = new Blob(
          [JSON.stringify(self.getPayload())],
          { type: "application/json" }
        );
        navigator.sendBeacon(self.url + "?csrf=" + encodeURIComponent(CJ.csrfToken()), body);
      } catch (e) {  }
    }, opts.signal ? { signal: opts.signal } : false);
  }

  Autosave.prototype.touch = function () {
    this.pending = true;
    this._render("Saving…");
    this.schedule();
  };

  Autosave.prototype.save = async function (force) {
    if (!this.pending && !force) return true;
    try {
      await CJ.api(this.url, { method: "POST", body: this.getPayload() });
      this.pending = false;
      this.lastSaved = Date.now();
      this._tick();
      return true;
    } catch (e) {
      this._render("Not saved");
      CJ.toast("Could not save your draft: " + e.message, "error");
      return false;
    }
  };

  Autosave.prototype._tick = function () {
    if (this.pending || !this.lastSaved) return;
    const secs = Math.floor((Date.now() - this.lastSaved) / 1000);
    if (secs < 5) this._render("Saved: just now");
    else if (secs < 60) this._render("Saved: " + secs + " seconds ago");
    else {
      const mins = Math.floor(secs / 60);
      this._render("Saved: " + mins + " minute" + (mins > 1 ? "s" : "") + " ago");
    }
  };

  Autosave.prototype._render = function (text) {
    if (this.label) this.label.textContent = text;
  };

  CJ.Autosave = Autosave;
})(window);
