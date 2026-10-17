"""Inventory as a JSON-ready dict (key order of the spec example; absent values omitted)."""

from dataclasses import fields
from typing import Any

from kcut.ingest.inventory_model import Clip, Inventory, SyncMember
from kcut.ingest.probe import VideoInfo


def video_keys() -> list[str]:
    """Field names of `VideoInfo`, in order."""
    return [f.name for f in fields(VideoInfo)]


def inventory_to_json(inv: Inventory) -> dict[str, Any]:
    """The inventory as a dict. `id_high` always covers the ids present, so what is written
    can be read back."""
    high = dict(inv.id_high)
    for clip in inv.clips:
        high[clip.id[0]] = max(high.get(clip.id[0], 0), int(clip.id[1:]))
    return {
        "schema": inv.schema,
        "generated": inv.generated,
        "fps": inv.fps,
        "id_high": dict(sorted(high.items())),
        "clips": [_clip_json(c) for c in inv.clips],
        "sync": {
            "master": inv.sync.master,
            "members": [_member_json(m) for m in inv.sync.members],
            "rejected": [
                {
                    "id": r.id,
                    "score": r.score,
                    "ratio": r.ratio,
                    "refine_corr": r.refine_corr,
                    "reason": r.reason,
                }
                for r in inv.sync.rejected
            ],
        },
    }


def _clip_json(c: Clip) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": c.id,
        "file": c.file,
        "slug": c.slug,
        "class": c.clip_class,
        "qhash": c.qhash,
        "size_bytes": c.size_bytes,
    }
    if c.duration_ms is not None:
        out["duration_ms"] = c.duration_ms
    if c.frames is not None:
        out["frames"] = c.frames
    if c.video is not None:
        out["video"] = {key: getattr(c.video, key) for key in video_keys()}
    if c.audio is not None:
        out["audio"] = {
            "codec": c.audio.codec,
            "sample_rate": c.audio.sample_rate,
            "channels": c.audio.channels,
            "start_ms": c.audio.start_ms,
            "streams": c.audio.streams,
            "peak_dbfs": c.audio.peak_dbfs,
            "silent": c.audio.silent,
        }
    if c.image is not None:
        out["image"] = {"w": c.image.w, "h": c.image.h, "has_alpha": c.image.has_alpha}
    if c.work is not None:
        out["work"] = {
            "proxy": c.work.proxy,
            "wav16": c.work.wav16,
            "proxy_w": c.work.proxy_w,
            "proxy_h": c.work.proxy_h,
        }
    out["warnings"] = list(c.warnings)
    return out


def _member_json(m: SyncMember) -> dict[str, Any]:
    return {
        "id": m.id,
        "offset_ms": m.offset_ms,
        "score": m.score,
        "second": m.second,
        "ratio": m.ratio,
        "refine_corr": m.refine_corr,
        "drift_ms": m.drift_ms,
        "drift_windows": m.drift_windows,
        "method": m.method,
    }
