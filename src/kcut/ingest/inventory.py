"""`.kcut/inventory.json`: what is in `crudo/`, how it was classified, its work files and sync.

The dataclasses live in `inventory_model.py` (split for the 300-line rule) and are re-exported here.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast, get_args

from kcut.errors import ProjectError
from kcut.ingest.classify import ClipClass
from kcut.ingest.inventory_check import (
    PREFIXES,
    check_clip,
    check_ids,
    check_sync_refs,
)
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
from kcut.ingest.inventory_sync import obj_without_nulls as _obj
from kcut.ingest.inventory_sync import parse_sync
from kcut.ingest.probe import VideoInfo
from kcut.jsonio import MAX_INVENTORY_BYTES, read_json, write_json_atomic
from kcut.schema_util import (
    SchemaError,
    describe_value,
    join_path,
    one_of,
    only_keys,
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
MAX_PATH_LEN = 260  # characters of a path in the inventory: Windows' own limit


FIELD_MAX = 120  # characters of a field path that go into a message


def field_text(field: str) -> str:
    """A field path cut to 120 characters (the last three are `...` when it was longer)."""
    return field if len(field) <= FIELD_MAX else field[: FIELD_MAX - 3] + "..."


class InventoryInvalid(ProjectError):
    """The file parsed but failed validation. `field` is the data path of the value that did
    (`clips[3].slug`, never the value); the message holds everything, so only a log may print it."""

    def __init__(self, message_es: str, field: str) -> None:
        super().__init__(message_es)
        self.field = field


def load_inventory(path: Path, root: Path | None = None) -> Inventory:
    """Read and validate an inventory file; the cache is never trusted.

    `root` is the project root (default: two levels above `.kcut/inventory.json`). Any bad id,
    slug or path makes the whole file invalid (InventoryInvalid, a ProjectError).
    """
    base = root if root is not None else path.resolve().parent.parent
    try:
        return _inventory(read_json(path, MAX_INVENTORY_BYTES), base)
    except SchemaError as exc:
        raise InventoryInvalid(f"{path.name}: {exc.full_es}", exc.path) from None


def save_inventory(path: Path, inv: Inventory) -> None:
    write_json_atomic(path, inventory_to_json(inv))


def _inventory(data: object, root: Path) -> Inventory:
    d = _obj(data, "")
    only_keys(d, {"schema", "generated", "fps", "id_high", "clips", "sync"}, "")
    schema = req_str(d, "schema", "")
    if schema != SCHEMA:
        raise SchemaError("schema", f"se esperaba {SCHEMA} (vino {describe_value(schema)})")
    clips = tuple(
        _clip(_obj(item, join_path("clips", i)), i)
        for i, item in enumerate(req_list(d, "clips", ""))
    )
    for index, clip in enumerate(clips):
        check_clip(clip, root, index)
    raw_high = _obj(d["id_high"], "id_high") if "id_high" in d else None
    high = None if raw_high is None else _id_high(raw_high)
    sync = parse_sync(_obj(d.get("sync", {}), "sync"))
    check_sync_refs(sync, clips)
    return Inventory(
        generated=req_str(d, "generated", ""),
        fps=req_int(d, "fps", "", 1, 240),
        clips=clips,
        sync=sync,
        id_high=check_ids(clips, high),
    )


def _id_high(raw: dict[str, Any]) -> dict[str, int]:
    """The `id_high` numbers. A key that is not an id prefix is the file's own text, so the path
    of its error stops at `id_high` (the key is in the log, spec 001.14 point 2)."""
    high: dict[str, int] = {}
    for key in raw:
        try:
            high[key] = req_int(raw, key, "id_high")
        except SchemaError as exc:
            if key in PREFIXES:
                raise
            raise SchemaError("id_high", exc.detail_es, full_path=exc.path) from None
    return high


def _clip(d: dict[str, Any], index: int) -> Clip:
    here = join_path("clips", index)  # by position: the id is not trusted yet
    allowed = {"id", "file", "slug", "class", "qhash", "size_bytes", "duration_ms", "frames"}
    only_keys(d, allowed | {"video", "audio", "image", "work", "warnings"}, here)
    clip_class = one_of(req_str(d, "class", here), get_args(ClipClass), join_path(here, "class"))
    return Clip(
        id=req_str(d, "id", here, min_len=2),
        file=req_str(d, "file", here, max_len=MAX_PATH_LEN, min_len=1),
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
        display_w=req_int(d, "display_w", path, 1),  # 001.24, point 12: 0 is no picture
        display_h=req_int(d, "display_h", path, 1),
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


MAX_PROXY_SIDE = 4096  # width or height of a proxy the inventory takes (spec 001.20, point 4)


def _work(d: dict[str, Any], path: str) -> WorkFiles:
    only_keys(d, {"proxy", "wav16", "proxy_w", "proxy_h"}, path)
    return WorkFiles(
        proxy=opt_str(d, "proxy", path, None, max_len=MAX_PATH_LEN),
        wav16=opt_str(d, "wav16", path, None, max_len=MAX_PATH_LEN),
        proxy_w=opt_int(d, "proxy_w", path, None, 1, MAX_PROXY_SIDE),
        proxy_h=opt_int(d, "proxy_h", path, None, 1, MAX_PROXY_SIDE),
    )


def _warnings(d: dict[str, Any], here: str) -> list[str]:
    items = opt_list(d, "warnings", here, [])
    for i, item in enumerate(items):
        if not isinstance(item, str):
            raise SchemaError(join_path(join_path(here, "warnings"), i), "debe ser texto")
    return cast(list[str], items)


__all__ = [
    "SCHEMA",
    "Clip",
    "ClipAudio",
    "ImageMeta",
    "Inventory",
    "InventoryInvalid",
    "Notice",
    "SyncInfo",
    "SyncMember",
    "SyncRejected",
    "WorkFiles",
    "field_text",
    "load_inventory",
    "save_inventory",
]
