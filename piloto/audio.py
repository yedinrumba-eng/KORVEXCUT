"""Pilot (throwaway): sample-exact voice assembly from the EDL + synthesized SFX bed.

usage: audio.py edl.json a1_voice.wav sfx_plan.json out_dir
  a1_voice.wav: 48 kHz mono, t=0 <=> A1 source t0 (edl["t0"]).
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000

def read_wav(p: str) -> np.ndarray:
    with wave.open(p, "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

def write_wav(p: Path, x: np.ndarray) -> None:
    y = np.clip(x, -1.0, 1.0)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((y * 32767).astype(np.int16).tobytes())

def fade(x: np.ndarray, n: int) -> np.ndarray:
    n = min(n, len(x) // 2)
    r = np.linspace(0.0, 1.0, n, dtype=np.float32)
    x = x.copy()
    x[:n] *= r
    x[-n:] *= r[::-1]
    return x

# ---- SFX synthesis (deterministic: fixed seeds) ----
def env_ad(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-np.maximum(t - attack, 0) / max(decay, 1e-4))

def lowpass(x: np.ndarray, cutoff: np.ndarray | float) -> np.ndarray:
    c = np.broadcast_to(np.asarray(cutoff, dtype=np.float32), x.shape)
    alpha = 1.0 - np.exp(-2 * np.pi * c / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += alpha[i] * (x[i] - acc)
        y[i] = acc
    return y

def whoosh(dur: float = 0.45, seed: int = 1) -> np.ndarray:
    n = int(dur * SR)
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n).astype(np.float32)
    t = np.linspace(0, 1, n, dtype=np.float32)
    sweep = 300 + 5200 * np.sin(np.pi * t) ** 2
    y = lowpass(noise, sweep) - lowpass(noise, sweep * 0.25)
    return (y * np.clip(np.sin(np.pi * t), 0.0, 1.0) ** 1.5 * 0.9).astype(np.float32)

def boom(dur: float = 0.9) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 38 + 70 * np.exp(-t * 18)
    ph = 2 * np.pi * np.cumsum(f) / SR
    rng = np.random.default_rng(7)
    click = lowpass(rng.standard_normal(n).astype(np.float32), 900.0) * np.exp(-t * 60)
    return ((np.sin(ph) * env_ad(n, 0.004, 0.28) + click * 0.6) * 0.95).astype(np.float32)

def pop(freq: float = 820.0, dur: float = 0.12) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = freq * (1 + 0.8 * np.exp(-t * 60))
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * env_ad(n, 0.002, 0.035) * 0.55).astype(np.float32)

def shimmer(dur: float = 1.1) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    for k, f in enumerate((2093.0, 2637.0, 3136.0, 4186.0)):
        d = 0.06 * k
        e = np.where(t >= d, np.exp(-(t - d) * 4.5), 0.0)
        y += (np.sin(2 * np.pi * f * t) * e * (1 + 0.3 * np.sin(2 * np.pi * 7 * t))).astype(np.float32)
    return (y * 0.13 * np.clip(t / 0.02, 0, 1)).astype(np.float32)

def key_click(seed: int) -> np.ndarray:
    n = int(0.05 * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(100 + seed)
    nz = rng.standard_normal(n).astype(np.float32)
    hp = nz - lowpass(nz, 2500.0)
    return (hp * np.exp(-t * 140) * 0.5 + np.sin(2 * np.pi * 180 * t) * np.exp(-t * 90) * 0.25).astype(np.float32)

def ui_click() -> np.ndarray:
    return pop(1900.0, 0.06) * 0.8

def kick() -> np.ndarray:
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    f = 46 + 110 * np.exp(-t * 32)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ad(n, 0.002, 0.14) * 0.95).astype(np.float32)

def hat(seed: int = 0) -> np.ndarray:
    n = int(0.045 * SR)
    t = np.arange(n) / SR
    nz = np.random.default_rng(300 + seed).standard_normal(n).astype(np.float32)
    return ((nz - lowpass(nz, 7000.0)) * np.exp(-t * 110) * 0.32).astype(np.float32)

def pad(dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    for f in (110.0, 164.81, 220.0, 261.63, 329.63):  # A minor-ish stack
        ph = 2 * np.pi * f * t
        y += (2 * ((ph / (2 * np.pi)) % 1.0) - 1).astype(np.float32) * 0.18  # saw
    y = lowpass(y, 900.0 + 500.0 * np.sin(2 * np.pi * 0.5 * t) ** 2)
    e = np.clip(t / 0.25, 0, 1) * np.clip((dur - t) / 0.35, 0, 1)
    return (y * e * 0.8).astype(np.float32)

def typing(dur: float, rate: float = 13.0) -> np.ndarray:
    n = int(dur * SR)
    y = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(55)
    t = 0.0
    k = 0
    while t < dur - 0.05:
        c = key_click(k) * (0.7 + 0.3 * rng.random())
        i = int(t * SR)
        y[i : i + len(c)] += c[: n - i]
        t += 1.0 / rate * (0.7 + 0.6 * rng.random())
        k += 1
    return y

def riser(dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.linspace(0, 1, n, dtype=np.float32)
    nz = np.random.default_rng(77).standard_normal(n).astype(np.float32)
    y = lowpass(nz, 400 + 7000 * t ** 2) * t ** 2
    tone = np.sin(2 * np.pi * np.cumsum(220 + 660 * t ** 2) / SR) * t ** 2 * 0.25
    return ((y * 0.5 + tone) * 0.8).astype(np.float32)

def blip8() -> np.ndarray:
    notes = (523.25, 659.25, 783.99, 1046.5)  # C E G C arpeggio, square wave
    seg = int(0.055 * SR)
    out = []
    for f in notes:
        t = np.arange(seg) / SR
        sq = np.sign(np.sin(2 * np.pi * f * t)).astype(np.float32)
        out.append(sq * np.exp(-t * 18) * 0.22)
    return np.concatenate(out).astype(np.float32)

def powerup() -> np.ndarray:
    n = int(0.55 * SR)
    t = np.arange(n) / SR
    f = 180 + 1400 * (t / t[-1]) ** 1.6
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.clip(t / 0.04, 0, 1) * np.exp(-np.maximum(t - 0.42, 0) * 25)
    return (y * 0.28 + shimmer(0.55) * 0.8).astype(np.float32)

SYNTH = {
    "whoosh": lambda p: whoosh(p.get("dur", 0.45), p.get("seed", 1)),
    "boom": lambda p: boom(),
    "pop": lambda p: pop(p.get("freq", 820.0)),
    "shimmer": lambda p: shimmer(p.get("dur", 1.1)),
    "key": lambda p: key_click(p.get("seed", 0)),
    "click": lambda p: ui_click(),
    "kick": lambda p: kick(),
    "hat": lambda p: hat(p.get("seed", 0)),
    "pad": lambda p: pad(p["dur"]),
    "typing": lambda p: typing(p["dur"]),
    "riser": lambda p: riser(p["dur"]),
    "blip8": lambda p: blip8(),
    "powerup": lambda p: powerup(),
}

def main() -> None:
    edl = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    src = read_wav(sys.argv[2])
    plan = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    out = Path(sys.argv[4])
    fps, t0 = edl["fps"], edl["t0"]
    spf = SR // fps
    assert spf * fps == SR
    total = edl["frames"] * spf
    voice = np.zeros(total, dtype=np.float32)
    base_f = round(t0 * fps)
    for c in edl["clips"]:
        o = c["out_in_f"] * spf
        n = c["dur_f"] * spf
        if c["kind"] == "voice":
            s = (c["src_in_f"] - base_f) * spf
            voice[o : o + n] = fade(src[s : s + n], int(0.005 * SR))
    sfx = np.zeros(total + SR * 2, dtype=np.float32)
    for ev in plan:
        y = SYNTH[ev["type"]](ev) * float(ev.get("gain", 1.0))
        i = int(round(ev["t"] * SR))
        sfx[i : i + len(y)] += y[: max(0, len(sfx) - i)]
    sfx = sfx[:total]
    pk = float(np.abs(sfx).max())
    if pk > 0.9:
        sfx *= 0.9 / pk
    write_wav(out / "voice_cut.wav", voice)
    write_wav(out / "sfx.wav", sfx)
    print(f"voice_cut.wav {total / SR:.3f}s  sfx.wav peak={np.abs(sfx).max():.2f}  events={len(plan)}")

if __name__ == "__main__":
    main()
