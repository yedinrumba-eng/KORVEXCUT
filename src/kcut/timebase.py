"""Frame, millisecond and audio-sample arithmetic. Integers only: floats never compare times."""

from kcut.errors import ProjectError

ALLOWED_FPS: frozenset[int] = frozenset({24, 25, 30, 48, 50, 60})
SAMPLE_RATE = 48000
# One cap for every stored time (lags, offsets, drift) and for `ingest.max_duration_h`: 48 h.
MAX_TIME_MS = 48 * 3_600_000


def spf(fps: int) -> int:
    """Audio samples (48 kHz) per video frame: 2000, 1920, 1600, 1000, 960 or 800."""
    if fps not in ALLOWED_FPS:
        allowed = ", ".join(str(f) for f in sorted(ALLOWED_FPS))
        raise ProjectError(f"fps {fps} no permitido; usa uno de: {allowed}")
    return SAMPLE_RATE // fps


def rdiv(x: int, d: int) -> int:
    """`x / d` rounded to nearest, halves up, in pure integer arithmetic."""
    if d <= 0:
        raise ValueError("rdiv needs a positive divisor")
    return (2 * x + d) // (2 * d)


def ms_to_f_floor(ms: int, fps: int) -> int:
    """Whole frames that fit in `ms` milliseconds (compares ms*fps with frames*1000)."""
    return (ms * fps) // 1000


def ms_to_f_ceil(ms: int, fps: int) -> int:
    """Smallest frame count that covers `ms` milliseconds."""
    return -((-ms * fps) // 1000)


def ms_to_f_round(ms: int, fps: int) -> int:
    """Nearest frame to `ms` milliseconds, halves up."""
    return rdiv(ms * fps, 1000)


def f_to_ms_round(f: int, fps: int) -> int:
    """Nearest millisecond to frame `f`, halves up."""
    return rdiv(f * 1000, fps)


def fmt_tc(f: int, fps: int) -> str:
    """Human timecode `mm:ss.s` (tenths of a second, nearest)."""
    sign = "-" if f < 0 else ""
    tenths = rdiv(abs(f) * 10, fps)
    minutes, rest = divmod(tenths, 600)
    return f"{sign}{minutes:02d}:{rest // 10:02d}.{rest % 10}"


def fmt_s(f: int, fps: int) -> str:
    """Seconds with two decimals (`12.34`), nearest hundredth."""
    sign = "-" if f < 0 else ""
    hundredths = rdiv(abs(f) * 100, fps)
    return f"{sign}{hundredths // 100}.{hundredths % 100:02d}"
