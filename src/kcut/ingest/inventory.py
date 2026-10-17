"""`.kcut/inventory.json`: what is in `crudo/`, how it was classified, its work files and sync.

The dataclasses live in `inventory_model.py` (split for the 300-line rule) and are re-exported here.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast, get_args

from kcut.config.names import has_forbidden_chars
from kcut.errors import ProjectError
from kcut.ingest.classify import ClipClass
from kcut.ingest.inventory_check import check_clip, check_ids
from kcut.ingest.inventory_json import inventory_to_json, video_keys
from kcut.ingest.inventory_model import (
    SCHEMA,
    Clip,
    ClipAudio,
    ImageMeta,
    Inventory,
    Notice,
    SyncInfo,
    SyncMember,
    SyncRejected,
    WorkFiles,
)
from kcut.ingest.probe import VideoInfo
from kcut.ingest.sync_reasons import MAX_LAG_MS, MAX_TEXT_LEN
from kcut.jsonio import read_json, write_json_atomic
from kcut.schema_util import (
    SchemaError,
    join_path,
    obj,
    one_of,
    only_keys,
    opt_float,
    opt_int,
    opt_list,
    opt_str,
    req_bool,
    req_float,
    req_int,
    req_list,
    req_str,
)

_VIDEO_KEYS = video_keys()


def _text(d: dict[str, Any], key: str, path: str) -> str:
    """Free text of the sync results: short, and with no control, format or line-separator
    characters (it may be printed to a terminal)."""
    value = req_str(d, key, path, max_len=MAX_TEXT_LEN)
    if has_forbidden_chars(value):
        raise SchemaError(
            join_path(path, key), "no puede llevar caracteres de control ni de formato"
        )
    return value


def _obj(v: object, path: str) -> dict[str, Any]:
    """A JSON object where `null` means "absent" (the file writes `null` for missing values)."""
    return {k: item for k, item in obj(v, path).items() if item is not None}


def load_inventory(path: Path, root: Path | None = None) -> Inventory:
    """Read and validate an inventory file; the cache is never trusted.

    `root` is the project root (default: two levels above `.kcut/inventory.json`). Any bad id,
    slug or path makes the whole file invalid (ProjectError).
    """
    base = root if root is not None else path.resolve().parent.parent
    try:
        return _inventory(read_json(path), base)
    except SchemaError as exc:
        raise ProjectError(f"{path.name}: {exc.message_es}") from None


def save_inventory(path: Path, inv: Inventory) -> None:
    write_json_atomic(path, inventory_to_json(inv))


def _inventory(data: object, root: Path) -> Inventory:
    d = _obj(data, "")
    only_keys(d, {"schema", "generated", "fps", "id_high", "clips", "sync"}, "")
    schema = req_str(d, "schema", "")
    if schema != SCHEMA:
        raise SchemaError("schema", f"se esperaba {SCHEMA} (vino {schema!r})")
    clips = tuple(
        _clip(_obj(item, join_path("clips", i))) for i, item in enumerate(req_list(d, "clips", ""))
    )
    for clip in clips:
        check_clip(clip, root)
    raw_high = _obj(d["id_high"], "id_high") if "id_high" in d else None
    high = None if raw_high is None else {k: req_int(raw_high, k, "id_high") for k in raw_high}
    return Inventory(
        generated=req_str(d, "generated", ""),
        fps=req_int(d, "fps", "", 1, 240),
        clips=clips,
        sync=_sync(_obj(d.get("sync", {}), "sync")),
        id_high=check_ids(clips, high),
    )


def _clip(d: dict[str, Any]) -> Clip:
    here = f"clips[{d.get('id', '?')}]"
    allowed = {"id", "file", "slug", "class", "qhash", "size_bytes", "duration_ms", "frames"}
    only_keys(d, allowed | {"video", "audio", "image", "work", "warnings"}, here)
    clip_class = one_of(req_str(d, "class", here), get_args(ClipClass), join_path(here, "class"))
    return Clip(
        id=req_str(d, "id", here, min_len=2),
        file=req_str(d, "file", here, min_len=1),
        slug=req_str(d, "slug", here, min_len=1),
        clip_class=cast(ClipClass, clip_class),
        qhash=req_str(d, "qhash", here, min_len=8),
        size_bytes=req_int(d, "size_bytes", here, 0),
        duration_ms=opt_int(d, "duration_ms", here, None, 0),
        frames=opt_int(d, "frames", here, None, 0),
        video=_sub(d, "video", here, _video),
        audio=_sub(d, "audio", here, _audio),
        image=_sub(d, "image", here, _image),
        work=_sub(d, "work", here, _work),
        warnings=tuple(_warnings(d, here)),
    )


def _sub[R](
    d: dict[str, Any], key: str, here: str, parse: Callable[[dict[str, Any], str], R]
) -> R | None:
    """Parse the optional object `key` of a clip with `parse(obj, path)`."""
    if key not in d:
        return None
    where = join_path(here, key)
    return parse(_obj(d[key], where), where)


def _video(d: dict[str, Any], path: str) -> VideoInfo:
    only_keys(d, set(_VIDEO_KEYS), path)
    return VideoInfo(
        codec=req_str(d, "codec", path),
        w=req_int(d, "w", path, 0),
        h=req_int(d, "h", path, 0),
        display_w=req_int(d, "display_w", path, 0),
        display_h=req_int(d, "display_h", path, 0),
        rotation=req_int(d, "rotation", path),
        fps_r=req_str(d, "fps_r", path),
        fps_avg=req_str(d, "fps_avg", path),
        vfr=req_bool(d, "vfr", path),
        pix_fmt=req_str(d, "pix_fmt", path),
        bit_depth=req_int(d, "bit_depth", path, 1, 32),
        color_transfer=opt_str(d, "color_transfer", path, None),
        color_primaries=opt_str(d, "color_primaries", path, None),
        color_space=opt_str(d, "color_space", path, None),
        color_range=opt_str(d, "color_range", path, None),
        hdr=opt_str(d, "hdr", path, None),
        dolby_vision=req_bool(d, "dolby_vision", path),
        dv_profile=opt_int(d, "dv_profile", path, None),
        start_ms=req_int(d, "start_ms", path),
    )


def _audio(d: dict[str, Any], path: str) -> ClipAudio:
    keys = {"codec", "sample_rate", "channels", "start_ms", "streams", "peak_dbfs", "silent"}
    only_keys(d, keys, path)
    return ClipAudio(
        codec=req_str(d, "codec", path),
        sample_rate=req_int(d, "sample_rate", path, 0),
        channels=req_int(d, "channels", path, 0),
        start_ms=req_int(d, "start_ms", path),
        streams=req_int(d, "streams", path, 1),
        peak_dbfs=req_float(d, "peak_dbfs", path),
        silent=req_bool(d, "silent", path),
    )


def _image(d: dict[str, Any], path: str) -> ImageMeta:
    only_keys(d, {"w", "h", "has_alpha"}, path)
    return ImageMeta(
        w=req_int(d, "w", path, 1),
        h=req_int(d, "h", path, 1),
        has_alpha=req_bool(d, "has_alpha", path),
    )


def _work(d: dict[str, Any], path: str) -> WorkFiles:
    only_keys(d, {"proxy", "wav16", "proxy_w", "proxy_h"}, path)
    return WorkFiles(
        proxy=opt_str(d, "proxy", path, None),
        wav16=opt_str(d, "wav16", path, None),
        proxy_w=opt_int(d, "proxy_w", path, None, 1),
        proxy_h=opt_int(d, "proxy_h", path, None, 1),
    )


def _warnings(d: dict[str, Any], here: str) -> list[str]:
    items = opt_list(d, "warnings", here, [])
    for i, item in enumerate(items):
        if not isinstance(item, str):
            raise SchemaError(join_path(join_path(here, "warnings"), i), "debe ser texto")
    return cast(list[str], items)


def _sync(d: dict[str, Any]) -> SyncInfo:
    only_keys(d, {"master", "members", "rejected"}, "sync")
    members = tuple(
        _member(_obj(m, join_path("sync.members", i)), join_path("sync.members", i))
        for i, m in enumerate(opt_list(d, "members", "sync", []))
    )
    rejected = tuple(
        _rejected(_obj(r, join_path("sync.rejected", i)), join_path("sync.rejected", i))
        for i, r in enumerate(opt_list(d, "rejected", "sync", []))
    )
    return SyncInfo(master=opt_str(d, "master", "sync", None), members=members, rejected=rejected)


def _member(d: dict[str, Any], path: str) -> SyncMember:
    keys = {"id", "offset_ms", "score", "second", "ratio", "refine_corr", "drift_ms"}
    keys |= {"drift_windows", "method", "sync_version"}
    only_keys(d, keys, path)
    return SyncMember(
        id=req_str(d, "id", path),
        offset_ms=req_int(d, "offset_ms", path),
        score=req_float(d, "score", path),
        second=req_float(d, "second", path),
        ratio=opt_float(d, "ratio", path, None),
        drift_ms=opt_int(d, "drift_ms", path, None),
        drift_windows=req_int(d, "drift_windows", path, 0),
        method=_text(d, "method", path),
        refine_corr=opt_float(d, "refine_corr", path, None),
        sync_version=opt_int(d, "sync_version", path, 1, 1, 1000),
    )


def _rejected(d: dict[str, Any], path: str) -> SyncRejected:
    keys = {"id", "score", "ratio", "refine_corr", "reason", "lag_a_ms", "lag_b_ms", "sync_version"}
    only_keys(d, keys, path)
    return SyncRejected(
        id=req_str(d, "id", path),
        score=req_float(d, "score", path),
        ratio=opt_float(d, "ratio", path, None),
        reason=_text(d, "reason", path),
        refine_corr=opt_float(d, "refine_corr", path, None),
        lag_a_ms=opt_int(d, "lag_a_ms", path, None, -MAX_LAG_MS, MAX_LAG_MS),
        lag_b_ms=opt_int(d, "lag_b_ms", path, None, -MAX_LAG_MS, MAX_LAG_MS),
        sync_version=opt_int(d, "sync_version", path, 1, 1, 1000),
    )


__all__ = [
    "SCHEMA",
    "Clip",
    "ClipAudio",
    "ImageMeta",
    "Inventory",
    "Notice",
    "SyncInfo",
    "SyncMember",
    "SyncRejected",
    "WorkFiles",
    "load_inventory",
    "save_inventory",
]
