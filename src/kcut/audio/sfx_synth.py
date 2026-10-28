"""The sound effects, synthesized (spec S1.8a, 001.15): the 13 functions of `piloto/audio.py`, with
the same formulas and the same seeds, as functions of the number of samples.

Every function is `(n, sr, **params) -> float32[n]`: `n` is the length in samples (the library says
which types have a fixed one) and `sr` the sample rate. The seconds of the pilot (the envelopes, the
`dur - 0.05` of `typing`, the `(dur - t) / 0.35` of `pad`) are worked out from `dur = n / sr`.
Nothing is random but what a seed says: each function makes its own `default_rng`, so the same
call is always the same bytes, and nothing global is touched. Peaks are those of the pilot (no
function normalizes): a gain is what the bus is for.
"""

import numpy as np
from numpy.typing import NDArray

Audio = NDArray[np.float32]
Curve = NDArray[np.floating]


def env_ad(n: int, sr: int, attack: float, decay: float) -> NDArray[np.float64]:
    """Attack (linear) and decay (exponential) envelope of `n` samples, seconds as arguments."""
    t = np.arange(n) / sr
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return np.asarray(a * np.exp(-np.maximum(t - attack, 0) / max(decay, 1e-4)))


def lowpass(x: Audio, cutoff: Curve | float, sr: int) -> Audio:
    """One-pole low pass whose cutoff (Hz) may change from sample to sample, as the pilot's."""
    c = np.broadcast_to(np.asarray(cutoff, dtype=np.float32), x.shape)
    alpha = 1.0 - np.exp(-2 * np.pi * c / sr)
    y = np.empty_like(x)
    acc = np.float32(0.0)
    for i in range(len(x)):
        acc += alpha[i] * (x[i] - acc)
        y[i] = acc
    return y


