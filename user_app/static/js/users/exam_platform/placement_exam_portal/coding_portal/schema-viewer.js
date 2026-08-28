(function (window) {
  "use strict";

  const CJ = window.CJ;
  const MIN = 0.25, MAX = 4;

  function SchemaViewer(root, signal) {
    this.root = typeof root === "string" ? CJ.$(root) : root;
    if (!this.root) return;

    this.viewport = CJ.$(".schema-viewport", this.root);
    this.stage = CJ.$(".schema-stage", this.root);
    if (!this.viewport || !this.stage) return;

    this.scale = 1;
    this.x = 0;
    this.y = 0;
    this._bind(signal);
    this.apply();
  }

  SchemaViewer.prototype._bind = function (signal) {
    const self = this;
    const opts = signal ? { signal: signal } : undefined;

    CJ.$$("[data-zoom]", this.root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        const kind = btn.dataset.zoom;
        if (kind === "in") self.zoomBy(1.25);
        else if (kind === "out") self.zoomBy(0.8);
        else self.reset();
      }, opts);
    });

    let dragging = false, sx = 0, sy = 0, ox = 0, oy = 0;

    this.viewport.addEventListener("mousedown", function (e) {
      dragging = true;
      sx = e.clientX; sy = e.clientY;
      ox = self.x; oy = self.y;
      self.viewport.classList.add("is-panning");
      e.preventDefault();
    }, opts);

    window.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      self.x = ox + (e.clientX - sx);
      self.y = oy + (e.clientY - sy);
      self.apply();
    }, opts);

    window.addEventListener("mouseup", function () {
      dragging = false;
      self.viewport.classList.remove("is-panning");
    }, opts);

    this.viewport.addEventListener("wheel", function (e) {
      if (!e.ctrlKey) return;
      e.preventDefault();
      self.zoomBy(e.deltaY < 0 ? 1.12 : 0.89);
    }, { passive: false });

    let tx = 0, ty = 0, tox = 0, toy = 0;
    this.viewport.addEventListener("touchstart", function (e) {
      if (e.touches.length !== 1) return;
      tx = e.touches[0].clientX; ty = e.touches[0].clientY;
      tox = self.x; toy = self.y;
    }, { passive: true });

    this.viewport.addEventListener("touchmove", function (e) {
      if (e.touches.length !== 1) return;
      self.x = tox + (e.touches[0].clientX - tx);
      self.y = toy + (e.touches[0].clientY - ty);
      self.apply();
    }, { passive: true });
  };

  SchemaViewer.prototype.zoomBy = function (factor) {
    this.scale = Math.min(MAX, Math.max(MIN, this.scale * factor));
    this.apply();
  };

  SchemaViewer.prototype.reset = function () {
    this.scale = 1; this.x = 0; this.y = 0;
    this.apply();
  };

  SchemaViewer.prototype.apply = function () {
    this.stage.style.transform =
      "translate(" + this.x + "px," + this.y + "px) scale(" + this.scale + ")";
  };

  CJ.SchemaViewer = SchemaViewer;
})(window);
