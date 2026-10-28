"""The music of `mode: synth`, made sample by sample (spec S1.8b, 001.15; port of `piloto/music.py`,
which is read as a reference and not imported).

A pad of detuned saws, a bass, an arpeggio of triangles and a soft kit of drums, on a grid of bars
that begins at `origin_f`. The tempo is `bpm` (the pilot's seconds are at 120 bpm: `BEAT = 60/bpm`,
`BAR = 4 * BEAT`); bar `b` begins at `origin_s + b * BAR` and before `origin_s` there is silence.
`dur = (total - origin_f * spf) / sr` is what is left of the video from the origin. All the buffers
have `total + sr` samples and are cut to `total` at the end. No global chance: the hi-hat is
`default_rng(9)`.

`synth_layers` gives the four layers before the end (they are exported for the tests) and
`synth_music` is their sum plus the end: a linear fade of 1.2 s, a high-pass at 35 Hz and the peak
at 0.9.
"""

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.signal import butter, lfilter

from kcut.audio.chords import parse_chord
from kcut.audio.music_model import SynthCfg
from kcut.timebase import spf as samples_per_frame

Track = NDArray[np.float32]
FADE_S = 1.2  # the linear fade of the end
PEAK = 0.9
_PAD_DETUNE = (-0.07, 0.07)  # semitones
_BASS_NOTES = ((0.0, 0.45, 1.0), (2.0, 0.45, 0.85), (3.5, 0.2, 0.55))  # beats, seconds, gain
_ARP_S = 0.22
_KICK_S = 0.25
_HAT_N = 1920  # 40 ms at 48 kHz


@dataclass(frozen=True)
class MusicLayers:
    """The four layers before the end of `synth_music`, each one `total` samples."""

    pad: Track
    bass: Track
    arp: Track
    drums: Track


