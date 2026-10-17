"""Sync two recordings of the same scene: loudness-envelope correlation, then a raw-audio refine.

Technique of `piloto/sync.py`. `offset_ms` means the member's t=0 falls at `t=offset_ms` of the
master (positive: the member started recording later).
"""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from kcut.audio.wavio import read_wav_s16_mono
from kcut.config.model import SyncSection
from kcut.errors import ProjectError
from kcut.ingest.sync_reasons import (
    REASON_AMBIGUOUS,
    REASON_RATIO,
    REASON_SCORE,
    REASON_WEAK_REFINE,
)

# Version of the sync algorithm; it is stored with every result (001.7, point 15). A stored result
# is reused only if it carries the current version, so ANY change that can alter what a pair
# gives (floors, thresholds, new checks) must raise this number. 001.7 is version 2; everything
# before counts as 1.
SYNC_VERSION = 2
HOP_MS = 5
_EXCLUDE_MS = 2000
_MIN_OVERLAP_S = 10
# Lags overlapping less than min(10 s, this fraction of the shorter clip) are ignored (spec
# 001.5). With 0.5 a secondary peak at a small overlap was inflated by the normalization and the
# spec's own synthetic camera B was rejected (ratio 1.39 < 1.5); with 0.75 it is 1.77.
MIN_OVERLAP_FRACTION = 0.75
# Short clips only (001.7): the best lag with this looser floor is also computed, and a pair whose
# two best lags differ by more than AMBIGUITY_LAG_MS is rejected as ambiguous. Periodic audio
# (tones, a music loop) can make the wrong lag win at 0.75 and still correlate strongly.
AMBIGUITY_FLOOR_FRACTION = 0.5
AMBIGUITY_LAG_MS = 2000
_MIN_WINDOW_S = 0.2
_MIN_DRIFT_OVERLAP_S = 30


@dataclass(frozen=True)
class CoarseResult:
    offset_ms: float
    score: float
    second: float
    ratio: float
    loose_offset_ms: float | None = None  # best lag at the looser floor; None when not computed


@dataclass(frozen=True)
class DriftResult:
    drift_ms: int | None
    windows: int


@dataclass(frozen=True)
class SyncResult:
    accepted: bool
    offset_ms: int
    score: float
    second: float
    ratio: float
    drift_ms: int | None
    drift_windows: int
    reason: str | None
    drift_warning: bool
    refine_corr: float | None = None
    lag_a_ms: int | None = None  # only for `ambiguous`: best lag at the 0.75 floor
    lag_b_ms: int | None = None  # only for `ambiguous`: best lag at the 0.5 floor


def envelope(x: NDArray[np.float32], sr: int, hop_ms: int = HOP_MS) -> NDArray[np.float32]:
    """RMS per `hop_ms` block, `log1p(rms * 100)`, z-normalized (all zeros if it is flat)."""
    hop = sr * hop_ms // 1000
    if hop < 1:
        raise ValueError("hop_ms is shorter than one sample")
    blocks = len(x) // hop
    if blocks == 0:
        return np.zeros(0, dtype=np.float32)
    shaped = x[: blocks * hop].astype(np.float64).reshape(blocks, hop)
    env = np.log1p(np.sqrt((shaped**2).mean(axis=1)) * 100.0)
    return ((env - env.mean()) / (env.std() + 1e-9)).astype(np.float32)


