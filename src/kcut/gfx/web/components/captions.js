"use strict";
// captions: the subtitles. One block of words, centered on x = 0.5 and on style.y, 0.87 of the
// width wide. The chunk on screen is the one that holds t; its active word is the last one that
// has begun. Everything is worked out from t, so the same t always gives the same picture.
(function () {
  const KC = window.KC;

  // The index of the chunk that holds second t, or -1. Chunks are in order and do not overlap.
  function find(chunks, t, fps) {
    let lo = 0;
    let hi = chunks.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (t < chunks[mid].s_f / fps) hi = mid - 1;
      else if (t >= chunks[mid].e_f / fps) lo = mid + 1;
      else return mid;
    }
    return -1;
  }

  KC.register("captions", {
    css: ".kc-cap{text-align:center;white-space:normal}" +
      ".kc-capw{display:inline-block;font-weight:900;letter-spacing:-1px;margin:0 9px;" +
      "paint-order:stroke fill;text-shadow:0 6px 18px rgba(0,0,0,.45)}",
    mount(root, cue, ctx) {
      const style = cue.params.style;
      const box = KC.el("div", "kc-abs kc-cap");
      const width = 0.87 * ctx.w;
      box.style.left = (ctx.w - width) / 2 + "px";
      box.style.width = width + "px";
      box.style.top = style.y * ctx.h + "px";
      box.style.display = "none";
      root.appendChild(box);
      return { box, key: -1, spans: [] };
    },
    update(state, cue, lt, t, ctx) {
      const style = cue.params.style;
      const at = find(cue.params.chunks, t, ctx.fps);
      state.box.style.display = at < 0 ? "none" : "";
      if (at < 0) {
        state.key = -1;
        return;
      }
      const chunk = cue.params.chunks[at];
      if (state.key !== at) {
        state.box.textContent = "";
        state.spans = chunk.words.map((word) => {
          const span = KC.el("span", "kc-capw", word.text);
          span.style.fontSize = style.font_px + "px";
          span.style.webkitTextStroke = "11px " + style.stroke_color;
          state.box.appendChild(span);
          return span;
        });
        state.key = at;
      }
      const t0 = chunk.s_f / ctx.fps;
      const grow = KC.outBack(KC.prog(t, t0, 0.14));
      state.box.style.opacity = KC.prog(t, t0, 0.06);
      state.box.style.transform = "translateY(-50%) scale(" + (0.86 + 0.14 * grow) + ")";
      let active = -1;
      chunk.words.forEach((word, i) => {
        if (word.s_f / ctx.fps <= t) active = i;
      });
      state.spans.forEach((span, i) => {
        const on = i === active;
        span.style.color = on ? style.active_color : style.color;
        const k = on ? KC.outBack(KC.prog(t, chunk.words[i].s_f / ctx.fps, 0.12)) : 0;
        span.style.transform = "scale(" + (1 + 0.07 * k) + ")";
      });
    },
  });
})();
