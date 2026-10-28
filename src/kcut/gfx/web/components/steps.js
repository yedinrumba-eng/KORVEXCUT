"use strict";
// steps: the steps of a process on a dark panel near the top, one at a time. Step i is on screen
// from its at_f to the at_f of the next one (the last one, to the end of the cue), and pops in
// and out. Each panel has a badge with the label and the text of the step beside it.
(function () {
  const KC = window.KC;

  // "#RRGGBB" and an alpha as an rgba() color
  function rgba(hex, alpha) {
    const n = parseInt(hex.slice(1), 16);
    return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + alpha + ")";
  }

  // the panel of one step, popped as `st` says: the badge with its label and the text beside it
  function panel(p, item, st, ctx) {
    const box = KC.el("div", "kc-abs kc-steps");
    box.style.left = ctx.w / 2 + "px";
    box.style.top = p.y * ctx.h + "px";
    box.style.background = rgba(p.panel, 0.92);
    box.style.boxShadow = "0 0 0 3px " + p.ring + ", 0 10px 30px rgba(0,0,0,.4)";
    box.style.opacity = st.o;
    box.style.transform = "translate(-50%,-50%) scale(" + st.s + ")";
    const badge = KC.el("div", "kc-steps-badge", item.label);
    badge.style.background = p.badge;
    badge.style.color = ctx.brand.dark;
    const text = KC.el("div", "kc-steps-text", item.text);
    text.style.color = ctx.brand.light;
    box.appendChild(badge);
    box.appendChild(text);
    return box;
  }

  KC.register("steps", {
    css: ".kc-steps{display:flex;align-items:center;gap:20px;padding:14px 30px 14px 18px;" +
      "border-radius:22px}" +
      ".kc-steps-badge{font-weight:900;font-size:30px;line-height:1;padding:10px 18px;" +
      "border-radius:14px;letter-spacing:.5px}" +
      ".kc-steps-text{font-weight:800;font-size:42px;line-height:1.1}",
    // Nothing is built here: the panel of the step that is on screen is made on every seek.
    mount(root, cue, ctx) {
      return { root };
    },
    update(state, cue, lt, t, ctx) {
      const p = cue.params;
      const end = (cue.end_f - cue.start_f) / ctx.fps;
      // A panel that is kept and changed from one seek to the next keeps its layer, and Chromium
      // draws its soft shadow from an earlier seek: the same time then gave pixels that differ
      // depending on which frames were shown before (001.34, row 4; measured: all of 9 frames, in
      // three orders). A new panel has no earlier seek, so the picture depends on the time alone.
      state.root.replaceChildren();
      p.items.forEach((item, i) => {
        const next = i + 1 < p.items.length ? p.items[i + 1].at_f / ctx.fps : end;
        const st = KC.pop(lt, item.at_f / ctx.fps, next, 0.18, 0.1);
        if (st) state.root.appendChild(panel(p, item, st, ctx));
      });
    },
  });
})();
