"use strict";
// label: a pill with a short text, centered on (x, y), with a ring of color and a shadow.
(function () {
  const KC = window.KC;

  KC.register("label", {
    css: "",
    mount(root, cue, ctx) {
      const p = cue.params;
      const pill = KC.el("div", "kc-abs kc-pill", p.text);
      pill.style.left = p.x * ctx.w + "px";
      pill.style.top = p.y * ctx.h + "px";
      pill.style.fontSize = p.size + "px";
      pill.style.color = p.fg;
      pill.style.background = p.bg;
      pill.style.boxShadow = "0 0 0 4px " + p.ring + ", 0 10px 30px rgba(0,0,0,.4)";
      root.appendChild(pill);
      return { pill };
    },
    update(state, cue, lt, t, ctx) {
      const st = KC.pop(lt, 0, (cue.end_f - cue.start_f) / ctx.fps);
      state.pill.style.display = st ? "" : "none";
      if (!st) return;
      state.pill.style.opacity = st.o;
      state.pill.style.transform = "translate(-50%,-50%) scale(" + st.s + ")";
    },
  });
})();
