"use strict";
// kcut graphics runtime (spec S1.6a). The picture is a function of the time: window.seek(t) puts the
// page exactly as it must look at second t, with nothing that depends on a clock, on chance or on
// what was shown before. Components register themselves; the runtime mounts one layer for each cue
// and, on every seek, updates the ones that are on screen and hides the rest.
(function () {
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const prog = (t, t0, d) => (d > 0 ? clamp((t - t0) / d) : t >= t0 ? 1 : 0);
  const outCubic = (x) => 1 - Math.pow(1 - x, 3);
  const inCubic = (x) => x * x * x;
  const inOutCubic = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const outBack = (x) => {
    const c1 = 1.70158;
    const c3 = c1 + 1;
    return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
  };

  // Pop in at t0, hold, pop out until t1 (exclusive). null outside [t0, t1).
  function pop(t, t0, t1, inDur = 0.22, outDur = 0.16) {
    if (t < t0 || t >= t1) return null;
    const a = outBack(prog(t, t0, inDur));
    const b = prog(t, t1 - outDur, outDur);
    return { s: (0.6 + 0.4 * a) * (1 + 0.12 * b), o: clamp(prog(t, t0, 0.6 * inDur)) * (1 - inCubic(b)) };
  }

  // Park-Miller: the same numbers for the same seed, always.
  function rng(seed) {
    return () => {
      seed = (seed * 16807) % 2147483647;
      return seed / 2147483647;
    };
  }

  // The only way to put text in the page: createElement, className and textContent.
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  const defs = {};
  function register(id, def) {
    defs[id] = def;
  }

  let ctx = null;
  let layers = [];

  function imagesDecoded(images) {
    return Object.keys(images).map((rel) => {
      const img = new Image();
      img.src = images[rel];
      return img.decode();
    });
  }

  function start() {
    const data = JSON.parse(document.getElementById("kc-data").textContent);
    ctx = { fps: data.fps, w: data.w, h: data.h, brand: data.brand, images: data.images || {} };
    const style = document.documentElement.style;
    for (const name of Object.keys(ctx.brand)) style.setProperty("--kc-" + name, ctx.brand[name]);
    const root = document.getElementById("kc-root");
    root.style.width = ctx.w + "px";
    root.style.height = ctx.h + "px";
    const injected = {};
    layers = data.cues.map((cue) => {
      const def = defs[cue.component];
      if (!def) throw new Error("kcut: falta el componente " + cue.component);
      if (!injected[cue.component]) {
        injected[cue.component] = true;
        document.head.appendChild(el("style", "", def.css));
      }
      const layer = el("div", "kc-cue");
      layer.style.width = ctx.w + "px";
      layer.style.height = ctx.h + "px";
      layer.style.display = "none";
      root.appendChild(layer);
      return { cue, def, layer, state: def.mount(layer, cue, ctx) };
    });
    const loading = [
      document.fonts.load("600 16px Inter"),
      document.fonts.load("800 16px Inter"),
      document.fonts.load("900 16px Inter"),
      ...imagesDecoded(ctx.images),
    ];
    Promise.all(loading).then(() => {
      window.kcutReady = true;
    });
  }

  // The page as it looks at second t. Pure: the result depends only on t.
  function seek(t) {
    if (ctx === null) return true;
    for (const item of layers) {
      const t0 = item.cue.start_f / ctx.fps;
      const on = t0 <= t && t < item.cue.end_f / ctx.fps;
      item.layer.style.display = on ? "" : "none";
      if (on) item.def.update(item.state, item.cue, t - t0, t, ctx);
    }
    return true;
  }

  window.kcutReady = false;
  window.seek = seek;
  window.KC = { register, clamp, prog, outCubic, inCubic, inOutCubic, outBack, pop, rng, el };
  window.addEventListener("load", start);
})();
