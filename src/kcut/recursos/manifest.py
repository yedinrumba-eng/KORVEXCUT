"""`recursos/recursos.json`: the approved-assets manifest (D7, DS9)."""

import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from kcut.errors import GateError, ProjectError
from kcut.jsonio import read_json
from kcut.paths import resolve_in_project, to_rel
from kcut.project import Project
from kcut.schema_util import (
    SchemaError,
    join_path,
    obj,
    one_of,
    only_keys,
    opt_str,
    req_list,
    req_str,
)

SCHEMA = "kcut.recursos/1"
KINDS = ("imagen", "musica", "sfx", "video", "fuente", "otro")
ORIGINS = ("propio", "descargado", "generado", "cliente")
_KEYS = {
    "file",
    "kind",
    "origin",
    "source_url",
    "license",
    "license_url",
    "obtained",
    "approved_by",
    "approved_on",
    "notes",
}
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class ResourceItem:
    file: str
    kind: str
    origin: str
    source_url: str | None
    license: str
    license_url: str | None
    obtained: str
    approved_by: str
    approved_on: str | None
    notes: str


def load_manifest(project: Project) -> list[ResourceItem]:
    """Every item of the manifest; a missing manifest means no resources. Errors raise."""
    return [_parse_item(project, raw, join_path("items", i)) for i, raw in _raw_items(project)]


def validate_manifest(project: Project) -> list[str]:
    """Every problem of the manifest as a Spanish sentence (empty list: all good)."""
    try:
        raw_items = _raw_items(project)
    except ProjectError as exc:
        return [exc.message_es]
    errors: list[str] = []
    seen: set[str] = set()
    for index, raw in raw_items:
        path = join_path("items", index)
        try:
            item = _parse_item(project, raw, path)
        except ProjectError as exc:
            errors.append(exc.message_es)
            continue
        key = os.path.normcase(item.file)
        if key in seen:
            errors.append(f"{path}.file: {item.file} está repetido en el manifiesto")
        seen.add(key)
        if not resolve_in_project(project.root, item.file).is_file():
            errors.append(f"{path}.file: {item.file} no existe en el proyecto")
    return errors


def require_approved(project: Project, rel: str) -> ResourceItem:
    """The manifest entry of `rel`, or GateError (exit 5) if it is unlisted or unapproved."""
    wanted = to_rel(project.root, resolve_in_project(project.root, rel))
    for item in load_manifest(project):
        if os.path.normcase(item.file) != os.path.normcase(wanted):
            continue
        if not item.approved_by.strip():
            raise GateError(
                f"el recurso {wanted} no está aprobado: falta approved_by en el manifiesto"
            )
        if not resolve_in_project(project.root, wanted).is_file():
            raise ProjectError(f"el recurso aprobado {wanted} no existe en el proyecto")
        return item
    raise GateError(
        f"el recurso {wanted} no está en el manifiesto recursos/recursos.json: "
        "pide aprobación antes de usarlo"
    )


def _raw_items(project: Project) -> list[tuple[int, dict[str, Any]]]:
    path = project.layout.manifest
    if not path.is_file():
        return []
    try:
        data = obj(read_json(path), "")
        only_keys(data, {"schema", "items"}, "")
        schema = req_str(data, "schema", "")
        if schema != SCHEMA:
            raise SchemaError("schema", f"se esperaba {SCHEMA} (vino {schema!r})")
        return [
            (i, _without_nulls(obj(item, join_path("items", i))))
            for i, item in enumerate(req_list(data, "items", ""))
        ]
    except SchemaError as exc:
        raise ProjectError(f"{path.name}: {exc.message_es}") from None


def _parse_item(project: Project, d: dict[str, Any], path: str) -> ResourceItem:
    try:
        return _item(project, d, path)
    except SchemaError as exc:
        raise ProjectError(f"{project.layout.manifest.name}: {exc.message_es}") from None


def _item(project: Project, d: dict[str, Any], path: str) -> ResourceItem:
    only_keys(d, _KEYS, path)
    origin = one_of(req_str(d, "origin", path), ORIGINS, join_path(path, "origin"))
    source_url = opt_str(d, "source_url", path, None)
    if origin == "descargado" and not (source_url or "").strip():
        raise SchemaError(
            join_path(path, "source_url"), 'es obligatorio cuando origin es "descargado"'
        )
    license_text = req_str(d, "license", path)
    if not license_text.strip():
        raise SchemaError(join_path(path, "license"), "no puede estar vacía")
    return ResourceItem(
        file=_file(project, req_str(d, "file", path), join_path(path, "file")),
        kind=one_of(req_str(d, "kind", path), KINDS, join_path(path, "kind")),
        origin=origin,
        source_url=source_url,
        license=license_text,
        license_url=opt_str(d, "license_url", path, None),
        obtained=_date(req_str(d, "obtained", path), join_path(path, "obtained")),
        approved_by=req_str(d, "approved_by", path),
        approved_on=_optional_date(d, "approved_on", path),
        notes=opt_str(d, "notes", path, ""),
    )


def _file(project: Project, rel: str, where: str) -> str:
    try:
        normalized = to_rel(project.root, resolve_in_project(project.root, rel))
    except ProjectError as exc:
        raise SchemaError(where, exc.message_es) from None
    if not normalized.startswith("recursos/"):
        raise SchemaError(where, f"debe empezar con recursos/ (vino {rel!r})")
    return normalized


def _optional_date(d: dict[str, Any], key: str, path: str) -> str | None:
    value = opt_str(d, key, path, None)
    return None if value is None else _date(value, join_path(path, key))


def _date(text: str, where: str) -> str:
    try:
        valid = _DATE.fullmatch(text) is not None and date.fromisoformat(text) is not None
    except ValueError:
        valid = False
    if not valid:
        raise SchemaError(where, f"debe ser una fecha AAAA-MM-DD (vino {text!r})")
    return text


def _without_nulls(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}
