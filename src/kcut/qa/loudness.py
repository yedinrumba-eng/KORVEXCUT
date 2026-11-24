"""The `loudness` check of `kcut qa` (spec S1.9a, 001.15 T3).

The video is measured with `ebur128=peak=true:framelog=quiet` (`audio/loudnorm.ebur128_args` and
`parse_ebur128`, S1.8b): the `Summary` is read by the parser and nothing of the raw text is shown.
`|I - target| <= tolerance` and `TP <= max_tp`; an `I` that could not be measured (silence) is a
`fail` with its reason, and a `TP` that could not be measured counts as under the ceiling.
"""

from pathlib import Path

from kcut import proc
from kcut.audio.loudnorm import EburMeasure, ebur128_args, parse_ebur128
from kcut.config.model import QaSection
from kcut.qa.report import Check

NO_LOUDNESS_ES = "no se pudo medir la sonoridad: el audio está en silencio"
_EPSILON = 1e-9  # the figures are decimals read from text; a limit is a closed interval


def measure_args(ffmpeg: Path, video: Path) -> list[str]:
    """`ebur128` over the first audio stream of `video`. Only `salida/vN.mp4` is measured, which
    kcut made and has no metadata of the user (spec 0.8)."""
    return ebur128_args(ffmpeg, ["-i", str(video)])


def measure_video(video: Path, log: Path | None, timeout_s: float) -> EburMeasure:
    """`I`, `TP` and `LRA` of the audio of `video`, in `timeout_s` at most."""
    args = measure_args(proc.tool_path("ffmpeg"), video)
    result = proc.run(args, log=log, timeout_s=timeout_s, capture_stderr=True)
    return parse_ebur128(result.stderr)


def check_loudness(measure: EburMeasure, qa: QaSection, target_lufs: float) -> Check:
    """The check from a measure: `target_lufs` is `audio.target_lufs` of the project, and the
    tolerance and the ceiling are the `[qa]` section."""
    loudness, peak = measure.I, measure.TP
    data: dict[str, object] = {
        "I_LUFS": loudness,
        "TP_dBTP": peak,
        "LRA": measure.LRA,
        "target": target_lufs,
        "tolerance": qa.lufs_tolerance,
        "max_tp": qa.max_tp,
    }
    if loudness is None:
        return Check("loudness", "fail", data, NO_LOUDNESS_ES)
    near = abs(loudness - target_lufs) <= qa.lufs_tolerance + _EPSILON
    under = peak is None or peak <= qa.max_tp + _EPSILON
    return Check("loudness", "pass" if near and under else "fail", data)
