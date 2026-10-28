"use strict";
// holo_board: a holographic board that is born where `born` says, grows to `center` (flickering as
// it opens), shows a moving grid, a sweep, a label and a progress bar, and types a word letter by
// letter, the last one falling at `type_at_f`. Light beams from `beams_from` go to its corners
// while it opens. It folds up in the last 0.22 s. Everything is worked out from the time alone: the
// same time, the same picture.
(function () {
  const KC = window.KC;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const GRID_PX = 40; // a cell of the grid
  const GRID_SPEED = 32; // px/s the grid runs
  const SWEEP_PX = 110; // height of the bright band that sweeps down
  const SWEEP_SPEED = 430; // px/s
  const GROW = 0.45; // s to grow from `born` to `center`
  const HEIGHT_AT = 0.08; // the height starts later and overshoots a little
  const HEIGHT_FOR = 0.42;
  const FLICKER = 0.32; // s of flicker as it opens
  const FOLD = 0.22; // s to fold up at the end
  const MARGIN = 60; // px kept free at each side of the word
  const TALLEST = 0.46; // the word is at most this much of the height of the board (230 of 500)
  const CURSOR_EM = 0.13; // the cursor and the space before it, in letter sizes
  const FALL_EM = 0.217; // how far above its place a letter starts, in letter sizes (50 of 230)

  function parts(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [n >> 16, (n >> 8) & 255, n & 255];
  }

  // "#RRGGBB" as an rgba() color: `lift` of the way to white, `dim` of the way to black
  function rgba(hex, alpha, lift = 0, dim = 0) {
    const mixed = parts(hex).map((v) => Math.round((v + (255 - v) * lift) * (1 - dim)));
    return "rgba(" + mixed.join(",") + "," + alpha + ")";
  }

  function child(parent, cls, text) {
    const node = KC.el("div", "kc-holo-abs " + cls, text);
    parent.appendChild(node);
    return node;
  }

  // the size at which the whole word, the cursor included, fits between the margins of the board:
  // the letters are measured at 100 px on a canvas (the font is loaded by then) and scaled
  function wordSize(state, p) {
    state.probe.font = "900 100px Inter";
    let wide = 0;
    for (const ch of state.chars) wide += state.probe.measureText(ch.toUpperCase()).width;
    const room = p.w_px - 2 * MARGIN + 2 * state.chars.length; // the letters sit 2 px closer
    return Math.max(16, Math.min(TALLEST * p.h_px, room / (wide / 100 + CURSOR_EM)));
  }

  function buildBeams(root, p, ctx) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("width", ctx.w);
    svg.setAttribute("height", ctx.h);
    svg.style.position = "absolute";
    svg.style.left = "0px";
    svg.style.top = "0px";
    svg.style.filter = "blur(6px)";
    svg.style.display = "none";
    const shafts = p.beams_from.map(() => {
      const shaft = document.createElementNS(SVG_NS, "polygon");
      shaft.setAttribute("fill", rgba(p.color, 0.45));
      svg.appendChild(shaft);
      return shaft;
    });
    root.appendChild(svg);
    return { svg, shafts };
  }

  function buildFrame(board, p, ctx) {
    const c = p.color;
    const frame = child(board, "kc-holo-frame", "");
    frame.style.border = "3px solid " + rgba(c, 0.95);
    frame.style.background = "linear-gradient(180deg, " + rgba(c, 0.24) + ", " + rgba(c, 0.1, 0, 0.55) + ")";
    frame.style.boxShadow = "0 0 48px " + rgba(c, 0.65) + ", inset 0 0 80px " + rgba(c, 0.28);
    const grid = child(frame, "kc-holo-grid", "");
    const line = "linear-gradient(" + rgba(c, 0.17) + " 1px,transparent 1px)";
    const column = "linear-gradient(90deg," + rgba(c, 0.17) + " 1px,transparent 1px)";
    grid.style.backgroundImage = line + "," + column;
    child(frame, "kc-holo-scan", "");
    const sweep = child(frame, "kc-holo-sweep", "");
    const band = rgba(c, 0.32, 0.45);
    const label = child(frame, "kc-holo-label", p.label);
    label.style.color = rgba(c, 0.95, 0.4);
    const corner = child(frame, "kc-holo-corner", p.corner_text);
    corner.style.color = rgba(c, 0.7, 0.4);
    const track = child(frame, "kc-holo-track", "");
    track.style.background = rgba(c, 0.25);
    const fill = KC.el("div", "kc-holo-fill");
    fill.style.background = ctx.brand.accent;
    fill.style.boxShadow = "0 0 12px " + ctx.brand.accent;
    track.appendChild(fill);
    const word = child(frame, "kc-holo-word kc-big", "");
    word.style.color = rgba(c, 1, 0.89);
    word.style.textShadow = "0 0 16px " + rgba(c, 0.95) + ", 0 0 48px " + rgba(c, 0.7);
    const letters = buildLetters(word, p);
    const cursor = KC.el("span", "kc-holo-cursor");
    cursor.style.background = ctx.brand.accent;
    cursor.style.boxShadow = "0 0 14px " + ctx.brand.accent;
    word.appendChild(cursor);
    return { grid, sweep, band, label, fill, word, letters, cursor };
  }

  // the board and its beams, built under `root`: the nodes that `update` changes
  function buildBoard(root, p, ctx) {
    const beams = buildBeams(root, p, ctx);
    const board = KC.el("div", "kc-abs");
    board.style.left = "0px";
    board.style.top = "0px";
    board.style.width = p.w_px + "px";
    board.style.height = p.h_px + "px";
    const view = Object.assign({ beams, board }, buildFrame(board, p, ctx));
    const edge = "6px solid " + ctx.brand.accent;
    const corners = [["left", "top"], ["right", "top"], ["left", "bottom"], ["right", "bottom"]];
    for (const [x, y] of corners) {
      const bracket = child(board, "kc-holo-bracket", "");
      bracket.style[x] = "-10px";
      bracket.style[y] = "-10px";
      bracket.style["border" + (x === "left" ? "Left" : "Right")] = edge;
      bracket.style["border" + (y === "top" ? "Top" : "Bottom")] = edge;
    }
    root.appendChild(board);
    return view;
  }

  // one span for each character (a code point, as the length of `text` is counted), all hidden
  function buildLetters(word, p) {
    return Array.from(p.text).map((ch) => {
      const node = KC.el("span", "kc-holo-letter", ch);
      node.style.display = "none";
      word.appendChild(node);
      return node;
    });
  }

  // where the cursor is lit at local time lt: it blinks at 5 Hz until just before the first letter,
  // stays lit while the word is typed and blinks at 4 Hz after the last letter fell
  function cursorOn(p, lt, fps) {
    const n = Array.from(p.text).length;
    const first = (p.type_at_f - (n - 1) * p.type_step_f) / fps;
    const last = p.type_at_f / fps;
    if (lt < first - 0.05) return Math.floor(lt * 5) % 2 === 0;
    if (lt < last) return true;
    return Math.floor((lt - last) * 4) % 2 === 0;
  }

  KC.register("holo_board", {
    css: ".kc-holo-abs{position:absolute}" +
      ".kc-holo-frame{left:0;top:0;right:0;bottom:0;border-radius:22px;overflow:hidden}" +
      ".kc-holo-grid{left:0;right:0;bottom:0;top:0;background-size:40px 40px}" +
      ".kc-holo-scan{left:0;top:0;right:0;bottom:0;" +
      "background:repeating-linear-gradient(180deg,rgba(255,255,255,.07) 0 2px,transparent 2px 6px)}" +
      ".kc-holo-sweep{left:0;top:0;right:0;bottom:0}" +
      ".kc-holo-label{left:36px;top:26px;font-weight:800;font-size:30px;letter-spacing:7px;" +
      "text-transform:uppercase}" +
      ".kc-holo-corner{right:32px;top:30px;font-weight:600;font-size:22px;letter-spacing:4px;" +
      "text-transform:uppercase}" +
      ".kc-holo-track{left:36px;right:36px;bottom:30px;height:4px}" +
      ".kc-holo-fill{height:100%;width:0}" +
      ".kc-holo-word{left:0;top:0;width:100%;height:100%;display:flex;align-items:center;" +
      "justify-content:center}" +
      ".kc-holo-letter{display:inline-block;white-space:pre}" +
      ".kc-holo-cursor{display:inline-block;width:.078em;height:.78em;margin-left:.052em}" +
      ".kc-holo-bracket{width:56px;height:56px}",
    // Nothing is built here: every seek builds the board anew (see `update`).
    mount(root, cue, ctx) {
      return { root, chars: Array.from(cue.params.text), probe: KC.el("canvas").getContext("2d") };
    },
    update(state, cue, lt, t, ctx) {
      const p = cue.params;
      // The board is built anew on every seek (001.34, row 4). A board that is kept and changed from
      // one seek to the next keeps its layers and its tiles, and Chromium draws some of those tiles
      // from an earlier seek (the soft shadows are drawn again only where something changed): the
      // same time then gave pixels that differ by a few levels at the corners, depending on which
      // frames were shown before (measured: 6 of 9 frames, in three orders). A new board has no
      // earlier seek, so the picture depends on the time alone.
      state.root.replaceChildren();
      const view = buildBoard(state.root, p, ctx);
      const dur = (cue.end_f - cue.start_f) / ctx.fps;
      const u = KC.outCubic(KC.prog(lt, 0, GROW));
      const uy = KC.outBack(KC.prog(lt, HEIGHT_AT, HEIGHT_FOR));
      const fold = KC.prog(lt, dur - FOLD, FOLD);
      const cx = (p.born.x + (p.center.x - p.born.x) * u) * ctx.w;
      const cy = (p.born.y + (p.center.y - p.born.y) * u) * ctx.h;
      const sx = (0.14 + 0.86 * u) * (1 + 0.08 * fold);
      const sy = Math.max(0.03, (0.05 + 0.95 * uy) * (1 - 0.97 * KC.inCubic(fold)));
      const flicker = lt < FLICKER ? 0.55 + 0.45 * Math.abs(Math.sin(lt * 95)) : 1;
      view.board.style.opacity = flicker * (1 - KC.inCubic(KC.prog(lt, dur - 0.08, 0.08)));
      view.board.style.transform = "translate(" + (cx - p.w_px / 2) + "px," + (cy - p.h_px / 2) +
        "px) perspective(1400px) rotateX(9deg) scale(" + sx + "," + sy + ")";
      // the grid and the sweep move as paint: the position of a background, the stops of a gradient
      view.grid.style.backgroundPosition = "0px " + ((lt * GRID_SPEED) % GRID_PX) + "px";
      const top = ((lt * SWEEP_SPEED) % (p.h_px + 140)) - SWEEP_PX;
      view.sweep.style.background = "linear-gradient(180deg,transparent " + top + "px," + view.band +
        " " + (top + SWEEP_PX / 2) + "px,transparent " + (top + SWEEP_PX) + "px)";
      view.label.style.opacity = KC.prog(lt, 0.3, 0.15);
      view.fill.style.width = 100 * KC.prog(lt, 0.3, dur - 0.8) + "%";
      // the beams: from each point to the corners of the nearer side, fading out from +0.15 to +0.65
      const power = KC.clamp(1 - KC.prog(lt, 0.15, 0.5)) * 0.9;
      const lit = power > 0.01 && p.beams_from.length > 0;
      view.beams.svg.style.display = lit ? "" : "none";
      if (lit) {
        const half = { w: (p.w_px / 2) * sx, h: (p.h_px / 2) * sy };
        view.beams.svg.style.opacity = power;
        p.beams_from.forEach((from, i) => {
          const edge = from.x < p.center.x ? cx - half.w : cx + half.w;
          view.beams.shafts[i].setAttribute("points", from.x * ctx.w + "," + from.y * ctx.h + " " +
            edge + "," + (cy - half.h) + " " + edge + "," + (cy + half.h));
        });
      }
      // the word: each letter falls in `type_step_f` frames after the one before; the last one at
      // `type_at_f`. `accent_index`: not given, the last letter; null, none.
      const n = view.letters.length;
      const accent = "accent_index" in p ? p.accent_index : n - 1;
      const size = wordSize(state, p);
      view.word.style.fontSize = size + "px";
      view.letters.forEach((node, i) => {
        const ti = (p.type_at_f - (n - 1 - i) * p.type_step_f) / ctx.fps;
        node.style.display = lt >= ti ? "" : "none";
        if (lt < ti) return;
        const k = KC.outBack(KC.prog(lt, ti, 0.16));
        const glitch = lt - ti < 0.08 ? (i % 2 ? 6 : -6) : 0;
        node.style.transform = "translate(" + glitch + "px," + (1 - k) * FALL_EM * size + "px) " +
          "scale(" + (0.6 + 0.4 * k) + ")";
        node.style.color = i === accent ? ctx.brand.accent : "";
      });
      view.cursor.style.opacity = cursorOn(p, lt, ctx.fps) ? 1 : 0;
    },
  });
})();