def _midi(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _filter(x: Track, fc: float, kind: str, sr: int) -> Track:
    b, a = butter(2, fc / (sr / 2), kind)
    return np.asarray(lfilter(b, a, x), dtype=np.float32)


def _add(buf: Track, sig: Track, t: float, sr: int) -> None:
    """`sig` summed into `buf` at the sample `int(round(t * sr))`; what falls outside is cut."""
    i = round(t * sr)
    if i >= len(buf):
        return
    n = min(len(sig), len(buf) - i)
    buf[i : i + n] += sig[:n]


class _Grid:
    """The tempo, the chords and the origin of one synthesis, so the layers share them."""

    def __init__(self, cfg: SynthCfg, total: int, fps: int, sr: int) -> None:
        self.cfg, self.fps, self.sr = cfg, fps, sr
        self.beat = 60.0 / cfg.bpm
        self.bar = 4 * self.beat
        self.origin_s = cfg.origin_f / fps
        self.dur = (total - cfg.origin_f * samples_per_frame(fps)) / sr
        self.n_bars = math.ceil(self.dur / self.bar) + 1
        self.size = total + sr
        self.eighths = int(self.dur / (self.beat / 2))  # the `k` of the arpeggio and the drums

    def chord(self, bar: int) -> tuple[int, tuple[int, int, int]]:
        return parse_chord(self.cfg.progression[bar % len(self.cfg.progression)])

    def quiet(self, t: float) -> bool:
        """Is the instant `t` of the output one where the drums are silent? A window mutes from
        0.05 s before its start (a hit that would begin just before it) up to its end, and
        `stop_drums_f` mutes everything from there on."""
        for start, end in self.cfg.mute_drums:
            if start / self.fps - 0.05 <= t < end / self.fps:
                return True
        stop = self.cfg.stop_drums_f
        return stop is not None and t >= stop / self.fps


def synth_layers(cfg: SynthCfg, total: int, fps: int, sr: int) -> MusicLayers:
    """The pad, the bass, the arpeggio and the drums of `cfg`, each one `total` samples long."""
    grid = _Grid(cfg, total, fps, sr)
    pad, bass, arp = _pad(grid), _bass(grid), _arp(grid)
    drums = _drums(grid) if cfg.drums else np.zeros(grid.size, dtype=np.float32)
    return MusicLayers(pad[:total], bass[:total], arp[:total], drums[:total])


def synth_music(cfg: SynthCfg, total: int, fps: int, sr: int) -> Track:
    """The music of `cfg`, exactly `total` samples: the sum of its layers, a fade of 1.2 s at the
    end (less if the video is shorter), a high-pass at 35 Hz and the peak at 0.9."""
    layers = synth_layers(cfg, total, fps, sr)
    out = layers.pad + layers.bass + layers.arp + layers.drums
    if out.size == 0:
        return out
    fade = min(int(FADE_S * sr), out.size)
    out[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    out = _filter(out, 35.0, "high", sr)
    out *= PEAK / max(1e-6, float(np.abs(out).max()))
    return out


def _pad(grid: _Grid) -> Track:
    """Per bar, saws of the three notes and the first one an octave up, each detuned by 0.07
    semitones each way, with an attack of 0.18 s, all through a low-pass at 1100 Hz. The last bar
    of the video is longer (1.6 s more) and fades out in 1.4 s."""
    sr = grid.sr
    pad = np.zeros(grid.size, dtype=np.float32)
    for b in range(grid.n_bars):
        _, tones = grid.chord(b)
        t0 = grid.origin_s + b * grid.bar
        last = b * grid.bar + grid.bar >= grid.dur
        length = grid.bar + (1.6 if last else 0.25)
        t = np.arange(int(length * sr)) / sr
        y = np.zeros_like(t, dtype=np.float32)
        for m in (*tones, tones[0] + 12):
            for det in _PAD_DETUNE:
                ph = _midi(m + det) * t
                y += (2 * (ph % 1.0) - 1).astype(np.float32)
        env = np.clip(t / 0.18, 0, 1) * np.clip((length - t) / (1.4 if last else 0.25), 0, 1)
        seg = (y * env * 0.06).astype(np.float32)
        i = int(t0 * sr)
        n = min(len(seg), grid.size - i)
        if n > 0:
            pad[i : i + n] += seg[:n]
    return _filter(pad, 1100.0, "low", sr)


def _bass(grid: _Grid) -> Track:
    """The root on beats 1 and 3 and a pickup on the "and" of 4: a sine and its octave at 0.35."""
    sr = grid.sr
    bass = np.zeros(grid.size, dtype=np.float32)
    for b in range(grid.n_bars):
        root, _ = grid.chord(b)
        for beats, seconds, gain in _BASS_NOTES:
            rel = b * grid.bar + beats * grid.beat
            if rel >= grid.dur:
                continue
            t = np.arange(int(seconds * sr)) / sr
            f = _midi(root)
            y = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)
            env = np.clip(t / 0.008, 0, 1) * np.exp(-t * 4.5)
            _add(bass, (y * env * 0.22 * gain).astype(np.float32), grid.origin_s + rel, sr)
    return bass


def _arp(grid: _Grid) -> Track:
    """Eighth notes of triangles, one octave above the pad, of the chord of their bar (an eighth
    note `k` is in bar `k // 8`), through a low-pass at 3200 Hz."""
    sr = grid.sr
    arp = np.zeros(grid.size, dtype=np.float32)
    t = np.arange(int(_ARP_S * sr)) / sr
    for k in range(grid.eighths):
        _, tones = grid.chord(k // 8)
        m = (*tones, tones[0] + 12)[k % 4] + 12
        ph = _midi(m) * t
        tri = (2 * np.abs(2 * (ph % 1.0) - 1) - 1).astype(np.float32)
        seg = tri * np.exp(-t * 16) * 0.05
        i = int((grid.origin_s + k * grid.beat / 2) * sr)
        arp[i : i + len(seg)] += seg[: max(0, grid.size - i)]
    return _filter(arp, 3200.0, "low", sr)


def _drums(grid: _Grid) -> Track:
    """A kick on beats 1 and 3 and a hi-hat off the beat. A hit in a silent instant is jumped over
    without taking numbers from `rng`, so muting a bar does not change the hats that come after."""
    sr = grid.sr
    drums = np.zeros(grid.size, dtype=np.float32)
    rng = np.random.default_rng(9)
    for k in range(grid.eighths):
        t_out = grid.origin_s + k * grid.beat / 2
        if grid.quiet(t_out):
            continue
        if k % 4 == 0:
            t = np.arange(int(_KICK_S * sr)) / sr
            f = 48 + 90 * np.exp(-t * 35)
            y = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 9)
            _add(drums, (y * 0.30).astype(np.float32), t_out, sr)
        if k % 2 == 1:
            noise = _filter(rng.standard_normal(_HAT_N).astype(np.float32), 7500.0, "high", sr)
            env = np.exp(-np.arange(_HAT_N) / sr * 120)
            _add(drums, (noise * env * 0.05).astype(np.float32), t_out, sr)
    return drums
