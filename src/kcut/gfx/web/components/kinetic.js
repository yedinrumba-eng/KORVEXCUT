"use strict";
// kinetic: up to four lines of big text, one block centered on y; each line pops in at its at_f.
(function () {
  const KC = window.KC;

  KC.register("kinetic", {
    css: "",
    // Only where each line goes is worked out here: the node of a line is made on every seek, in
    // `update`, and only for the lines that are on screen (001.35, point 7).
    mount(root, cue, ctx) {
      const p = cue.params;
      const total = p.lines.reduce((sum, line) => sum + line.size, 0) + p.gap_px * (p.lines.length - 1);
      let top = p.y * ctx.h - total / 2;
      const lines = p.lines.map((line) => {
        const plan = { line, top: top + line.size / 2, t0: line.at_f / ctx.fps };
        top += line.size + p.gap_px;
        return plan;
      });
      return { root, lines };
    },
    update(state, cue, lt, t, ctx) {
      const p = cue.params;
      const dur = (cue.end_f - cue.start_f) / ctx.fps;
      // A node that is kept and changed from one seek to the next keeps its layer, and the pixels
      // of its edges depended on which frames were shown before (65 pixels apart at frames 12, 17
      // and 23 once `will-change` was gone from base.css). A new node has no earlier seek.
      state.root.replaceChildren();
      for (const plan of state.lines) {
        const st = KC.pop(lt, plan.t0, dur);
        if (!st) continue;
        const node = KC.el("div", "kc-abs kc-big kc-stroke", plan.line.text);
        node.style.left = ctx.w / 2 + "px";
        node.style.top = plan.top + "px";
        node.style.fontSize = plan.line.size + "px";
        node.style.color = plan.line.color;
        node.style.fontStyle = p.italic ? "italic" : "normal";
        node.style.opacity = st.o;
        node.style.transform =
          "translate(-50%,-50%) scale(" + st.s + ") rotate(" + p.rotate_deg + "deg)";
        const g = 1 - KC.prog(lt, plan.t0, 0.22);
        node.style.textShadow = p.glitch
          ? 14 * g + "px 0 0 rgba(255,0,80,.8), " + -14 * g + "px 0 0 rgba(0,220,255,.8)"
          : "none";
        state.root.appendChild(node);
      }
    },
  });
})();
