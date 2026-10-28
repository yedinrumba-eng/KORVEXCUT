"use strict";
// sticker: an approved image (a mascot, a logo) with its feet on (x, y). It comes in dropping from
// above (squash on landing, rebound) or popping in, bobs while it stays, and leaves by popping out,
// by flying to another point or by just ending with the cue. A glow under the feet and seven
// sparkles (SVG, seeded) go with it. Everything is worked out from the time alone: the same
// time, the same picture. No blinking: this is the generic version.
(function () {
  const KC = window.KC;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const FALL = 0.24; // drop: falls DROP_PX in this time, stretched
  const SQUASH = 0.12; // drop: squashes on landing
  const REBOUND = 0.26; // drop: stretches back, hops a little and settles
  const SETTLED = FALL + SQUASH + REBOUND; // from here, the idle
  const POP_IN = 0.22; // the standard pop: when it is done coming in
  const DROP_PX = 430;
  const CROUCH = 0.15; // before the flight, it crouches this long
  const FADE = 0.12; // the flight ends, and the sticker fades out, in the last 0.12 s of the cue
  const ARC_PX = 300;
  const SPARKS = 7;
  const ONLY_IN = 1e9; // the end for KC.pop that never pops out

  function parts(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [n >> 16, (n >> 8) & 255, n & 255];
  }

  // "#RRGGBB" as an rgba() color, `lift` of the way to white (0 keeps it, 1 is white)
  function rgba(hex, alpha, lift = 0) {
    const mixed = parts(hex).map((v) => Math.round(v + (255 - v) * lift));
    return "rgba(" + mixed.join(",") + "," + alpha + ")";
  }

  // where the feet are at local time lt: on the path (straight between points, held before the
  // first and after the last) or, with no path, at (x, y)
  function feetAt(p, lt, ctx) {
    const pts = p.path;
    if (!pts || pts.length === 0) return { x: p.x * ctx.w, y: p.y * ctx.h };
    const f = lt * ctx.fps;
    let a = pts[0];
    let b = pts[0];
    for (let i = 1; i < pts.length && f > pts[i - 1].at_f; i++) {
      a = pts[i - 1];
      b = pts[i];
    }
    const k = b.at_f > a.at_f ? KC.clamp((f - a.at_f) / (b.at_f - a.at_f)) : 1;
    return { x: (a.x + (b.x - a.x) * k) * ctx.w, y: (a.y + (b.y - a.y) * k) * ctx.h };
  }

  // the way in and the idle: how far above its feet it is, how squashed, how turned, how visible
  function stand(p, lt) {
    const m = { dy: 0, sx: 1, sy: 1, ry: 0, rz: 0, o: 1 };
    let settled = POP_IN;
    if (p.enter === "drop") {
      settled = SETTLED;
      if (lt < FALL) {
        const u = lt / FALL;
        m.dy = -DROP_PX * (1 - u * u);
        m.sx = 0.9;
        m.sy = 1.12;
        m.o = KC.clamp(lt / 0.05);
      } else if (lt < FALL + SQUASH) {
        const k = Math.sin(((lt - FALL) / SQUASH) * Math.PI);
        m.sx = 1 + 0.24 * k;
        m.sy = 1 - 0.28 * k;
      } else if (lt < SETTLED) {
        const u = (lt - FALL - SQUASH) / REBOUND;
        const k = Math.sin(u * Math.PI);
        m.sx = 1 - 0.08 * k * (1 - u);
        m.sy = 1 + 0.14 * k * (1 - u);
        m.dy = -30 * k;
      }
    } else {
      const st = KC.pop(lt, 0, ONLY_IN, POP_IN);
      m.sx = st.s;
      m.sy = st.s;
      m.o = st.o;
    }
    if (lt >= settled && p.idle === "bob") {
      const ti = lt - settled;
      m.dy = -7 * (0.5 - 0.5 * Math.cos(6.2 * ti));
      m.ry = 18 * Math.sin(2.7 * ti);
      m.rz = 3 * Math.sin(3.6 * ti);
    }
    return m;
  }

  // the whole pose at local time lt: where the feet are and what the picture does there
  function pose(p, lt, dur, ctx) {
    const m = stand(p, lt);
    const feet = feetAt(p, lt, ctx);
    m.x = feet.x;
    m.y = feet.y + m.dy;
    if (p.exit === "pop") {
      const b = KC.prog(lt, dur - 0.16, 0.16);
      m.sx *= 1 + 0.12 * b;
      m.sy *= 1 + 0.12 * b;
      m.o *= 1 - KC.inCubic(b);
    } else if (p.exit === "fly_to" && lt >= p.fly_to.at_f / ctx.fps - CROUCH) {
      const fly = p.fly_to;
      const t0 = fly.at_f / ctx.fps;
      const from = feetAt(p, Math.min(lt, t0), ctx);
      m.dy = 0;
      m.ry = 0;
      m.rz = 0;
      m.x = from.x;
      m.y = from.y;
      if (lt < t0) {
        const u = (lt - (t0 - CROUCH)) / CROUCH; // crouches before it jumps
        m.sx = 1 + 0.16 * u;
        m.sy = 1 - 0.22 * u;
      } else {
        const u = KC.prog(lt, t0, Math.max(0, dur - FADE - t0));
        const e = KC.outCubic(u);
        const arc = Math.sin(Math.PI * Math.min(1, u * 1.1));
        const scale = 1 - 0.6 * e;
        m.x = from.x + (fly.x * ctx.w - from.x) * e;
        m.y = from.y + (fly.y * ctx.h - from.y) * e - ARC_PX * arc;
        m.sx = scale * (1 - 0.12 * arc);
        m.sy = scale * (1 + 0.18 * arc);
        m.rz = -360 * e;
        m.o *= 1 - KC.prog(lt, dur - FADE, FADE);
      }
    }
    return m;
  }

  // how strong the glow under the feet and the sparkles are at local time lt (0 to 1)
  function strengths(p, lt, dur, ctx) {
    const landing = p.enter === "drop" && lt >= FALL && lt < FALL + SQUASH;
    let glow = KC.prog(lt, 0.2, 0.12) * (landing ? 1 : 0.8);
    let spark = KC.prog(lt, 0.3, 0.2);
    if (p.exit === "fly_to") {
      const t0 = p.fly_to.at_f / ctx.fps;
      glow *= 1 - KC.prog(lt, t0, 0.2);
      spark *= 1 - KC.prog(lt, t0, 0.25);
    } else if (p.exit === "pop") {
      const k = 1 - KC.inCubic(KC.prog(lt, dur - 0.16, 0.16));
      glow *= k;
      spark *= k;
    }
    return { glow, spark };
  }

  // a four-pointed star of radius r centered on (x, y), as the data of an SVG path
  function star(x, y, r) {
    const c = " Q" + x + " " + y + " ";
    return (
      "M" + x + " " + (y - r) + c + (x + r) + " " + y + c + x + " " + (y + r) +
      c + (x - r) + " " + y + c + x + " " + (y - r) + "Z"
    );
  }

  // the glow under the feet: where the feet are (held where the flight began), as wide as the picture
  function glowNode(p, m, lt, strength, ctx) {
    const held = p.exit === "fly_to" ? Math.min(lt, p.fly_to.at_f / ctx.fps) : lt;
    const base = feetAt(p, held, ctx);
    const tall = (p.w_px * 80) / 280;
    const glow = KC.el("div", "kc-abs kc-sticker-glow");
    glow.style.left = "0px";
    glow.style.top = "0px";
    glow.style.width = p.w_px + "px";
    glow.style.height = tall + "px";
    glow.style.background = "radial-gradient(ellipse at center, " + rgba(p.glow_color, 0.85, 0.3) +
      ", " + rgba(p.glow_color, 0.4) + " 45%, " + rgba(p.glow_color, 0) + " 70%)";
    glow.style.opacity = strength;
    glow.style.transform = "translate(" + (base.x - p.w_px / 2) + "px," + (base.y - tall / 2) +
      "px) scale(" + m.sx + ",1)";
    return glow;
  }

  // the box on the feet with the picture in it, turned and squashed as the pose says
  function boxNode(img, p, m) {
    const box = KC.el("div", "kc-abs kc-sticker");
    box.style.left = "0px";
    box.style.top = "0px";
    box.style.width = p.w_px + "px";
    box.style.opacity = m.o;
    box.style.transform = "translate(" + m.x + "px," + m.y + "px) translate(-50%,0) " +
      "perspective(900px) rotateY(" + m.ry + "deg) rotateZ(" + m.rz + "deg) " +
      "scale(" + m.sx + "," + m.sy + ")";
    box.appendChild(img);
    return box;
  }

  // the sparkles that are lit at local time lt, around the middle of the picture
  function sparksNode(state, p, m, lt, strength, ctx) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("width", ctx.w);
    svg.setAttribute("height", ctx.h);
    svg.style.position = "absolute";
    svg.style.left = "0px";
    svg.style.top = "0px";
    const img = state.img;
    const ratio = img.naturalWidth > 0 ? img.naturalHeight / img.naturalWidth : 1;
    const cy = m.y - p.w_px * ratio * 0.45;
    state.sparks.forEach((spark, i) => {
      const k = Math.pow(Math.max(0, Math.sin(lt * 7 + i * 1.7)), 2) * strength;
      if (k < 0.02) return;
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("fill", rgba(p.glow_color, 1, 0.8));
      path.setAttribute("fill-opacity", 0.95 * k);
      path.setAttribute("d", star(m.x + spark.dx, cy + spark.dy, spark.r * (0.4 + 0.6 * k)));
      path.style.filter = "drop-shadow(0 0 8px " + rgba(p.glow_color, 0.9) + ")";
      svg.appendChild(path);
    });
    return svg;
  }

  KC.register("sticker", {
    // the box has no height and sits on the feet, and the picture hangs up from its bottom edge:
    // where the feet are does not depend on whether the picture has loaded yet, and it squashes
    // and turns around the feet (the box is the point it turns around)
    css: ".kc-sticker{height:0;transform-origin:50% 100%}" +
      ".kc-sticker-img{position:absolute;left:0;bottom:0;display:block;width:100%;height:auto}" +
      ".kc-sticker-glow{border-radius:50%;filter:blur(5px)}",
    // What is made once is the picture (a new <img> would have to load again) and where the
    // sparkles are; the nodes around it are made on every seek (see `update`).
    mount(root, cue, ctx) {
      const p = cue.params;
      const uri = ctx.images[p.image];
      if (!uri) throw new Error("kcut: falta la imagen del sticker");
      const img = KC.el("img", "kc-sticker-img");
      img.decoding = "sync";
      img.alt = "";
      img.src = uri;
      img.style.filter = "drop-shadow(0 12px 14px rgba(0,0,0,.45))" +
        (p.glow ? " drop-shadow(0 0 22px " + rgba(p.glow_color, 0.55) + ")" : "");
      const next = KC.rng(p.seed);
      const sparks = [];
      for (let i = 0; p.sparkles && i < SPARKS; i++) {
        sparks.push({
          dx: (2 * next() - 1) * 0.7 * p.w_px,
          dy: -next() * 0.9 * p.w_px,
          r: (0.043 + 0.036 * next()) * p.w_px,
        });
      }
      return { root, img, sparks };
    },
    update(state, cue, lt, t, ctx) {
      const p = cue.params;
      const dur = (cue.end_f - cue.start_f) / ctx.fps;
      const m = pose(p, lt, dur, ctx);
      const power = strengths(p, lt, dur, ctx);
      // The glow, the box with the picture and the sparkles are made anew on every seek (001.34,
      // row 4). Nodes that are kept and moved from one seek to the next keep their layers, and
      // Chromium draws the soft shadows of those layers from an earlier seek: the same time then
      // gave different pixels depending on which frames were shown before (measured: every frame
      // of 9, in three orders). New nodes have no earlier seek. The picture is moved into the new
      // box, already loaded.
      state.root.replaceChildren();
      if (p.glow && power.glow > 0.01) {
        state.root.appendChild(glowNode(p, m, lt, power.glow, ctx));
      }
      state.root.appendChild(boxNode(state.img, p, m));
      if (state.sparks.length > 0 && power.spark > 0.01) {
        state.root.appendChild(sparksNode(state, p, m, lt, power.spark, ctx));
      }
    },
  });
})();
