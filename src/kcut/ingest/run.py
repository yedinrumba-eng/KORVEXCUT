"""`kcut ingest`: scan `crudo/`, probe, extract audio, classify, build proxies, sync cameras."""

from collections import Counter
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from kcut.console import Out, Progress
from kcut.errors import ProjectError, ToolError
from kcut.ingest import workfiles
from kcut.ingest.classify import NewFile, assign_ids, classify
from kcut.ingest.examine import examine, first_line
from kcut.ingest.inventory import (
    Clip,
    ClipAudio,
    Inventory,
    InventoryInvalid,
    Notice,
    WorkFiles,
    field_text,
    load_inventory,
    save_inventory,
)
from kcut.ingest.naming import slugify
from kcut.ingest.scan import Found, scan_crudo
from kcut.ingest.sync_stage import clip_warnings, sync_clips
from kcut.logfile import append_log
from kcut.paths import to_rel
from kcut.project import Project
from kcut.timebase import ms_to_f_floor

SILENT_DBFS = -60.0
_INVALID = "se ignora el inventario anterior: no pasó la validación"


def run_ingest(
    project: Project,
    *,
    make_proxies: bool,
    resync: bool,
    progress: Progress | None,
    log: Path | None = None,
    notices: list[Notice] | None = None,
) -> Inventory:
    """Build `.kcut/inventory.json`. A failed proxy is recorded as `proxy: null` and the command
    ends with ToolError (exit 4) after the inventory is saved.

    `log` is the run log chosen by the CLI. `None` means the CLI decided this run leaves no log
    (001.7): nothing is written to `.kcut/logs/`, and no other name is invented. Run-level
    warnings are appended to `notices` and also printed to stderr.
    """
    notes = notices if notices is not None else []
    shown = len(notes)
    try:
        return _run(project, make_proxies, resync, progress, log, notes)
    finally:
        for notice in notes[shown:]:
            Out(json_mode=False).warn(f"{notice.code}: {notice.detail}")


def _run(
    project: Project,
    make_proxies: bool,
    resync: bool,
    progress: Progress | None,
    log: Path | None,
    notes: list[Notice],
) -> Inventory:
    layout, fps = project.layout, project.config.output.fps
    previous = _previous(project, notes, log)
    reusable = {c.qhash: c for c in previous.clips} if previous else {}
    found = scan_crudo(project, notes)
    _set_total(progress, len(found))
    for done, item in enumerate(found, start=1):
        examine(project, item, reusable, log, notes)
        item.clip_class = "desconocido" if item.failed else classify(item.ext, item.info, item.peak)
        _tick(progress, done)
    ids, id_high = assign_ids([NewFile(f.rel, f.hash, f.clip_class) for f in found], previous)
    shared = {p for p, n in Counter(f.wav for f in found if f.wav is not None).items() if n > 1}
    clips = [_make_clip(project, item, ids[item.rel], shared) for item in found]
    for path in shared:
        if path.name.startswith("stage-"):
            workfiles.discard(project, path)
    skip = {ids[f.rel] for f in found if "too_long" in f.flags}
    clips, failures = _proxies(project, clips, skip, make_proxies, log, progress, notes)
    sync = sync_clips(project, clips, previous, resync, progress)
    flags = {ids[f.rel]: _flags(f) for f in found}
    final = tuple(
        replace(
            c, warnings=clip_warnings(c, fps, sync, project.config.sync.max_drift_ms, flags[c.id])
        )
        for c in clips
    )
    inventory = Inventory(
        generated=datetime.now().isoformat(timespec="seconds"),
        fps=fps,
        clips=final,
        sync=sync,
        id_high=id_high,
    )
    workfiles._assert_in_cache(project, layout.inventory)
    save_inventory(layout.inventory, inventory)
    if failures:
        raise ToolError(
            f"fallaron {len(failures)} proxies ({', '.join(failures)}); el inventario quedó "
            "guardado con proxy: null. Revisa el log de .kcut/logs/ y repite kcut ingest"
        )
    return inventory


def _flags(item: Found) -> frozenset[str]:
    flags = set(item.flags)
    if item.failed:
        flags.add("probe_failed")
    if item.wav_failed:
        flags.add("wav16_failed")
    return frozenset(flags)


