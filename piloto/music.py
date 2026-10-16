"""Pilot (throwaway): synthesize a license-free 120 BPM bed (Am-F-C-G) for the edit.

usage: music.py cues.json out.wav
Grid origin t=0 (hook impact on the downbeat). Drums mute during the screen insert,
where the SFX groove (same grid) takes over -> it feels like a drop.
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, lfilter

SR = 48000
BEAT = 0.5
BAR = 2.0
cues = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
DUR = float(cues["total"])
N = int(DUR * SR) + SR
out = np.zeros(N, np.float32)

def midi(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)

def lp(x: np.ndarray, fc: float, order: int = 2) -> np.ndarray:
    b, a = butter(order, fc / (SR / 2), "low")
    return lfilter(b, a, x).astype(np.float32)

def hp(x: np.ndarray, fc: float) -> np.ndarray:
    b, a = butter(2, fc / (SR / 2), "high")
    return lfilter(b, a, x).astype(np.float32)

def add(sig: np.ndarray, t: float) -> None:
    i = int(round(t * SR))
    if i >= N:
        return
    n = min(len(sig), N - i)
    out[i : i + n] += sig[:n]

CHORDS = [  # (bass root, chord tones)
    (45, (57, 60, 64)),  # Am
    (41, (53, 57, 60)),  # F
    (48, (55, 60, 64)),  # C
    (43, (55, 59, 62)),  # G
]
S0, S1 = cues["screen"]["t"], cues["screen"]["end"]
O0 = cues["outro"]["t"]
n_bars = int(np.ceil(DUR / BAR)) + 1

# pad: detuned saws per bar, soft attack/release, low-passed
pad = np.zeros(N, np.float32)
for b in range(n_bars):
    root, tones = CHORDS[b % 4]
    t0 = b * BAR
    last = t0 + BAR >= DUR
    L = BAR + (1.6 if last else 0.25)
    t = np.arange(int(L * SR)) / SR
    y = np.zeros_like(t, dtype=np.float32)
    for m in tones + (tones[0] + 12,):
        for det in (-0.07, 0.07):
            ph = midi(m + det) * t
            y += (2 * (ph % 1.0) - 1).astype(np.float32)
    env = np.clip(t / 0.18, 0, 1) * np.clip((L - t) / (1.4 if last else 0.25), 0, 1)
    seg = (y * env * 0.06).astype(np.float32)
    i = int(t0 * SR)
    n = min(len(seg), N - i)
    if n > 0:
        pad[i : i + n] += seg[:n]
out += lp(pad, 1100.0)

# bass: root on beats 1 and 3, pickup on the 'and' of 4
for b in range(n_bars):
    root, _ = CHORDS[b % 4]
    for off, dur, g in ((0.0, 0.45, 1.0), (1.0, 0.45, 0.85), (1.75, 0.2, 0.55)):
        t0 = b * BAR + off
        if t0 >= DUR:
            continue
        t = np.arange(int(dur * SR)) / SR
        f = midi(root)
        y = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)
        env = np.clip(t / 0.008, 0, 1) * np.exp(-t * 4.5)
        add((y * env * 0.22 * g).astype(np.float32), t0)

# arpeggio: 8th-note plucks (triangle) one octave up
arp = np.zeros(N, np.float32)
for k in range(int(DUR / (BEAT / 2))):
    t0 = k * BEAT / 2
    _, tones = CHORDS[int(t0 // BAR) % 4]
    m = (tones + (tones[0] + 12,))[k % 4] + 12
    t = np.arange(int(0.22 * SR)) / SR
    ph = midi(m) * t
    tri = (2 * np.abs(2 * (ph % 1.0) - 1) - 1).astype(np.float32)
    seg = tri * np.exp(-t * 16) * 0.05
    i = int(t0 * SR)
    arp[i : i + len(seg)] += seg[: max(0, N - i)]
out += lp(arp, 3200.0)

# soft drums (muted during the screen insert and after the outro hit)
rng = np.random.default_rng(9)
for k in range(int(DUR / (BEAT / 2))):
    t0 = k * BEAT / 2
    if S0 - 0.05 <= t0 < S1 or t0 >= O0:
        continue
    if k % 4 == 0:  # beats 1 & 3 of each bar
        t = np.arange(int(0.25 * SR)) / SR
        f = 48 + 90 * np.exp(-t * 35)
        y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
        add((y * 0.30).astype(np.float32), t0)
    if k % 2 == 1:  # off-beat hats
        n = int(0.04 * SR)
        nz = hp(rng.standard_normal(n).astype(np.float32), 7500.0)
        add((nz * np.exp(-np.arange(n) / SR * 120) * 0.05).astype(np.float32), t0)

out = out[: int(DUR * SR)]
fade = int(1.2 * SR)
out[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
out = hp(out, 35.0)
out *= 0.9 / max(1e-6, float(np.abs(out).max()))
with wave.open(sys.argv[2], "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())
print(f"music {DUR:.2f}s bars={n_bars} drums muted {S0:.2f}-{S1:.2f} and after {O0:.2f}")
