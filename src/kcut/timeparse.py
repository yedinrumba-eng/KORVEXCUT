"""The times a person types for `kcut view` and `kcut frames` (spec S1.4, 001.15).

Pure. No step uses `float`: `0.15s` is exactly 150 ms, and 150 ms at 30 fps is frame 5 (with a
float it came out as 4).
"""

import re
from fractions import Fraction

from kcut.errors import UsageError
from kcut.timebase import ms_to_f_round

MAX_LEN = 32  # characters: nobody types a time longer than this
_FRAMES = re.compile(r"[0-9]+")
_SECONDS = re.compile(r"([0-9]+(?:\.[0-9]+)?)s")
_CLOCK = re.compile(r"([0-9]+):([0-9]{1,2}(?:\.[0-9]+)?)")
_MINUTE = 60
_HALF = Fraction(1, 2)


def parse_time(s: str, fps: int) -> int:
    """Frames (whole, of the source clock) for a time typed as `90` (frames), `3s`, `2.5s`,
    `1:02` or `0:03.5` (minutes:seconds). Anything else is a UsageError.

    Seconds are read as an exact fraction, turned into whole milliseconds (halves up) and then
    into the nearest frame, as `timebase.ms_to_f_round` does with every measured time.
    """
    if len(s) > MAX_LEN:
        raise UsageError(f"el tiempo es demasiado largo (más de {MAX_LEN} caracteres)")
    if _FRAMES.fullmatch(s):
        return int(s)
    seconds = _seconds(s)
    if seconds is None:
        raise UsageError(
            f"no entiendo el tiempo {s!r}: usa frames (90), segundos (3s, 2.5s) o mm:ss (1:02)"
        )
    ms = int(seconds * 1000 + _HALF)  # floor of a positive Fraction + 1/2: halves up
    return ms_to_f_round(ms, fps)


def _seconds(s: str) -> Fraction | None:
    """The seconds a `3.5s` or `mm:ss.d` text says, or None if it is neither."""
    match = _SECONDS.fullmatch(s)
    if match:
        return Fraction(match.group(1))
    match = _CLOCK.fullmatch(s)
    if match is None:
        return None
    rest = Fraction(match.group(2))
    if rest >= _MINUTE:
        raise UsageError(f"los segundos de {s!r} tienen que ser menos de 60")
    return int(match.group(1)) * _MINUTE + rest
