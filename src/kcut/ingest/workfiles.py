"""Work files under `.kcut/` (wav16, wav48, proxies). Each has a sidecar that proves it is fresh.

Nothing read from the cache is trusted, and every write, move or delete is checked first with
`_assert_in_cache`: kcut never touches a path that resolves outside `.kcut/` (spec 0.9).
"""

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from kcut import proc
from kcut.errors import ProjectError, ToolError
from kcut.ff.args import proxy_args, wav_args
from kcut.ff.color import CHAIN_VERSION, video_chain
from kcut.ingest.cache_guard import assert_in_cache
from kcut.ingest.inventory import Clip, Notice
from kcut.ingest.probe import VideoInfo
from kcut.jsonio import MAX_SIDECAR_BYTES, read_json, refuse_directory, write_json_atomic
from kcut.paths import resolve_in_project
from kcut.project import Project
from kcut.timebase import rdiv

PROXY_LONG_SIDE = 960
PROXY_PARAMS_VERSION = 2
_WAV_VERSION = 1
_PROXY_CRF = 23
_TIMEOUT_PER_MEDIA_SECOND = 10
_TIMEOUT_BASE_S = 60.0

SidecarState = Literal["fresh", "stale", "missing", "corrupt"]

# the guard lives in `cache_guard.py` (001.26, 300-line rule); this is the name the code uses
_assert_in_cache = assert_in_cache


def max_job_seconds(project: Project) -> float:
    """Length cap of an ffmpeg job (`-t`): `max_duration_h` + 60 s; declared durations lie."""
    return project.config.ingest.max_duration_h * 3600 + 60


def sidecar_path(path: Path) -> Path:
    """`<file>.json` next to a work file."""
    return path.with_name(path.name + ".json")


def sidecar_state(path: Path, qhash: str, params: dict[str, Any]) -> SidecarState:
    """Is the work file `path` usable? `corrupt`: the sidecar exists but cannot be read."""
    if not path.is_file():
        return "missing"
    sidecar = sidecar_path(path)
    if not sidecar.is_file():
        return "missing"
    try:
        data = read_json(sidecar, MAX_SIDECAR_BYTES)
    except ProjectError:
        return "corrupt"
    return "fresh" if data == {"qhash": qhash, "params": params} else "stale"


def is_fresh(path: Path, qhash: str, params: dict[str, Any]) -> bool:
    """True when `path` exists and its sidecar holds exactly this `qhash` and `params`."""
    return sidecar_state(path, qhash, params) == "fresh"


def job_timeout_s(duration_ms: int) -> float:
    """Time allowed to one ffmpeg job: 10 x the media duration in seconds, plus 60 s."""
    return _TIMEOUT_PER_MEDIA_SECOND * duration_ms / 1000 + _TIMEOUT_BASE_S


def work_name(clip_id: str, slug: str, ext: str) -> str:
    """`a1_crudo-1.wav`: short, ASCII, no spaces (spec 0.10.8)."""
    return f"{clip_id}_{slug}.{ext}"


def wav_params(sr: int) -> dict[str, Any]:
    return {"sr": sr, "channels": 1, "format": "pcm_s16le", "resampler": "soxr", "v": _WAV_VERSION}


def proxy_size(video: VideoInfo) -> tuple[int, int]:
    """Long side 960, short side even, from the displayed (already rotated) size."""
    long_side, short_side = sorted((video.display_w, video.display_h), reverse=True)
    if short_side <= 0:
        raise ProjectError("el video no declara su tamaño")
    short_scaled = max(2, 2 * rdiv(short_side * PROXY_LONG_SIDE, 2 * long_side))
    if video.display_w >= video.display_h:
        return PROXY_LONG_SIDE, short_scaled
    return short_scaled, PROXY_LONG_SIDE


def proxy_params(video: VideoInfo, fps: int) -> tuple[dict[str, Any], str, tuple[int, int]]:
    """Freshness parameters, ffmpeg filter chain and size of the proxy of `video`."""
    size = proxy_size(video)
    chain = video_chain(video, size[0], size[1], fps)
    params = {
        "chain": chain,
        "fps": fps,
        "crf": _PROXY_CRF,
        "chain_version": CHAIN_VERSION,
        "params_version": PROXY_PARAMS_VERSION,
    }
    return params, chain, size


def stage_wav16(
    project: Project,
    rel: str,
    qhash: str,
    duration_ms: int,
    log: Path | None,
    notices: list[Notice] | None = None,
) -> Path:
    """wav16 under a content-addressed name, used before the clip has an id."""
    stage = project.layout.wav16 / f"stage-{qhash.removeprefix('sha256:')[:16]}.wav"
    src = resolve_in_project(project.root, rel)
    _build_wav(project, src, stage, qhash, 16000, duration_ms, log, notices)
    return stage


def adopt(project: Project, src: Path, dst: Path, *, copy: bool = False) -> None:
    """Give a work file (and its sidecar) its final name: move it, or copy it when another
    clip with identical content uses the same source. Both ends must lie inside `.kcut/`."""
    pairs = [(src, dst)]
    if sidecar_path(src).is_file():
        pairs.append((sidecar_path(src), sidecar_path(dst)))
    for source, target in pairs:  # check everything before touching the disk
        _assert_in_cache(project, source)
        _assert_in_cache(project, target)
    if src == dst:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    for source, target in pairs:
        if copy:
            _copy(source, target)
        else:
            _replace(source, target)


def discard(project: Project, path: Path) -> None:
    """Delete a work file and its sidecar if they exist (only inside `.kcut/`)."""
    for target in (path, sidecar_path(path)):
        _assert_in_cache(project, target)
    path.unlink(missing_ok=True)
    sidecar_path(path).unlink(missing_ok=True)


