"""Pilot (throwaway): frame-exact base video compositor (no graphics layer).

usage: compose.py edl.json mezz_dir out.mp4
Each output frame k is built from an explicitly computed source frame -> A/V can't drift.
Readers/encoder are ffmpeg pipes with explicit bt709 matrices (cv2's decoder assumes bt601).
"""
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

W, H, FPS = 1080, 1920, 30
LIME = (81, 254, 215)  # BGR of Higgsfield-like lime (#D7FE51)

def reader(path: Path, t0: float, w: int, h: int, n: int):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t0:.4f}", "-i", str(path), "-frames:v", str(n),
           "-vf", "scale=in_color_matrix=bt709:in_range=tv,format=bgr24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = w * h * 3
    assert p.stdout is not None
    for _ in range(n):
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
    p.stdout.close()
    p.wait()

def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2

def back_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2

def cam_frame(img: np.ndarray, zoom: float, cx: float, anchor_top: bool) -> np.ndarray:
    h, w = img.shape[:2]
    cw, ch = int(round(w / zoom)), int(round(h / zoom))
    x = int(round(min(max(cx * w - cw / 2, 0), w - cw)))
    y = 0 if anchor_top else (h - ch) // 2
    crop = img[y : y + ch, x : x + cw]
    return cv2.resize(crop, (W, H), interpolation=cv2.INTER_AREA)

def ferrari_frame(img: np.ndarray, cx: float, push: float, dim: float) -> np.ndarray:
    h, w = img.shape[:2]
    ch = h / push
    cw = ch * 9 / 16
    x = min(max(cx * w - cw / 2, 0), w - cw)
    y = (h - ch) / 2
    crop = img[int(y) : int(y + ch), int(x) : int(x + cw)]
    up = cv2.resize(crop, (W, H), interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(up, (0, 0), 2.0)
    sharp = cv2.addWeighted(up, 1.35, blur, -0.35, 0)
    return (sharp.astype(np.float32) * dim).clip(0, 255).astype(np.uint8)

# ---- screen insert ----
SCREEN_KF = [  # rel t, crop (cx, cy, cw) in source px (crop aspect follows card), card (w, h) on output
    (0.00, (947, 433, 1894), (1040, 476)),
    (1.50, (947, 433, 1894), (1040, 476)),
    (1.90, (947, 433, 1894), (1040, 476)),
    (2.55, (1735, 395, 330), (1000, 760)),
    (3.10, (1735, 395, 330), (1000, 760)),
    (3.75, (1010, 530, 520), (1000, 1100)),
    (4.30, (1010, 530, 520), (1000, 1100)),
]

def screen_src_t(rel: float) -> float:
    return rel if rel < 1.5 else 3.0 + (rel - 1.5)

def lerp(a, b, u):
    return tuple(x + (y - x) * u for x, y in zip(a, b))

def screen_state(rel: float):
    for (t0, c0, k0), (t1, c1, k1) in zip(SCREEN_KF, SCREEN_KF[1:]):
        if t0 <= rel <= t1:
            u = ease((rel - t0) / (t1 - t0)) if t1 > t0 else 1.0
            return lerp(c0, c1, u), lerp(k0, k1, u)
    return SCREEN_KF[-1][1], SCREEN_KF[-1][2]

def rounded_mask(w: int, h: int, r: int) -> np.ndarray:
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (r, 0), (w - r, h), 255, -1)
    cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        cv2.circle(m, (cx, cy), r, 255, -1, lineType=cv2.LINE_AA)
    return m

def make_bg() -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.dstack([np.full((H, W), v, np.float32) for v in (14, 11, 10)])
    d = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H * 0.47) / H) ** 2)
    glow = np.exp(-(d / 0.32) ** 2)[..., None] * np.array(LIME, np.float32) * 0.16
    return (base + glow).clip(0, 255).astype(np.uint8)

