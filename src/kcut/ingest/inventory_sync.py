"""The `sync` block of an inventory read from `.kcut/`: members, rejected clips, their free texts.

Split from `inventory.py` for the 300-line rule. Every id is checked as a clip id here (spec
001.12, point 1); that the ids are clips of the inventory is checked by `check_sync_refs`.
"""

from typing import Any

from kcut.config.names import has_forbidden_chars
from kcut.ingest.inventory_check import check_clip_id
from kcut.ingest.inventory_model import SyncInfo, SyncMember, SyncRejected
from kcut.ingest.sync_reasons import MAX_TEXT_LEN
from kcut.schema_util import (
    SchemaError,
    join_path,
    obj,
    only_keys,
    opt_float,
    opt_int,
    opt_list,
    opt_str,
    req_float,
    req_int,
    req_str,
)
from kcut.timebase import MAX_TIME_MS

MAX_DRIFT_WINDOWS = 100_000  # the windows of the drift check: far above any real clip


def _text(d: dict[str, Any], key: str, path: str) -> str:
    """Free text of the sync results: short, and with no control, format or line-separator
    characters (it may be printed to a terminal)."""
    value = req_str(d, key, path, max_len=MAX_TEXT_LEN)
    if has_forbidden_chars(value):
        raise SchemaError(
            join_path(path, key), "no puede llevar caracteres de control ni de formato"
        )
    return value


def obj_without_nulls(v: object, path: str) -> dict[str, Any]:
    """A JSON object where `null` means "absent" (the file writes `null` for missing values)."""
    return {k: item for k, item in obj(v, path).items() if item is not None}


def parse_sync(d: dict[str, Any]) -> SyncInfo:
    only_keys(d, {"master", "members", "rejected"}, "sync")
    members = tuple(
        _member(obj_without_nulls(m, join_path("sync.members", i)), join_path("sync.members", i))
        for i, m in enumerate(opt_list(d, "members", "sync", []))
    )
    rejected = tuple(
        _rejected(
            obj_without_nulls(r, join_path("sync.rejected", i)), join_path("sync.rejected", i)
        )
        for i, r in enumerate(opt_list(d, "rejected", "sync", []))
    )
    master = opt_str(d, "master", "sync", None)
    if master is not None:
        check_clip_id(master, "sync.master")
    return SyncInfo(master=master, members=members, rejected=rejected)


def _member(d: dict[str, Any], path: str) -> SyncMember:
    keys = {"id", "offset_ms", "score", "second", "ratio", "refine_corr", "drift_ms"}
    keys |= {"drift_windows", "method", "sync_version"}
    only_keys(d, keys, path)
    check_clip_id(req_str(d, "id", path), join_path(path, "id"))
    return SyncMember(
        id=req_str(d, "id", path),
        offset_ms=req_int(d, "offset_ms", path, -MAX_TIME_MS, MAX_TIME_MS),
        score=req_float(d, "score", path),
        second=req_float(d, "second", path),
        ratio=opt_float(d, "ratio", path, None),
        drift_ms=opt_int(d, "drift_ms", path, None, -MAX_TIME_MS, MAX_TIME_MS),
        drift_windows=req_int(d, "drift_windows", path, 0, MAX_DRIFT_WINDOWS),
        method=_text(d, "method", path),
        refine_corr=opt_float(d, "refine_corr", path, None),
        sync_version=opt_int(d, "sync_version", path, 1, 1, 1000),
    )


def _rejected(d: dict[str, Any], path: str) -> SyncRejected:
    keys = {"id", "score", "ratio", "refine_corr", "reason", "lag_a_ms", "lag_b_ms", "sync_version"}
    only_keys(d, keys, path)
    check_clip_id(req_str(d, "id", path), join_path(path, "id"))
    return SyncRejected(
        id=req_str(d, "id", path),
        score=req_float(d, "score", path),
        ratio=opt_float(d, "ratio", path, None),
        reason=_text(d, "reason", path),
        refine_corr=opt_float(d, "refine_corr", path, None),
        lag_a_ms=opt_int(d, "lag_a_ms", path, None, -MAX_TIME_MS, MAX_TIME_MS),
        lag_b_ms=opt_int(d, "lag_b_ms", path, None, -MAX_TIME_MS, MAX_TIME_MS),
        sync_version=opt_int(d, "sync_version", path, 1, 1, 1000),
    )
