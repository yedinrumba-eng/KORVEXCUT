"""Energy of the audio, measured on the samples (lesson 2: Whisper's timestamps lie).

Everything here is pure: arrays and lists in, arrays and lists out. A "run" is a half-open range
`(start_ms, end_ms)` of the clip's own clock; lists of runs are sorted and do not overlap.
"""

from bisect import bisect_right
from collections.abc import Iterable, Sequence

import numpy as np
from numpy.typing import NDArray

from kcut.transcribe.model import Word

Run = tuple[int, int]
_FLOOR = 1e-9  # keeps log10 finite on digital silence: 20*log10(1e-9) = -180 dB
_BEYOND = 1 << 62


def rms_db(x: NDArray[np.float32], sr: int, hop_ms: int = 10) -> NDArray[np.float32]:
    """RMS level in dB (`20*log10(sqrt(mean(x^2)) + 1e-9)`) of each `hop_ms` block of `x`.

    Blocks do not overlap. The last block may be shorter and is averaged over its own samples,
    so the blocks always cover the whole signal.
    """
    return rms_db_stream([x], sr, hop_ms)


def rms_db_stream(
    chunks: Iterable[NDArray[np.float32]], sr: int, hop_ms: int = 10
) -> NDArray[np.float32]:
    """Same result as `rms_db` on the concatenation of `chunks`, with flat memory: a long wav is
    read in pieces and each piece only holds its own samples (chunks need not be block-aligned)."""
    block = max(1, sr * hop_ms // 1000)
    levels: list[NDArray[np.float32]] = []
    carry = np.zeros(0, dtype=np.float32)
    for chunk in chunks:
        data = np.concatenate([carry, np.asarray(chunk, dtype=np.float32)])
        whole = (len(data) // block) * block
        if whole:
            levels.append(_levels(data[:whole].reshape(-1, block)))
        carry = data[whole:]
    if len(carry):
        levels.append(_levels(carry.reshape(1, -1)))
    if not levels:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(levels).astype(np.float32)


def _levels(blocks: NDArray[np.float32]) -> NDArray[np.float32]:
    power = np.mean(np.square(blocks, dtype=np.float64), axis=1)
    return (20.0 * np.log10(np.sqrt(power) + _FLOOR)).astype(np.float32)


def silence_runs(
    db: NDArray[np.float32], hop_ms: int, threshold_db: float, min_ms: int
) -> list[Run]:
    """Ranges `[start_ms, end_ms)` where the level is under `threshold_db` for `min_ms` or more."""
    return [
        (a * hop_ms, b * hop_ms)
        for a, b in _blocks_where(db < threshold_db)
        if (b - a) * hop_ms >= min_ms
    ]


def voiced_without_words(
    db: NDArray[np.float32],
    hop_ms: int,
    threshold_db: float,
    words: Sequence[Word],
    min_ms: int = 250,
    tol_ms: int = 50,
) -> list[Run]:
    """Stretches at or above `threshold_db` for `min_ms` or more that touch no word.

    A word touches a stretch when the word, widened by `tol_ms` on both sides, overlaps it:
    a laugh, a cough or a word Whisper missed shows up here. A stretch that touches a word
    is not reported, however long it is.
    """
    starts = sorted((w.s_ms, w.e_ms) for w in words)
    reach = (
        np.maximum.accumulate(np.array([e for _, e in starts], dtype=np.int64)) if starts else None
    )
    found: list[Run] = []
    for a, b in _blocks_where(db >= threshold_db):
        start, end = a * hop_ms, b * hop_ms
        if end - start < min_ms:
            continue
        # words that begin before the stretch ends (widened) are candidates; the running maximum
        # of their ends says whether any of them reaches back into the stretch
        count = bisect_right(starts, (end + tol_ms - 1, _BEYOND))
        if count and reach is not None and int(reach[count - 1]) + tol_ms > start:
            continue
        found.append((start, end))
    return found


def word_in_silence(word: Word, runs: Sequence[Run]) -> bool:
    """True if the whole word lies inside one silence run (`runs` sorted and disjoint)."""
    index = bisect_right(runs, (word.s_ms, _BEYOND)) - 1
    return index >= 0 and word.e_ms <= runs[index][1]


def containing_run(runs: Sequence[Run], t_ms: int) -> Run | None:
    """The run with `start <= t_ms < end`, or None (`runs` sorted and disjoint)."""
    index = bisect_right(runs, (t_ms, _BEYOND)) - 1
    if index >= 0 and t_ms < runs[index][1]:
        return runs[index]
    return None


def _blocks_where(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """Maximal `[first, end)` block ranges where `mask` is true."""
    if not len(mask):
        return []
    padded = np.concatenate([[False], mask, [False]]).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2], strict=True)]
