"use strict";
// kinetic: up to four lines of big text, one block centered on y; each line pops in at its at_f.
(function () {
  const KC = window.KC;

  KC.register("kinetic", {
    css: "",
    mount(root, cue, ctx) {
      const p = cue.params;
      const total = p.lines.reduce((sum, line) => sum + line.size, 0) + p.gap_px * (p.lines.length - 1);
      let top = p.y * ctx.h - total / 2;
      const lines = p.lines.map((line) => {
        const node = KC.el("div", "kc-abs kc-big kc-stroke", line.text);
        node.style.left = ctx.w / 2 + "px";
        node.style.top = top + line.size / 2 + "px";
        node.style.fontSize = line.size + "px";
        node.style.color = line.color;
        node.style.fontStyle = p.italic ? "italic" : "normal";
        node.style.display = "none";
        root.appendChild(node);
        top += line.size + p.gap_px;
        return { node, t0: line.at_f / ctx.fps };
      });
      return { lines };
    },
    update(state, cue, lt, t, ctx) {
      const p = cue.params;
      const dur = (cue.end_f - cue.start_f) / ctx.fps;
      for (const line of state.lines) {
        const st = KC.pop(lt, line.t0, dur);
        line.node.style.display = st ? "" : "none";
        if (!st) continue;
        line.node.style.opacity = st.o;
        line.node.style.transform =
          "translate(-50%,-50%) scale(" + st.s + ") rotate(" + p.rotate_deg + "deg)";
        const g = 1 - KC.prog(lt, line.t0, 0.22);
        line.node.style.textShadow = p.glitch
          ? 14 * g + "px 0 0 rgba(255,0,80,.8), " + -14 * g + "px 0 0 rgba(0,220,255,.8)"
          : "none";
      }
    },
  });
})();
