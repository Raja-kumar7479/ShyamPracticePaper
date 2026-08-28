(function (window) {
  "use strict";

  const CJ = window.CJ;

  function Timer(opts) {
    this.nodes = CJ.$$(opts.selector || "#section-timer");
    this.onExpire = opts.onExpire;
    this.expired = false;

    // A missing / non-numeric remaining must NEVER be treated as "0 seconds
    // left", or the very first tick would fire onExpire and auto-submit the
    // exam without the candidate doing anything. In that case we show the
    // clock but arm no auto-expiry: only a real countdown that genuinely
    // reaches zero is allowed to end the test.
    var secs = Number(opts.remainingSeconds);
    this.valid = isFinite(secs) && secs > 0;
    this.remaining = this.valid ? Math.floor(secs) : 0;
    this.deadline = Date.now() + this.remaining * 1000;

    const self = this;
    this._id = setInterval(function () { self._tick(); }, 1000);
    this._tick();
  }

  Timer.prototype._tick = function () {
    const left = Math.max(0, Math.round((this.deadline - Date.now()) / 1000));
    this.remaining = left;
    this._render(left);

    // Auto-expiry only fires when a valid countdown actually reaches zero.
    if (this.valid && left <= 0 && !this.expired) {
      this.expired = true;
      clearInterval(this._id);
      if (this.onExpire) this.onExpire();
    }
  };

  Timer.prototype._render = function (secs) {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    const text =
      String(h).padStart(2, "0") + ":" +
      String(m).padStart(2, "0") + ":" +
      String(s).padStart(2, "0");

    this.nodes.forEach(function (node) {
      node.textContent = text;
      node.classList.toggle("is-low", secs <= 300 && secs > 60);
      node.classList.toggle("is-critical", secs <= 60);
    });
  };

  Timer.prototype.stop = function () { clearInterval(this._id); };

  CJ.Timer = Timer;
})(window);