def _previous(project: Project, notes: list[Notice], log: Path | None) -> Inventory | None:
    """The previous inventory, or None. An unreadable or untrustworthy one counts as absent.

    The warning says a fixed text plus the path of the failing field, cut to 120 characters
    (001.10, point 1): the loader's message quotes keys, ids and values of a file anyone could
    have planted, and Claude reads this output. The whole message goes to the log, and only there.
    """
    if not project.layout.inventory.is_file():
        return None
    try:
        return load_inventory(project.layout.inventory, project.root)
    except ProjectError as exc:
        field = exc.field if isinstance(exc, InventoryInvalid) else ""
        notes.append(Notice("inventory_invalid", _invalid_text(field)))
        if log is not None:
            append_log(log, f"[inventory_invalid] {exc.message_es}\n")
        return None


def _invalid_text(field: str) -> str:
    """`se ignora el inventario anterior: no pasó la validación (<field cut to 120>)`."""
    return f"{_INVALID} ({field_text(field)})" if field else _INVALID


def _make_clip(project: Project, item: Found, clip_id: str, shared: set[Path]) -> Clip:
    fps = project.config.output.fps
    slug = slugify(item.path.stem)
    base = Clip(
        id=clip_id,
        file=item.rel,
        slug=slug,
        clip_class=item.clip_class,
        qhash=item.hash,
        size_bytes=item.size,
        image=item.image,
    )
    info = item.info
    if info is None or (info.video is None and info.audio is None):
        return base
    wav_rel: str | None = None
    audio: ClipAudio | None = None
    if info.audio is not None and item.wav is not None and item.peak is not None:
        final = project.layout.wav16 / workfiles.work_name(clip_id, slug, "wav")
        workfiles.adopt(project, item.wav, final, copy=item.wav in shared)
        wav_rel = to_rel(project.root, final)
        audio = ClipAudio(
            codec=info.audio.codec,
            sample_rate=info.audio.sample_rate,
            channels=info.audio.channels,
            start_ms=info.audio.start_ms,
            streams=info.audio.streams,
            peak_dbfs=item.peak,
            silent=item.peak <= SILENT_DBFS,
        )
    size = item.proxy_dims if item.proxy_dims is not None else (None, None)
    return replace(
        base,
        duration_ms=info.duration_ms,
        frames=ms_to_f_floor(info.duration_ms, fps),
        video=info.video,
        audio=audio,
        work=WorkFiles(proxy=None, wav16=wav_rel, proxy_w=size[0], proxy_h=size[1]),
    )


def _proxies(
    project: Project,
    clips: list[Clip],
    skip: set[str],
    make_proxies: bool,
    log: Path | None,
    progress: Progress | None,
    notes: list[Notice],
) -> tuple[list[Clip], list[str]]:
    """Build (or find) every proxy. Returns the clips with `work.proxy` set and the failures."""
    fps = project.config.output.fps
    videos = [c for c in clips if c.video is not None and c.work is not None and c.id not in skip]
    steps_before = progress.total if progress else 0
    _set_total(progress, steps_before + len(videos))
    failures: list[str] = []
    result: dict[str, Clip] = {}
    for done, clip in enumerate(videos, start=1):
        assert clip.video is not None and clip.work is not None  # narrowed by `videos`
        proxy: Path | None = None
        try:
            if make_proxies:
                proxy = workfiles.ensure_proxy(project, clip, log, notes)
            else:
                params, _, _ = workfiles.proxy_params(clip.video, fps)
                existing = project.layout.proxy / workfiles.work_name(clip.id, clip.slug, "mp4")
                proxy = existing if workfiles.is_fresh(existing, clip.qhash, params) else None
        except ToolError as exc:
            failures.append(clip.id)
            Out(json_mode=False).warn(f"{clip.id}: falló el proxy ({first_line(exc)})")
        rel = to_rel(project.root, proxy) if proxy is not None else None
        result[clip.id] = replace(clip, work=replace(clip.work, proxy=rel))
        _tick(progress, steps_before + done)
    return [result.get(c.id, c) for c in clips], failures


def _set_total(progress: Progress | None, total: int) -> None:
    if progress is not None:
        progress.total = total


def _tick(progress: Progress | None, done: int) -> None:
    if progress is not None:
        progress.update(done)
