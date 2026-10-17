"""Doctor checks that run ffmpeg on tiny synthetic sources: HDR tone-map chain and soxr."""

from kcut import proc
from kcut.doctor.result import CheckResult
from kcut.errors import KcutError
from kcut.ff.color import HDR_TO_SDR

_TIMEOUT_S = 60.0
_HDR_SOURCE = (
    "testsrc2=s=64x64:d=0.04,"
    "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc,"
    "format=yuv420p10le"
)
_BASE = ["-hide_banner", "-nostdin", "-loglevel", "error"]
_BUILD_FIX = "usa el build full de gyan.dev (trae zscale, tonemap y soxr)"


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
