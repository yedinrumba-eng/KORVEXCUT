"""Pilot (throwaway): track the palm with LK optical flow; emit output-space positions per frame.

usage: track.py edl.json a1_mezz.mp4 out.json
Windows (A1 source time) + init point (normalized in the A1 frame) are below.
Output coords assume the A1 span uses zoom 1.0 (full frame -> 1080x1920).
"""
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

FPS = 30
TW, TH = 720, 1280  # tracking resolution
WINDOWS = [  # (src_start, src_end, init_x, init_y) — A1 seconds, normalized init
    (92.000, 93.333, 0.53, 0.42),
    (95.767, 97.000, 0.57, 0.54),
]

def gray_frames(path: str, t0: float, n: int):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t0 - 0.25 / FPS:.4f}", "-i", path, "-frames:v",
           str(n), "-vf", f"scale={TW}:{TH},format=gray", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    assert p.stdout is not None
    for _ in range(n):
        b = p.stdout.read(TW * TH)
        if len(b) < TW * TH:
            break
        yield np.frombuffer(b, np.uint8).reshape(TH, TW)
    p.wait()

def track(path: str, t_src0: float, n: int, ix: float, iy: float, t_base: float) -> list[tuple[float, float]]:
    frames = list(gray_frames(path, t_src0 - t_base, n))
    pos = np.array([ix * TW, iy * TH], np.float32)
    pts = None
    out = []
    prev = None
    for f in frames:
        if prev is not None and pts is not None and len(pts) >= 6:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, f, pts, None, winSize=(31, 31), maxLevel=4,
                                                  criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
            ok = st.reshape(-1) == 1
            if ok.sum() >= 4:
                d = np.median((nxt[ok] - pts[ok]).reshape(-1, 2), axis=0)
                pos = pos + d
                pts = nxt[ok].reshape(-1, 1, 2)
            else:
                pts = None
        if pts is None or len(pts) < 12:
            r = 70
            x0, y0 = int(max(pos[0] - r, 0)), int(max(pos[1] - r, 0))
            roi = f[y0 : y0 + 2 * r, x0 : x0 + 2 * r]
            g = cv2.goodFeaturesToTrack(roi, maxCorners=60, qualityLevel=0.01, minDistance=5)
            pts = None if g is None else (g + np.array([[x0, y0]], np.float32)).astype(np.float32)
        out.append((float(pos[0] / TW), float(pos[1] / TH)))
        prev = f
    return out

def smooth(seq: list[tuple[float, float]], k: int = 5) -> list[tuple[float, float]]:
    a = np.array(seq)
    pad = np.pad(a, ((k // 2, k // 2), (0, 0)), mode="edge")
    ker = np.ones(k) / k
    return [(float(x), float(y)) for x, y in zip(np.convolve(pad[:, 0], ker, "valid"), np.convolve(pad[:, 1], ker, "valid"))]

def main() -> None:
    edl = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    t_base = edl["t0"]
    voice = [c for c in edl["clips"] if c["kind"] == "voice"]
    result = []
    for s0, s1, ix, iy in WINDOWS:
        n = round((s1 - s0) * FPS)
        traj = smooth(track(sys.argv[2], s0, n, ix, iy, t_base))
        for i, (x, y) in enumerate(traj):
            ts = s0 + i / FPS
            for c in voice:
                a, b = c["src_in_f"] / FPS, c["src_out_f"] / FPS
                if a <= ts < b:
                    result.append({"t": round(c["out_in_f"] / FPS + (ts - a), 4), "x": round(x * 1080, 1),
                                   "y": round(y * 1920, 1)})
                    break
    Path(sys.argv[3]).write_text(json.dumps(result), encoding="utf-8")
    xs = [r["x"] for r in result]
    ys = [r["y"] for r in result]
    print(f"track points={len(result)} t={result[0]['t']}..{result[-1]['t']} x={min(xs):.0f}..{max(xs):.0f} y={min(ys):.0f}..{max(ys):.0f}")

if __name__ == "__main__":
    main()
