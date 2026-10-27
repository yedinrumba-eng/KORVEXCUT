"use strict";
// title: big text, centered on (x, y), with a bar of color behind it that grows from the left.
(function () {
  const KC = window.KC;
  const PAD_X = 26;
  const PAD_Y = 6;

  KC.register("title", {
    css: ".kc-title-bar{position:absolute;left:0;border-radius:14px;transform-origin:left center}" +
      ".kc-title-text{position:relative}",
    mount(root, cue, ctx) {
      const p = cue.params;
      const box = KC.el("div", "kc-abs");
      box.style.left = p.x * ctx.w + "px";
      box.style.top = p.y * ctx.h + "px";
      box.style.padding = PAD_Y + "px " + PAD_X + "px";
      let bar = null;
      if (p.bar) {
        bar = KC.el("div", "kc-title-bar");
        bar.style.top = Math.round(0.136 * p.size) + "px";
        bar.style.width = "100%";
        bar.style.height = p.size + "px";
        bar.style.background = p.bar_color;
        box.appendChild(bar);
      }
      const text = KC.el("div", "kc-big kc-title-text" + (p.stroke ? " kc-stroke" : ""), p.text);
      text.style.fontSize = p.size + "px";
      text.style.color = p.color;
      box.appendChild(text);
      root.appendChild(box);
      return { box, bar };
    },
    update(state, cue, lt, t, ctx) {
      const st = KC.pop(lt, 0, (cue.end_f - cue.start_f) / ctx.fps, 0.2, 0.15);
      state.box.style.display = st ? "" : "none";
      if (!st) return;
      state.box.style.opacity = st.o;
      state.box.style.transform = "translate(-50%,-50%) scale(" + st.s + ")";
      if (state.bar) state.bar.style.transform = "scaleX(" + KC.outCubic(KC.prog(lt, 0, 0.32)) + ")";
    },
  });
})();