def coarse_offset(
    master_env: NDArray[np.float32], member_env: NDArray[np.float32], hop_ms: int
) -> CoarseResult:
    """Cross-correlate two envelopes. Every lag is scored as `corr / overlap(lag)`, so a partial
    overlap is not punished; lags with too little overlap are ignored (they are mostly noise)."""
    from scipy import signal  # lazy: importing scipy.signal costs ~1 s on every CLI start

    m = master_env.astype(np.float64)
    b = member_env.astype(np.float64)
    if len(m) == 0 or len(b) == 0:
        return CoarseResult(0.0, 0.0, 0.0, math.inf)
    corr = signal.fftconvolve(m, b[::-1], mode="full")
    lags = np.arange(len(corr)) - (len(b) - 1)
    overlap = np.minimum(len(m), lags + len(b)) - np.maximum(0, lags)
    shorter, cap = min(len(m), len(b)), _MIN_OVERLAP_S * 1000 / hop_ms
    valid = overlap >= min(cap, MIN_OVERLAP_FRACTION * shorter)
    if not valid.any():
        return CoarseResult(0.0, 0.0, 0.0, math.inf)
    normalized = corr / np.maximum(overlap, 1)
    scored = np.where(valid, normalized, -np.inf)
    peak = int(np.argmax(scored))
    score = float(scored[peak])
    guard = round(_EXCLUDE_MS / hop_ms)
    far = np.concatenate([scored[: max(0, peak - guard)], scored[peak + guard + 1 :]])
    far = far[np.isfinite(far)]
    second = float(far.max()) if far.size else 0.0
    ratio = score / second if second > 0 else math.inf
    loose_ms = None
    if MIN_OVERLAP_FRACTION * shorter < cap:  # the fraction, not the 10 s cap, sets the floor
        loose = np.where(overlap >= AMBIGUITY_FLOOR_FRACTION * shorter, normalized, -np.inf)
        loose_ms = float(lags[int(np.argmax(loose))]) * hop_ms
    return CoarseResult(float(lags[peak]) * hop_ms, score, second, ratio, loose_ms)


def refine_offset(
    master: NDArray[np.float32],
    member: NDArray[np.float32],
    sr: int,
    coarse_ms: float,
    search_ms: int = 50,
    step: int = 4,
    window_s: float = 60.0,
) -> tuple[float, float]:
    """Refine on raw audio: window of up to 60 s at the centre of the overlap, normalized dot
    product for every shift in `coarse_ms +- search_ms` (every `step` samples). Returns the best
    `(offset_ms, correlation)`; with no usable overlap, `(coarse_ms, 0.0)`."""
    c, w = round(coarse_ms * sr / 1000), round(search_ms * sr / 1000)
    lo, end = _valid_range(len(master), len(member), c, w)
    if end - lo < _MIN_WINDOW_S * sr:
        return coarse_ms, 0.0
    length = min(end - lo, int(window_s * sr))
    start = lo + (end - lo - length) // 2
    off, corr = _best_shift(master, member, start, length, c, w, step)
    return off * 1000.0 / sr, corr


def drift(
    master: NDArray[np.float32],
    member: NDArray[np.float32],
    sr: int,
    offset_ms: float,
    window_s: float = 10,
    hop_s: float = 10,
    search_ms: int = 20,
    step: int = 2,
    min_corr: float = 0.3,
) -> DriftResult:
    """Spread of the refined offset across windows. Needs 30 s of overlap, else `None`."""
    c, w = round(offset_ms * sr / 1000), round(search_ms * sr / 1000)
    overlap = min(len(master), c + len(member)) - max(0, c)
    if overlap < _MIN_DRIFT_OVERLAP_S * sr:
        return DriftResult(None, 0)
    lo, end = _valid_range(len(master), len(member), c, w)
    length, hop = int(window_s * sr), int(hop_s * sr)
    found: list[float] = []
    for start in range(lo, end - length + 1, hop):
        off, corr = _best_shift(master, member, start, length, c, w, step)
        if corr >= min_corr:
            found.append(off * 1000.0 / sr)
    if not found:
        return DriftResult(None, 0)
    return DriftResult(round(max(found) - min(found)), len(found))


def sync_pair(master_wav: Path, member_wav: Path, cfg: SyncSection) -> SyncResult:
    """Sync one wav16 against the master's and decide whether to accept it."""
    master, sr = read_wav_s16_mono(master_wav)
    member, member_sr = read_wav_s16_mono(member_wav)
    if sr != member_sr:
        raise ProjectError("los wav16 de sincronía tienen distinta frecuencia de muestreo")
    return sync_arrays(master, member, sr, cfg)


