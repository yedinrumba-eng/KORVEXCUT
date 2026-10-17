"""Trust checks for an inventory read from `.kcut/`: the cache is never trusted (spec 0.9).

A poisoned `inventory.json` could name `../../x` as an id or point a work file at `crudo/`, so
every id, slug and path is validated with `re.fullmatch` and resolved before anything uses it.
"""

import os
import re
from collections.abc import Mapping
from pathlib import Path

from kcut.errors import ProjectError
from kcut.ingest.classify import ID_HIGH_MAX, ID_PREFIX
from kcut.ingest.inventory_model import Clip
from kcut.paths import is_inside, resolve_in_project, to_rel
from kcut.schema_util import SchemaError

_ID = re.compile(r"[a-z][0-9]{1,6}")
_SLUG = re.compile(r"[a-z0-9-]{1,40}")
PREFIXES = frozenset(ID_PREFIX.values())


def check_clip(clip: Clip, root: Path) -> None:
    """Raise SchemaError if the clip's id, slug or any of its paths cannot be trusted."""
    here = f"clips[{clip.id}]"
    if _ID.fullmatch(clip.id) is None:
        raise SchemaError(f"{here}.id", f"debe ser una letra y 1-6 dígitos (vino {clip.id!r})")
    if clip.id[0] != ID_PREFIX[clip.clip_class]:
        raise SchemaError(f"{here}.id", f"el prefijo no corresponde a la clase {clip.clip_class}")
    if _SLUG.fullmatch(clip.slug) is None:
        raise SchemaError(f"{here}.slug", f"debe ser [a-z0-9-] de 1 a 40 (vino {clip.slug!r})")
    _under(root, clip.file, "crudo", f"{here}.file")
    if clip.work is not None:
        if clip.work.proxy is not None:
            _under(root, clip.work.proxy, ".kcut/proxy", f"{here}.work.proxy")
        if clip.work.wav16 is not None:
            _under(root, clip.work.wav16, ".kcut/wav16", f"{here}.work.wav16")


def check_ids(clips: tuple[Clip, ...], id_high: Mapping[str, int] | None) -> dict[str, int]:
    """No duplicate ids; `id_high` has valid prefixes and covers every id present.

    Returns the effective `id_high` (derived from the ids when the file has none).
    """
    seen: set[str] = set()
    top: dict[str, int] = {}
    for clip in clips:
        if clip.id in seen:
            raise SchemaError(f"clips[{clip.id}].id", "está repetido")
        seen.add(clip.id)
        top[clip.id[0]] = max(top.get(clip.id[0], 0), int(clip.id[1:]))
    if id_high is None:
        return top
    for prefix, number in id_high.items():
        if prefix not in PREFIXES:
            raise SchemaError(f"id_high.{prefix}", "prefijo de id desconocido")
        if not 0 <= number <= ID_HIGH_MAX:
            raise SchemaError(f"id_high.{prefix}", f"debe estar entre 0 y {ID_HIGH_MAX}")
    for prefix, number in top.items():
        if id_high.get(prefix, 0) < number:
            raise SchemaError(
                f"id_high.{prefix}", f"es menor que un id presente ({prefix}{number})"
            )
    return dict(id_high)


def _under(root: Path, rel: str, folder: str, where: str) -> None:
    """`rel` must be the canonical POSIX path of a file under `<root>/<folder>/`."""
    try:
        resolved = resolve_in_project(root, rel)
        canonical = to_rel(root, resolved)
    except ProjectError as exc:
        raise SchemaError(where, exc.message_es) from None
    same = os.path.normcase(canonical) == os.path.normcase(rel)
    if not same or not is_inside((root / folder).resolve(), resolved) or canonical == folder:
        raise SchemaError(where, f"debe ser una ruta canónica bajo {folder}/ (vino {rel!r})")
