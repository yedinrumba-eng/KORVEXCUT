"""Pilot (throwaway): find time offset between two recordings via FFT cross-correlation."""
import sys
import wave

import numpy as np
from scipy.signal import fftconvolve


def load(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    return x / 32768.0, sr


def envelope(x: np.ndarray, sr: int, hop_s: float = 0.005) -> np.ndarray:
    hop = int(sr * hop_s)
    n = len(x) // hop
    e = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    e = np.log1p(e * 100)
    return (e - e.mean()) / (e.std() + 1e-9)


a, sr = load(sys.argv[1])
b, _ = load(sys.argv[2])
hop_s = 0.005
ea, eb = envelope(a, sr, hop_s), envelope(b, sr, hop_s)
corr = fftconvolve(ea, eb[::-1], mode="full")
lag = int(np.argmax(corr)) - (len(eb) - 1)
peak = corr.max() / min(len(ea), len(eb))
second = np.sort(corr)[-200] / min(len(ea), len(eb))
coarse = lag * hop_s
# refine on raw audio within +-50 ms of the coarse lag
w = int(0.05 * sr)
c = int(coarse * sr)
best, best_off = -1e9, c
seg_len = min(len(a), len(b)) // 2
for off in range(c - w, c + w + 1, 4):
    if off >= 0:
        xa, xb = a[off : off + seg_len], b[: seg_len]
    else:
        xa, xb = a[:seg_len], b[-off : -off + seg_len]
    m = min(len(xa), len(xb))
    v = float(np.dot(xa[:m], xb[:m]) / (np.linalg.norm(xa[:m]) * np.linalg.norm(xb[:m]) + 1e-9))
    if v > best:
        best, best_off = v, off
print(f"coarse_offset_s={coarse:.3f} envelope_peak={peak:.3f} (noise_floor~{second:.3f})")
print(f"refined_offset_s={best_off / sr:.4f} raw_corr={best:.3f}")
print("meaning: B starts at A_time = offset (positive => B started later than A)")