def sync_arrays(
    master: NDArray[np.float32], member: NDArray[np.float32], sr: int, cfg: SyncSection
) -> SyncResult:
    """The decision of `sync_pair` on audio already in memory.

    Accepted when the envelope `score` and `ratio` pass **and** the raw-audio refinement
    correlates at least `min_refine_corr`: a wrong lag can win the envelope test on short clips,
    but it never correlates on the raw samples (0.012-0.019 against 0.99 for the true one).
    Periodic audio is the exception (tones: the wrong lag refines at 0.85), so the order ends
    with the ambiguity check of 001.7: score, ratio, refine, weak refine, ambiguity.
    """
    coarse = coarse_offset(envelope(master, sr), envelope(member, sr), HOP_MS)
    coarse_ms = round(coarse.offset_ms)
    if coarse.score < cfg.min_score:
        return _rejected(coarse, coarse_ms, REASON_SCORE)
    if coarse.ratio < cfg.min_ratio:
        return _rejected(coarse, coarse_ms, REASON_RATIO)
    refined_ms, refine_corr = refine_offset(master, member, sr, coarse.offset_ms)
    if refine_corr < cfg.min_refine_corr:
        reason = (
            f"{REASON_WEAK_REFINE}: la correlacion del refinado ({refine_corr:.3f}) "
            f"esta bajo min_refine_corr ({cfg.min_refine_corr})"
        )
        return _rejected(coarse, round(refined_ms), reason, refine_corr)
    loose = coarse.loose_offset_ms
    if loose is not None and abs(loose - coarse.offset_ms) > AMBIGUITY_LAG_MS:
        lags = (coarse_ms, round(loose))
        reason = f"{REASON_AMBIGUOUS}: dos desfases posibles ({lags[0]} ms y {lags[1]} ms)"
        return _rejected(coarse, round(refined_ms), reason, refine_corr, lags)
    spread = drift(master, member, sr, refined_ms)
    warn = spread.drift_ms is not None and spread.drift_ms > cfg.max_drift_ms
    return SyncResult(
        True,
        round(refined_ms),
        coarse.score,
        coarse.second,
        coarse.ratio,
        spread.drift_ms,
        spread.windows,
        None,
        warn,
        refine_corr,
    )


def _rejected(
    coarse: CoarseResult,
    offset_ms: int,
    reason: str,
    refine_corr: float | None = None,
    lags: tuple[int, int] | None = None,
) -> SyncResult:
    lag_a, lag_b = lags if lags is not None else (None, None)
    return SyncResult(
        False,
        offset_ms,
        coarse.score,
        coarse.second,
        coarse.ratio,
        None,
        0,
        reason,
        False,
        refine_corr,
        lag_a,
        lag_b,
    )


def _valid_range(len_master: int, len_member: int, c: int, w: int) -> tuple[int, int]:
    """Master-time range `[lo, end)` where a window fits for every shift in `c +- w`."""
    return max(0, c + w), min(len_master, len_member + c - w)


def _best_shift(
    master: NDArray[np.float32],
    member: NDArray[np.float32],
    start: int,
    length: int,
    c: int,
    w: int,
    step: int,
) -> tuple[int, float]:
    """Best shift `off` (samples) in `c - w .. c + w` for the master window `[start, start+length)`.

    The member window for a shift is `member[start - off : start - off + length]`. All shifts
    are scored at once with one FFT correlation and a running sum of squares.
    """
    from scipy import signal  # lazy, see coarse_offset

    a = master[start : start + length].astype(np.float64)
    norm_a = float(np.sqrt(a @ a))
    if norm_a < 1e-9:
        return c, 0.0
    base = start - (c + w)
    b = member[base : base + length + 2 * w].astype(np.float64)
    dots = signal.correlate(b, a, mode="valid", method="fft")
    running = np.concatenate(([0.0], np.cumsum(b * b)))
    energy = running[length : length + 2 * w + 1] - running[: 2 * w + 1]
    ncc = dots / (norm_a * np.sqrt(np.maximum(energy, 0.0)) + 1e-12)
    candidates = np.arange(2 * w, -1, -step)
    best = int(candidates[int(np.argmax(ncc[candidates]))])
    return c + w - best, float(ncc[best])