def screen_frame(src: np.ndarray, rel: float, bg: np.ndarray) -> np.ndarray:
    (cx, cy, cw), (kw, kh) = screen_state(rel)
    kw, kh = int(round(kw)), int(round(kh))
    ch = cw * kh / kw
    sh, sw = src.shape[:2]
    x0 = min(max(cx - cw / 2, 0), sw - cw)
    y0 = cy - ch / 2
    # pad when the crop leaves the source (tall card over a wide screen)
    pad = int(max(0, -y0, y0 + ch - sh)) + 2
    srcp = cv2.copyMakeBorder(src, pad, pad, 0, 0, cv2.BORDER_CONSTANT, value=(12, 11, 11))
    crop = srcp[int(y0 + pad) : int(y0 + pad + ch), int(x0) : int(x0 + cw)]
    card = cv2.resize(crop, (kw, kh), interpolation=cv2.INTER_AREA if cw > kw else cv2.INTER_CUBIC)
    enter = back_out(rel / 0.32)
    scale = 0.72 + 0.28 * enter
    alpha = min(1.0, rel / 0.18)
    kw2, kh2 = max(2, int(kw * scale)), max(2, int(kh * scale))
    card = cv2.resize(card, (kw2, kh2), interpolation=cv2.INTER_AREA)
    out = bg.copy()
    cx_o, cy_o = W // 2, int(H * 0.47)
    x, y = cx_o - kw2 // 2, cy_o - kh2 // 2  # card always fits: kw<=1040, kh<=1250
    r = max(6, int(28 * scale))
    bp = 4  # lime border thickness
    m = rounded_mask(kw2, kh2, r)
    # drop shadow
    sh_m = np.zeros((H, W), np.uint8)
    sh_m[y + 24 : y + 24 + kh2, x : x + kw2] = m
    sh_m = cv2.GaussianBlur(sh_m, (0, 0), 28)
    out = (out.astype(np.float32) * (1 - 0.65 * alpha * sh_m[..., None] / 255)).astype(np.uint8)
    # lime border = bigger rounded rect behind the card
    bm = rounded_mask(kw2 + 2 * bp, kh2 + 2 * bp, r + bp).astype(np.float32)[..., None] / 255 * alpha
    reg = out[y - bp : y + kh2 + bp, x - bp : x + kw2 + bp].astype(np.float32)
    reg = reg * (1 - bm) + np.array(LIME, np.float32) * bm
    cm = np.zeros((kh2 + 2 * bp, kw2 + 2 * bp), np.float32)
    cm[bp : bp + kh2, bp : bp + kw2] = m.astype(np.float32) / 255 * alpha
    cimg = np.zeros_like(reg)
    cimg[bp : bp + kh2, bp : bp + kw2] = card
    reg = reg * (1 - cm[..., None]) + cimg * cm[..., None]
    out[y - bp : y + kh2 + bp, x - bp : x + kw2 + bp] = reg.clip(0, 255).astype(np.uint8)
    return out

def main() -> None:
    edl = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    mezz = Path(sys.argv[2])
    out_path = sys.argv[3]
    t0 = edl["t0"]
    enc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-colorspace", "bt709", "-color_primaries", "bt709",
         "-color_trc", "bt709", "-color_range", "tv", "-movflags", "+faststart", out_path],
        stdin=subprocess.PIPE)
    assert enc.stdin is not None
    bg = make_bg()
    ferrari_cx = {0.3: 0.50, 12.0: 0.50, 20.4: 0.46}
    written = 0
    for s in edl["video_spans"]:
        n, cam, p = s["dur_f"], s["cam"], s["param"]
        got = 0
        if cam in ("a1", "a2"):
            st = (s["src_in_f"] - round(t0 * FPS)) / FPS
            for img in reader(mezz / f"{cam}.mp4", st - 0.25 / FPS, 1440, 2560, n):
                enc.stdin.write(cam_frame(img, float(p), float(s.get("cx", 0.5)), cam == "a1").tobytes())
                got += 1
        elif cam == "ferrari":
            dim = 0.78 if s["out_in_f"] == 0 or s["out_in_f"] + n == edl["frames"] else 1.0
            for i, img in enumerate(reader(mezz / "ferrari.mp4", float(p) - 0.25 / FPS, 1920, 1080, n)):
                push = 1.0 + 0.07 * i / max(1, n - 1)
                enc.stdin.write(ferrari_frame(img, ferrari_cx.get(float(p), 0.5), push, dim).tobytes())
                got += 1
        elif cam == "screen":
            # time-remapped: read the two source windows sequentially
            rels = [i / FPS for i in range(n)]
            first = [r for r in rels if r < 1.5]
            second = [r for r in rels if r >= 1.5]
            frames = list(reader(mezz / "screen.mp4", 0.0, 1894, 866, len(first)))
            frames += list(reader(mezz / "screen.mp4", 3.0 - 0.25 / FPS, 1894, 866, len(second)))
            for rel, img in zip(rels, frames):
                enc.stdin.write(screen_frame(img, rel, bg).tobytes())
                got += 1
        assert got == n, f"span {s} produced {got}/{n} frames"
        written += got
        print(f"out {s['out_in_f'] / FPS:7.3f} {cam:<8} {got} frames", flush=True)
    enc.stdin.close()
    enc.wait()
    assert written == edl["frames"], (written, edl["frames"])
    print(f"BASE OK frames={written}")

if __name__ == "__main__":
    main()
