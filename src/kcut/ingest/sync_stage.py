"""Ingest step 6: sync every voiced clip against the master, and the per-clip warning codes."""

import math
from dataclasses import dataclass
from pathlib import Path

from kcut.console import Progress
from kcut.errors import ProjectError
from kcut.ingest.inventory import (
    Clip,
    Inventory,
    SyncInfo,
    SyncMember,
    SyncRejected,
)
from kcut.ingest.sync import SyncResult, sync_pair
from kcut.paths import resolve_in_project
from kcut.project import Project


@dataclass
class _Outcome:
    members: list[SyncMember]
    rejected: list[SyncRejected]


def sync_clips(
    project: Project,
    clips: list[Clip],
    previous: Inventory | None,
    resync: bool,
    progress: Progress | None,
) -> SyncInfo:
    """Sync the non-silent `a` and `s` clips against the master (`sync.master` or lowest `a`)."""
    cfg = project.config.sync
    group = [c for c in clips if _is_voiced(c)]
    master = _pick_master(group, cfg.master)
    if master is None:
        return SyncInfo()
    others = [c for c in group if c.id != master.id]
    steps_before = progress.total if progress else 0
    if progress is not None:
        progress.total = steps_before + len(others)
    outcome = _Outcome([], [])
    for done, member in enumerate(others, start=1):
        manual = cfg.manual.get(member.id)
        old = (
            None
            if manual is not None or resync
            else _reusable(previous, master, member, cfg.min_refine_corr)
        )
        if manual is not None:
            outcome.members.append(SyncMember(member.id, manual, 0.0, 0.0, None, None, 0, "manual"))
        elif isinstance(old, SyncMember):
            outcome.members.append(old)
        elif isinstance(old, SyncRejected):
            outcome.rejected.append(old)
        else:
            result = sync_pair(_wav(project, master), _wav(project, member), cfg)
            _record(outcome, member.id, result)
        if progress is not None:
            progress.update(steps_before + done)
    return SyncInfo(master.id, tuple(outcome.members), tuple(outcome.rejected))


def clip_warnings(
    clip: Clip, fps: int, sync: SyncInfo, max_drift_ms: int, flags: frozenset[str]
) -> tuple[str, ...]:
    """Warning codes of a clip, in the order of the spec. `flags` carries what the file
    inspection found: `probe_failed`, `wav16_failed`, `long_duration`, `too_long`."""
    found: list[str] = []
    video, audio = clip.video, clip.audio
    if video is not None:
        found += ["vfr"] if video.vfr else []
        found += ["hdr"] if video.hdr is not None else []
        found += ["dolby_vision"] if video.dolby_vision else []
        found += ["dv_profile_unsupported"] if video.dv_profile == 5 else []
        found += ["rotation"] if video.rotation != 0 else []
    if audio is not None:
        found += ["multi_audio"] if audio.streams > 1 else []
        found += ["silent_audio"] if audio.silent else []
    if video is not None and audio is not None:
        found += ["av_start_offset"] if abs(video.start_ms - audio.start_ms) > 1000 // fps else []
    mine = [r for r in sync.rejected if r.id == clip.id]
    found += ["sync_rejected"] if mine else []
    found += ["sync_weak_refine"] if any(r.refine_corr is not None for r in mine) else []
    drifting = any(
        m.id == clip.id and m.drift_ms is not None and m.drift_ms > max_drift_ms
        for m in sync.members
    )
    found += ["drift"] if drifting else []
    probe_failed = "probe_failed" in flags
    found += ["probe_failed"] if probe_failed else []
    found += ["unknown_type"] if clip.clip_class == "desconocido" and not probe_failed else []
    found += [code for code in ("wav16_failed", "long_duration", "too_long") if code in flags]
    return tuple(found)


def _is_voiced(clip: Clip) -> bool:
    return (
        clip.clip_class in ("video_voz", "audio")
        and clip.audio is not None
        and not clip.audio.silent
        and clip.work is not None
        and clip.work.wav16 is not None
    )


def _pick_master(group: list[Clip], configured: str) -> Clip | None:
    if configured:
        for clip in group:
            if clip.id == configured:
                return clip
        raise ProjectError(
            f'sync.master "{configured}" no es un clip con voz del inventario '
            "(revisa kcut.toml o los ids de kcut ingest)"
        )
    cameras = [c for c in group if c.id.startswith("a")]
    return min(cameras, key=lambda c: int(c.id[1:])) if cameras else None


def _wav(project: Project, clip: Clip) -> Path:
    if clip.work is None or clip.work.wav16 is None:
        raise ProjectError(f"{clip.id} no tiene wav16")
    return resolve_in_project(project.root, clip.work.wav16)


def _reusable(
    previous: Inventory | None, master: Clip, member: Clip, min_refine_corr: float
) -> SyncMember | SyncRejected | None:
    """Previous result for this pair, if neither file changed and it was not a manual entry.

    An accepted result is reused only if it recorded a refine correlation that still clears
    `min_refine_corr`: older inventories (no `refine_corr`) are measured again.
    """
    if previous is None or previous.sync.master != master.id:
        return None
    for clip in (master, member):
        before = previous.by_id(clip.id)
        if before is None or before.qhash != clip.qhash:
            return None
    for entry in previous.sync.members:
        if entry.id == member.id and entry.method != "manual":
            kept = entry.refine_corr is not None and entry.refine_corr >= min_refine_corr
            return entry if kept else None
    for rejected in previous.sync.rejected:
        if rejected.id == member.id:
            return rejected
    return None


def _record(outcome: _Outcome, clip_id: str, result: SyncResult) -> None:
    ratio = _finite(result.ratio)
    if result.accepted:
        outcome.members.append(
            SyncMember(
                clip_id,
                result.offset_ms,
                round(result.score, 4),
                round(result.second, 4),
                ratio,
                result.drift_ms,
                result.drift_windows,
                "envelope+raw",
                None if result.refine_corr is None else round(result.refine_corr, 4),
            )
        )
    else:
        reason = result.reason or "rechazado"
        corr = None if result.refine_corr is None else round(result.refine_corr, 4)
        outcome.rejected.append(SyncRejected(clip_id, round(result.score, 4), ratio, reason, corr))


def _finite(value: float) -> float | None:
    """JSON has no infinity: an unbounded ratio (no second peak at all) is stored as null."""
    return round(value, 2) if math.isfinite(value) else None