def ensure_wav16(
    project: Project, clip: Clip, log: Path | None = None, notices: list[Notice] | None = None
) -> Path:
    """Mono 16 kHz wav of the clip's first audio stream (analysis and sync)."""
    return _ensure_wav(project, clip, 16000, project.layout.wav16, log, notices)


def ensure_wav48(
    project: Project, clip: Clip, log: Path | None = None, notices: list[Notice] | None = None
) -> Path:
    """Mono 48 kHz wav of the clip's first audio stream (render, from S1.5)."""
    return _ensure_wav(project, clip, 48000, project.layout.wav48, log, notices)


def ensure_proxy(
    project: Project, clip: Clip, log: Path | None = None, notices: list[Notice] | None = None
) -> Path:
    """Small bt709 proxy of the clip's video, rebuilt only when stale."""
    if clip.video is None:
        raise ProjectError(f"{clip.id} no tiene video")
    fps = project.config.output.fps
    params, chain, _ = proxy_params(clip.video, fps)
    dst = project.layout.proxy / work_name(clip.id, clip.slug, "mp4")
    if _usable(dst, clip.qhash, params, notices):
        return dst
    src = resolve_in_project(project.root, clip.file)
    ffmpeg = proc.tool_path("ffmpeg")
    limit = max_job_seconds(project)
    _build(
        project,
        lambda out: proxy_args(ffmpeg, src, out, chain, fps, limit),
        dst,
        (clip.qhash, params, job_timeout_s(clip.duration_ms or 0)),
        log,
    )
    return dst


def _ensure_wav(
    project: Project,
    clip: Clip,
    sr: Literal[16000, 48000],
    folder: Path,
    log: Path | None,
    notices: list[Notice] | None,
) -> Path:
    if clip.audio is None:
        raise ProjectError(f"{clip.id} no tiene audio")
    dst = folder / work_name(clip.id, clip.slug, "wav")
    src = resolve_in_project(project.root, clip.file)
    _build_wav(project, src, dst, clip.qhash, sr, clip.duration_ms or 0, log, notices)
    return dst


def _build_wav(
    project: Project,
    src: Path,
    dst: Path,
    qhash: str,
    sr: Literal[16000, 48000],
    duration_ms: int,
    log: Path | None,
    notices: list[Notice] | None,
) -> None:
    params = wav_params(sr)
    if _usable(dst, qhash, params, notices):
        return
    ffmpeg = proc.tool_path("ffmpeg")
    limit = max_job_seconds(project)
    _build(
        project,
        lambda out: wav_args(ffmpeg, src, out, sr, limit),
        dst,
        (qhash, params, job_timeout_s(duration_ms)),
        log,
    )


def _usable(dst: Path, qhash: str, params: dict[str, Any], notices: list[Notice] | None) -> bool:
    """Fresh work file? A corrupt sidecar is not an error: it is rebuilt, with a notice."""
    state = sidecar_state(dst, qhash, params)
    if state == "corrupt" and notices is not None:
        detail = f"{dst.name}: el sidecar estaba dañado y se reconstruye"
        notices.append(Notice("cache_rebuilt", detail))
    return state == "fresh"


def _build(
    project: Project,
    make_args: Callable[[Path], list[str]],
    dst: Path,
    job: tuple[str, dict[str, Any], float],
    log: Path | None,
) -> None:
    """Run ffmpeg into `<name>.<pid>.partial.<ext>`, then replace `dst` and write its sidecar.

    The partial has the pid, so two renders that make the same file do not write the same one and
    each deletes only its own. If `dst` is fresh when the partial is done (the other one came
    first) it is used as it is, and the sidecar is the other's (001.26, point 3)."""
    qhash, params, timeout_s = job
    partial = dst.with_name(f"{dst.stem}.{os.getpid()}.partial{dst.suffix}")
    for target in (dst, partial, sidecar_path(dst)):
        _assert_in_cache(project, target)  # before touching the disk
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        partial.unlink(missing_ok=True)
        proc.run(make_args(partial), log=log, timeout_s=timeout_s)
        if not partial.is_file():
            raise ToolError(f"ffmpeg no produjo {dst.name}")
        if not _land(partial, dst, qhash, params):
            return
    finally:
        partial.unlink(missing_ok=True)
    write_json_atomic(sidecar_path(dst), {"qhash": qhash, "params": params})


def _land(partial: Path, dst: Path, qhash: str, params: dict[str, Any]) -> bool:
    """Put `partial` over `dst`: True if it was moved, False if `dst` was already fresh, before
    or because the replace was refused (a reader has it open: on Windows ffmpeg and `wave` do not
    share the delete), so the one that is there is the one to use."""
    if is_fresh(dst, qhash, params):
        return False
    refuse_directory(dst)
    try:
        os.replace(partial, dst)
    except PermissionError:
        if is_fresh(dst, qhash, params):
            return False
        raise ProjectError(f"cierra el archivo {dst} en el reproductor y repite") from None
    return True


def _copy(src: Path, dst: Path) -> None:
    if src.resolve() == dst.resolve():
        return  # same file: deleting the destination first would delete the source
    refuse_directory(dst)
    try:
        dst.unlink(missing_ok=True)  # break any hard link before writing
        shutil.copy2(src, dst)
    except PermissionError:
        raise ProjectError(f"cierra el archivo {dst} en el reproductor y repite") from None


def _replace(src: Path, dst: Path) -> None:
    refuse_directory(dst)
    try:
        os.replace(src, dst)
    except PermissionError:
        raise ProjectError(f"cierra el archivo {dst} en el reproductor y repite") from None