def whoosh(n: int, sr: int, *, seed: int = 1) -> Audio:
    """Filtered noise that sweeps up and down: a change of shot, a graphic that comes in."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n).astype(np.float32)
    t = np.linspace(0, 1, n, dtype=np.float32)
    sweep = 300 + 5200 * np.sin(np.pi * t) ** 2
    y = lowpass(noise, sweep, sr) - lowpass(noise, sweep * 0.25, sr)
    return (y * np.clip(np.sin(np.pi * t), 0.0, 1.0) ** 1.5 * 0.9).astype(np.float32)


def boom(n: int, sr: int, *, seed: int = 7) -> Audio:
    """A low hit that falls in pitch, with a click of noise on top."""
    t = np.arange(n) / sr
    f = 38 + 70 * np.exp(-t * 18)
    ph = 2 * np.pi * np.cumsum(f) / sr
    rng = np.random.default_rng(seed)
    click = lowpass(rng.standard_normal(n).astype(np.float32), 900.0, sr) * np.exp(-t * 60)
    return ((np.sin(ph) * env_ad(n, sr, 0.004, 0.28) + click * 0.6) * 0.95).astype(np.float32)


def pop(n: int, sr: int, *, freq: float = 820.0) -> Audio:
    """A short bubble: a sine that starts higher than `freq` and falls to it."""
    t = np.arange(n) / sr
    f = freq * (1 + 0.8 * np.exp(-t * 60))
    ph = 2 * np.pi * np.cumsum(f) / sr
    return (np.sin(ph) * env_ad(n, sr, 0.002, 0.035) * 0.55).astype(np.float32)


def shimmer(n: int, sr: int) -> Audio:
    """Four bell-like partials that come in one after the other."""
    t = np.arange(n) / sr
    y = np.zeros(n, dtype=np.float32)
    for k, f in enumerate((2093.0, 2637.0, 3136.0, 4186.0)):
        d = 0.06 * k
        e = np.where(t >= d, np.exp(-(t - d) * 4.5), 0.0)
        y += (np.sin(2 * np.pi * f * t) * e * (1 + 0.3 * np.sin(2 * np.pi * 7 * t))).astype(
            np.float32
        )
    return (y * 0.13 * np.clip(t / 0.02, 0, 1)).astype(np.float32)


def key(n: int, sr: int, *, seed: int = 0) -> Audio:
    """One key of a keyboard: high-passed noise and a short low thump. `seed` picks which key."""
    t = np.arange(n) / sr
    rng = np.random.default_rng(100 + seed)
    nz = rng.standard_normal(n).astype(np.float32)
    hp = nz - lowpass(nz, 2500.0, sr)
    return (
        hp * np.exp(-t * 140) * 0.5 + np.sin(2 * np.pi * 180 * t) * np.exp(-t * 90) * 0.25
    ).astype(np.float32)


def click(n: int, sr: int) -> Audio:
    """The click of an interface: a `pop` at 1900 Hz, at 0.8."""
    return pop(n, sr, freq=1900.0) * 0.8


def kick(n: int, sr: int) -> Audio:
    """A bass drum, for a beat."""
    t = np.arange(n) / sr
    f = 46 + 110 * np.exp(-t * 32)
    return (np.sin(2 * np.pi * np.cumsum(f) / sr) * env_ad(n, sr, 0.002, 0.14) * 0.95).astype(
        np.float32
    )


def hat(n: int, sr: int, *, seed: int = 0) -> Audio:
    """A hi-hat: high-passed noise with a very short decay."""
    t = np.arange(n) / sr
    nz = np.random.default_rng(300 + seed).standard_normal(n).astype(np.float32)
    return ((nz - lowpass(nz, 7000.0, sr)) * np.exp(-t * 110) * 0.32).astype(np.float32)


def pad(n: int, sr: int) -> Audio:
    """A short harmonic bed: five sawtooth notes under a slowly moving low pass."""
    dur = n / sr
    t = np.arange(n) / sr
    y = np.zeros(n, dtype=np.float32)
    for f in (110.0, 164.81, 220.0, 261.63, 329.63):  # A minor-ish stack
        ph = 2 * np.pi * f * t
        y += (2 * ((ph / (2 * np.pi)) % 1.0) - 1).astype(np.float32) * 0.18  # saw
    y = lowpass(y, 900.0 + 500.0 * np.sin(2 * np.pi * 0.5 * t) ** 2, sr)
    e = np.clip(t / 0.25, 0, 1) * np.clip((dur - t) / 0.35, 0, 1)
    return (y * e * 0.8).astype(np.float32)


def typing(n: int, sr: int, *, rate: float = 13.0, seed: int = 55) -> Audio:
    """Typing: key `k` (`key` with seed `k`) every `1 / rate` seconds, give or take. `seed` is the
    chance of the rhythm and of the strength of each key."""
    dur = n / sr
    y = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(seed)
    t = 0.0
    k = 0
    while t < dur - 0.05:
        c = key(2400, sr, seed=k) * (0.7 + 0.3 * rng.random())
        i = int(t * sr)
        y[i : i + len(c)] += c[: n - i]
        t += 1.0 / rate * (0.7 + 0.6 * rng.random())
        k += 1
    return y


def riser(n: int, sr: int, *, seed: int = 77) -> Audio:
    """Noise and a tone that rise in pitch and in volume before a hit."""
    t = np.linspace(0, 1, n, dtype=np.float32)
    nz = np.random.default_rng(seed).standard_normal(n).astype(np.float32)
    y = lowpass(nz, 400 + 7000 * t**2, sr) * t**2
    tone = np.sin(2 * np.pi * np.cumsum(220 + 660 * t**2) / sr) * t**2 * 0.25
    return ((y * 0.5 + tone) * 0.8).astype(np.float32)


def blip8(n: int, sr: int) -> Audio:
    """A four-note arpeggio, C E G C, of square waves: `n` is four notes of `n // 4` samples."""
    notes = (523.25, 659.25, 783.99, 1046.5)
    seg = n // 4
    out = []
    for f in notes:
        t = np.arange(seg) / sr
        sq = np.sign(np.sin(2 * np.pi * f * t)).astype(np.float32)
        out.append(sq * np.exp(-t * 18) * 0.22)
    return np.concatenate(out).astype(np.float32)


def powerup(n: int, sr: int) -> Audio:
    """A rising sweep with a shimmer on top: a magical appearance."""
    t = np.arange(n) / sr
    f = 180 + 1400 * (t / t[-1]) ** 1.6
    y = (
        np.sin(2 * np.pi * np.cumsum(f) / sr)
        * np.clip(t / 0.04, 0, 1)
        * np.exp(-np.maximum(t - 0.42, 0) * 25)
    )
    return (y * 0.28 + shimmer(26400, sr) * 0.8).astype(np.float32)
