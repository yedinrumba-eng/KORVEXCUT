"""Ingest steps 2-4 for one file: probe, image size, audio extraction and peak, duration limits."""

import json
import math
from pathlib import Path

from PIL import Image

from kcut import proc
from kcut.audio.wavio import wav_duration_ms, wav_peak
from kcut.config.model import IngestSection
from kcut.console import Out
from kcut.errors import ProjectError, ToolError
from kcut.ff.args import ffprobe_args
from kcut.ingest import workfiles
from kcut.ingest.classify import DOC_EXT, IMG_EXT
from kcut.ingest.inventory_model import Clip, ImageMeta, Notice
from kcut.ingest.probe import MediaInfo, parse_ffprobe
from kcut.ingest.scan import Found
from kcut.paths import is_inside, resolve_in_project
from kcut.project import Project

FFPROBE_TIMEOUT_S = 60.0
_FLOOR_DBFS = -120.0
_MS_PER_HOUR = 3_600_000


def examine(
    project: Project, item: Found, reusable: dict[str, Clip], log: Path, notices: list[Notice]
) -> None:
    """Fill in what is known about one file. A broken file is marked, never fatal."""
    if item.ext in DOC_EXT:
        return
    try:
        if item.ext in IMG_EXT:
            item.image = _image_meta(item.path)
            return
        item.info = _probe(item.path, log)
        if item.info.video is not None:
            item.proxy_dims = workfiles.proxy_size(item.info.video)
    except (ToolError, ProjectError, OSError, ValueError, Image.DecompressionBombError) as exc:
        item.failed = True
        item.info = None
        item.image = None
        Out(json_mode=False).warn(f"{item.rel}: no se pudo leer ({first_line(exc)})")
        return
    item.flags = duration_flags(item.info.duration_ms, project.config.ingest)
    if "too_long" in item.flags or item.info.audio is None:
        return
    try:
        _audio_peak(project, item, reusable, log, notices)
        _recheck_real_length(project, item)
    except (ToolError, ProjectError, OSError) as exc:
        item.wav = None
        item.peak = None
        item.wav_failed = True
        Out(json_mode=False).warn(f"{item.rel}: falló el wav16 ({first_line(exc)})")


def _recheck_real_length(project: Project, item: Found) -> None:
    """The declared duration is not trusted: re-evaluate the limits with the real wav16 length.
    A clip that turns out `too_long` loses its wav16 (it is not processed)."""
    if item.wav is None:
        return
    real = duration_flags(wav_duration_ms(item.wav), project.config.ingest)
    item.flags = tuple(dict.fromkeys((*item.flags, *real)))
    if "too_long" in real:
        workfiles.discard(project, item.wav)
        item.wav = None
        item.peak = None


def duration_flags(duration_ms: int, cfg: IngestSection) -> tuple[str, ...]:
    """`long_duration` above `warn_duration_h`; `too_long` (the clip is not processed) above
    `max_duration_h`. A clip over the maximum carries both."""
    flags: list[str] = []
    if duration_ms > round(cfg.warn_duration_h * _MS_PER_HOUR):
        flags.append("long_duration")
    if duration_ms > round(cfg.max_duration_h * _MS_PER_HOUR):
        flags.append("too_long")
    return tuple(flags)


def dbfs(linear_peak: float) -> float:
    """Peak level in dBFS, one decimal; digital silence is reported as -120."""
    if linear_peak <= 0.0:
        return _FLOOR_DBFS
    return round(max(20.0 * math.log10(linear_peak), _FLOOR_DBFS), 1)


def first_line(exc: BaseException) -> str:
    """First line of an error message (already scrubbed when it came from a child process)."""
    message = getattr(exc, "message_es", None) or str(exc)
    return (str(message).strip().splitlines() or [""])[0][:200]


def _probe(path: Path, log: Path) -> MediaInfo:
    """Run ffprobe and keep only the whitelisted fields; the raw JSON is dropped right here."""
    result = proc.run(
        ffprobe_args(proc.tool_path("ffprobe"), path), log=log, timeout_s=FFPROBE_TIMEOUT_S
    )
    try:
        data = json.loads(result.stdout.decode("utf-8", errors="replace"))
    except (ValueError, RecursionError):
        raise ProjectError("ffprobe devolvió una respuesta que no es JSON") from None
    if not isinstance(data, dict):
        raise ProjectError("ffprobe devolvió una respuesta inesperada")
    return parse_ffprobe(data)


def _image_meta(path: Path) -> ImageMeta:
    with Image.open(path) as image:
        width, height = image.size
        alpha = "A" in image.mode or "transparency" in image.info
    return ImageMeta(w=width, h=height, has_alpha=alpha)


def _audio_peak(
    project: Project, item: Found, reusable: dict[str, Clip], log: Path, notices: list[Notice]
) -> None:
    """Get the wav16 (reusing a fresh one from the previous run) and measure its peak."""
    known = reusable.get(item.hash)
    if known is not None and known.work is not None and known.work.wav16 is not None:
        old = resolve_in_project(project.root, known.work.wav16)
        in_wav16 = is_inside(project.layout.wav16.resolve(), old)  # never trust the old path
        state = workfiles.sidecar_state(old, item.hash, workfiles.wav_params(16000))
        if in_wav16 and state == "fresh":
            item.wav = old
        elif in_wav16 and state == "corrupt":
            detail = f"{old.name}: el sidecar estaba dañado y se reconstruye"
            notices.append(Notice("cache_rebuilt", detail))
    if item.wav is None:
        duration = item.info.duration_ms if item.info is not None else 0
        item.wav = workfiles.stage_wav16(project, item.rel, item.hash, duration, log, notices)
    item.peak = dbfs(wav_peak(item.wav))
