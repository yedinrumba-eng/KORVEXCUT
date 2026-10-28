"""The bus of sound effects: every event of the plan made and summed into one track (spec S1.8a,
001.15; lesson 10: the level is set with `gain`, `bus_gain_db` and the windows, and the bus is
**not** normalized).

Pure. The track has `total` samples (`frames * spf`); a sound that falls partly outside it is cut at
the edge (the A08 warning said so in `resolve_events`), and the sum is in float32.
"""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from kcut.audio.sfx_events import SfxEvent
from kcut.audio.sfx_library import SFX
from kcut.errors import InternalError

Track = NDArray[np.float32]


def build_sfx_bus(events_resolved: Sequence[SfxEvent], total: int, spf: int, sr: int) -> Track:
    """The sum of `events_resolved` in `total` samples. For each one: `n` is the `fixed_n` of its
    type or `dur_f * spf`; `y = fn(n, sr, **params) * gain`; and its first sample falls at
    `at_f * spf` (`start`), at `at_f * spf - n // 2` (`center`) or at
    `at_f * spf - (n - 1)` (`end`). What falls outside `[0, total)` is cut. Nothing is
    normalized."""
    bus = np.zeros(total, dtype=np.float32)
    for event in events_resolved:
        sfx = SFX[event.type]
        if sfx.fixed_n is not None:
            n = sfx.fixed_n
        elif event.dur_f is not None:
            n = event.dur_f * spf
        else:
            raise InternalError(f"el evento {event.type} necesita dur_f y no lo trae")
        y = sfx.fn(n, sr, **_params(event)) * event.gain
        first = event.at_f * spf
        if event.align == "center":
            first -= n // 2
        elif event.align == "end":
            first -= n - 1
        low, high = max(first, 0), min(first + n, total)
        if high > low:
            bus[low:high] += y[low - first : high - first]
    return bus


def _params(event: SfxEvent) -> dict[str, float]:
    """The parameters the type takes, as the keywords of its function: only those that are there."""
    named = {"seed": event.seed, "freq": event.freq, "rate": event.rate}
    return {name: value for name, value in named.items() if value is not None}
