"use strict";
// globe: a wire sphere (a parallel and a meridian every 30 degrees, and some dots on it) that
// spins on its axis, tilted, with a radial halo and a ring. It is drawn on a canvas 2.95 radii
// wide, and each picture is worked out from the time alone: the same time, the same picture.
(function () {
  const KC = window.KC;
  const STEP = Math.PI / 6; // 30 degrees
  const BACK = 0.18; // how much of its color the far side keeps
  const SEGMENTS = 48; // straight pieces in each parallel or meridian
  const DOT_PX = 3.5;

  function parts(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [n >> 16, (n >> 8) & 255, n & 255];
  }

  // a point of the unit sphere (latitude, longitude): turned by `spin` around the axis and then
  // tilted by `tilt` toward the camera; z > 0 is the near side
  function project(lat, lon, spin, tilt) {
    const a = lon + spin;
    const x = Math.cos(lat) * Math.sin(a);
    const y = Math.sin(lat);
    const z = Math.cos(lat) * Math.cos(a);
    return {
      x,
      y: y * Math.cos(tilt) - z * Math.sin(tilt),
      z: y * Math.sin(tilt) + z * Math.cos(tilt),
    };
  }

  // the line from (lat0, lon0) to (lat1, lon1) in SEGMENTS pieces, each one as opaque as the side
  // of the sphere it is on
  function line(g, view, lat0, lon0, lat1, lon1) {
    let prev = null;
    for (let i = 0; i <= SEGMENTS; i++) {
      const k = i / SEGMENTS;
      const q = project(lat0 + (lat1 - lat0) * k, lon0 + (lon1 - lon0) * k, view.spin, view.tilt);
      const point = { x: view.c + view.r * q.x, y: view.c - view.r * q.y, z: q.z };
      if (prev !== null) {
        g.strokeStyle = view.paint((prev.z + point.z) / 2 >= 0 ? 1 : BACK);
        g.beginPath();
        g.moveTo(prev.x, prev.y);
        g.lineTo(point.x, point.y);
        g.stroke();
      }
      prev = point;
    }
  }

  function draw(g, view, dots) {
    const { c, r } = view;
    g.clearRect(0, 0, 2 * c, 2 * c);
    const halo = g.createRadialGradient(c, c, 0, c, c, c);
    halo.addColorStop(0, view.paint(0.06));
    halo.addColorStop(r / c - 0.04, view.paint(0.24));
    halo.addColorStop(1, view.paint(0));
    g.fillStyle = halo;
    g.fillRect(0, 0, 2 * c, 2 * c);
    g.lineWidth = 2;
    g.lineCap = "round";
    for (let lat = -2 * STEP; lat <= 2 * STEP + 1e-9; lat += STEP) {
      line(g, view, lat, 0, lat, 2 * Math.PI);
    }
    for (let lon = 0; lon < 2 * Math.PI - 1e-9; lon += STEP) {
      line(g, view, -Math.PI / 2, lon, Math.PI / 2, lon);
    }
    for (const dot of dots) {
      const q = project(dot.lat, dot.lon, view.spin, view.tilt);
      g.fillStyle = view.paint(q.z >= 0 ? 1 : BACK);
      g.beginPath();
      g.arc(c + r * q.x, c - r * q.y, DOT_PX, 0, 2 * Math.PI);
      g.fill();
    }
    g.lineWidth = 3;
    g.strokeStyle = view.paint(1);
    g.beginPath();
    g.arc(c, c, r, 0, 2 * Math.PI);
    g.stroke();
  }

  KC.register("globe", {
    css: "",
    mount(root, cue, ctx) {
      const p = cue.params;
      const size = Math.round(2.95 * p.r_px);
      const canvas = KC.el("canvas", "kc-abs");
      canvas.width = size;
      canvas.height = size;
      canvas.style.left = p.x * ctx.w + "px";
      canvas.style.top = p.y * ctx.h + "px";
      canvas.style.display = "none";
      root.appendChild(canvas);
      const next = KC.rng(p.seed);
      const dots = [];
      for (let i = 0; i < p.dots; i++) {
        dots.push({ lat: Math.asin(2 * next() - 1), lon: 2 * Math.PI * next() });
      }
      const [red, green, blue] = parts(p.color);
      const paint = (alpha) => "rgba(" + red + "," + green + "," + blue + "," + alpha + ")";
      return { canvas, g: canvas.getContext("2d"), dots, c: size / 2, r: p.r_px, paint };
    },
    update(state, cue, lt, t, ctx) {
      const p = cue.params;
      const st = KC.pop(lt, 0, (cue.end_f - cue.start_f) / ctx.fps, 0.4, 0.2);
      state.canvas.style.display = st ? "" : "none";
      if (!st) return;
      const view = { c: state.c, r: state.r, paint: state.paint, spin: p.spin * lt, tilt: p.tilt };
      draw(state.g, view, state.dots);
      const turn = -90 * (1 - KC.outCubic(KC.prog(lt, 0, 0.5)));
      state.canvas.style.opacity = st.o;
      state.canvas.style.transform =
        "translate(-50%,-50%) scale(" + st.s + ") rotate(" + turn + "deg)";
    },
  });
})();
