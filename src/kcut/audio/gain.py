"""Windows of gain over a track (spec S1.8a, 001.15): the way to raise or lower a stretch of the
sound effects (or of the music) without normalizing the whole bus (lesson 10).

Pure. A window is `(start_f, end_f, gain_db)` in frames of the output: from the sample
`start_f * spf` up to (not including) `end_f * spf`.
"""

import numpy as np
from numpy.typing import NDArray

Track = NDArray[np.float32]
RAMP_MS = 10  # the ramp at each edge of a window


def apply_gain_windows(
    x: Track,
    windows: list[tuple[int, int, float]],
    spf: int,
    sr: int,
    ramp_ms: int = RAMP_MS,
) -> Track:
    """`x` with each window's gain applied: `gain_db` as a linear factor `10 ** (db / 20)`, with a
    linear ramp of `ramp_ms` inside each edge of the window (from 1 up to the factor, and from it
    back down to 1, so there is no click) and a gain of exactly 1 outside every window. A window
    shorter than two ramps has the ramps shortened to half of it. The ramps are those of the whole
    window, so a window that goes past the track is cut where the track ends (the gain stays the
    factor there); windows that overlap multiply. `x` is not changed: the result is a new array."""
    envelope = np.ones(len(x), dtype=np.float64)
    ramp = sr * ramp_ms // 1000
    for start_f, end_f, gain_db in windows:
        start, end = start_f * spf, end_f * spf
        low, high = max(start, 0), min(end, len(x))
        if high <= low:
            continue
        factor = 10.0 ** (gain_db / 20.0)
        edge = min(ramp, (end - start) // 2)
        where = np.arange(low, high)
        shape = np.full(high - low, factor, dtype=np.float64)
        if edge > 0:
            rising, falling = where < start + edge, where >= end - edge
            shape[rising] = 1.0 + (factor - 1.0) * (where[rising] - start) / edge
            shape[falling] = factor + (1.0 - factor) * (where[falling] - (end - edge)) / edge
        envelope[low:high] *= shape
    return (x * envelope).astype(np.float32)
