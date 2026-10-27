"""Doctor checks that run ffmpeg on tiny synthetic sources: HDR tone-map chain, soxr and looks."""

from kcut import proc
from kcut.config.load import parse_config
from kcut.config.model import BrandSection
from kcut.config.template import render_template
from kcut.doctor.result import CheckResult
from kcut.errors import KcutError
from kcut.ff.color import HDR_TO_SDR
from kcut.ff.reader import reader_args
from kcut.render.looks import LOOKS, look_chain

_TIMEOUT_S = 60.0
_HDR_SOURCE = (
    "testsrc2=s=64x64:d=0.04,"
    "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc,"
    "format=yuv420p10le"
)
_BASE = ["-hide_banner", "-nostdin", "-loglevel", "error"]
_BUILD_FIX = "usa el build full de gyan.dev (trae zscale, tonemap y soxr)"
_LOOKS_FIX = (
    "usa el build full de gyan.dev (trae colorbalance, curves, vibrance, vignette y colorhold)"
)
_LOOKS_SOURCE = "color=c=gray:s=64x64:d=0.04"
_LOOKS_BYTES = 64 * 64 * 3  # the one frame a look gives back: 12 288 bytes of BGR
_LOOKS_TIMEOUT_S = 30.0


def check_tonemap_chain() -> CheckResult:
    """ffmpeg must run the approved HDR to SDR chain on one HLG frame."""
    args = [
        *_BASE,
        "-f",
        "lavfi",
        "-i",
        _HDR_SOURCE,
        "-vf",
        HDR_TO_SDR,
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    return _run_check("tonemap_chain", args)


def check_soxr() -> CheckResult:
    """ffmpeg must resample with the soxr resampler (used for every wav16/wav48)."""
    args = [
        *_BASE,
        "-f",
        "lavfi",
        "-i",
        "sine=d=0.1",
        "-af",
        "aresample=16000:resampler=soxr",
        "-f",
        "null",
        "-",
    ]
    return _run_check("soxr", args)


def check_looks() -> CheckResult:
    """Every look of `render.looks` has to run in the frame reader, on a 64x64 gray source from
    lavfi, with the brand of the template (accent `#E5FF1F`): exit 0 and one frame of 12 288 bytes
    on stdout (spec S1.5b, 001.15)."""
    try:
        ffmpeg = proc.tool_path("ffmpeg")
    except KcutError as exc:
        return CheckResult("looks", True, False, exc.message_es, _BUILD_FIX)
    brand = _default_brand()
    failed: list[str] = []
    for look_id in LOOKS:
        args = reader_args(
            ffmpeg,
            ["-f", "lavfi", "-i", _LOOKS_SOURCE],
            1,
            rgb_filters=look_chain(look_id, brand),
        )
        try:
            ok = len(proc.run(args, timeout_s=_LOOKS_TIMEOUT_S).stdout) == _LOOKS_BYTES
        except KcutError:
            ok = False
        if not ok:
            failed.append(look_id)
    detail = f"{len(LOOKS) - len(failed)}/{len(LOOKS)}"
    if failed:
        return CheckResult(
            "looks", True, False, f"{detail} fallan: {', '.join(failed)}", _LOOKS_FIX
        )
    return CheckResult("looks", True, True, detail, None)


def _default_brand() -> BrandSection:
    """The brand of a new project: the one `kcut new` writes in `kcut.toml`."""
    text = render_template("doctor", "9:16", 30, "es", "2026-01-01")
    return parse_config(text, default_name="doctor", source="doctor").brand


def _run_check(check_id: str, tail: list[str]) -> CheckResult:
    try:
        ffmpeg = proc.tool_path("ffmpeg")
        result = proc.run(
            [str(ffmpeg), *tail], timeout_s=_TIMEOUT_S, check=False, capture_stderr=True
        )
    except KcutError as exc:
        return CheckResult(check_id, True, False, exc.message_es, _BUILD_FIX)
    if result.returncode == 0:
        return CheckResult(check_id, True, True, "ok", None)
    lines = proc.scrub_media_metadata(result.stderr).strip().splitlines()
    detail = (lines[-1] if lines else f"ffmpeg salió con código {result.returncode}")[:160]
    return CheckResult(check_id, True, False, detail, _BUILD_FIX)
