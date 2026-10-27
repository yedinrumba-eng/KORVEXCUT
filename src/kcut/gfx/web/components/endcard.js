"use strict";
// endcard: up to three lines of big text and, under them, a call to action in a pill. The lines
// and the pill are one block centered on y: 10 px between lines, 24 px before the pill.
(function () {
  const KC = window.KC;
  const GAP = 10;
  const CTA_GAP = 24;
  const CTA_SIZE = 40;
  const CTA_HEIGHT = CTA_SIZE + 2 * Math.round(0.35 * CTA_SIZE);

  KC.register("endcard", {
    css: "",
    mount(root, cue, ctx) {
      const p = cue.params;
      const hasCta = typeof p.cta === "string" && p.cta !== "";
      const lines = p.lines.reduce((sum, line) => sum + line.size, 0) + GAP * (p.lines.length - 1);
      const total = lines + (hasCta ? CTA_GAP + CTA_HEIGHT : 0);
      let top = p.y * ctx.h - total / 2;
      const nodes = p.lines.map((line) => {
        const node = KC.el("div", "kc-abs kc-big kc-stroke", line.text);
        node.style.left = ctx.w / 2 + "px";
        node.style.top = top + line.size / 2 + "px";
        node.style.fontSize = line.size + "px";
        node.style.color = line.color;
        node.style.display = "none";
        root.appendChild(node);
        top += line.size + GAP;
        return { node, t0: line.at_f / ctx.fps };
      });
      let cta = null;
      if (hasCta) {
        const pill = KC.el("div", "kc-abs kc-pill", p.cta);
        pill.style.left = ctx.w / 2 + "px";
        pill.style.top = top - GAP + CTA_GAP + CTA_HEIGHT / 2 + "px";
        pill.style.fontSize = CTA_SIZE + "px";
        pill.style.color = ctx.brand.accent;
        pill.style.background = ctx.brand.dark;
        pill.style.boxShadow = "0 0 0 4px " + ctx.brand.accent + ", 0 10px 30px rgba(0,0,0,.4)";
        pill.style.display = "none";
        root.appendChild(pill);
        cta = { node: pill, t0: p.cta_at_f / ctx.fps };
      }
      return { nodes, cta };
    },
    update(state, cue, lt, t, ctx) {
      const dur = (cue.end_f - cue.start_f) / ctx.fps;
      for (const line of state.nodes) show(line, KC.pop(lt, line.t0, dur));
      if (state.cta) show(state.cta, KC.pop(lt, state.cta.t0, dur));
    },
  });

  function show(item, st) {
    item.node.style.display = st ? "" : "none";
    if (!st) return;
    item.node.style.opacity = st.o;
    item.node.style.transform = "translate(-50%,-50%) scale(" + st.s + ")";
  }
})();
