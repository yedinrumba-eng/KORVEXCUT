"""The `[sync]` section of `kcut.toml`: the master, the thresholds and the manual offsets."""

import re
from types import MappingProxyType
from typing import Any

from kcut.config.model import SyncSection
from kcut.schema_util import (
    UNKNOWN_KEY,
    SchemaError,
    describe_value,
    join_path,
    obj,
    only_keys,
    opt_float,
    opt_int,
    opt_str,
)
from kcut.timebase import MAX_TIME_MS

_CLIP_ID = re.compile(r"[a-z][0-9]+")


def build_sync(d: dict[str, Any]) -> SyncSection:
    only_keys(
        d, {"master", "min_score", "min_ratio", "max_drift_ms", "min_refine_corr", "manual"}, "sync"
    )
    master = opt_str(d, "master", "sync", "")
    if master != "" and _CLIP_ID.fullmatch(master) is None:
        raise SchemaError(
            "sync.master", f'debe ser "" o un id de clip como a1 (vino {describe_value(master)})'
        )
    manual: dict[str, int] = {}
    table = obj(d.get("manual", {}), "sync.manual")
    for key, value in table.items():
        where = join_path("sync.manual", key)
        if _CLIP_ID.fullmatch(key) is None:  # the key is the file's own text: not in the path
            raise SchemaError(
                join_path("sync.manual", UNKNOWN_KEY),
                "la clave debe ser un id de clip como a2",
                full_path=where,
            )
        if isinstance(value, bool) or not isinstance(value, int):
            raise SchemaError(where, f"debe ser un entero en ms (vino {describe_value(value)})")
        manual[key] = opt_int(table, key, "sync.manual", 0, -MAX_TIME_MS, MAX_TIME_MS)
    return SyncSection(
        master=master,
        min_score=opt_float(d, "min_score", "sync", 0.35, 0.0, 1.0),
        min_ratio=opt_float(d, "min_ratio", "sync", 1.5, 1.0),
        max_drift_ms=opt_int(d, "max_drift_ms", "sync", 20, 1, 1000),
        min_refine_corr=opt_float(d, "min_refine_corr", "sync", 0.1, 0.0, 1.0),
        manual=MappingProxyType(manual),
    )
