"""A broken manifest says where it is broken, and quotes no value (spec S1.8b step 0, 001.36 point
9; row 20). The fixed texts of S1.8a-8 hid everything, so with a manifest of 20 items nothing said
which one was wrong. Now `require_approved` names the place: `items[N].<key>` when the key is one
that kcut knows (the `[N]` and the known keys are kcut's own words), `línea L, columna C` when the
JSON cannot be read. A key that kcut does not know is `<clave desconocida>`, never the key, and a
value is never printed (`approved_by` as a number: its number is not in the message).
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut.errors import ProjectError
from kcut.project import Project
from kcut.recursos.manifest import require_approved
from tests.unit.gfx_resolve_fakes import make_project

SECRET = "Maria-809-555-1234"
VALUE = 7654321


def _item(n: int, **changes: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "file": f"recursos/uno-{n}.png",
        "kind": "imagen",
        "origin": "propio",
        "license": "propia",
        "obtained": "2026-10-28",
        "approved_by": "test",
    }
    return item | changes


def _write(project: Project, data: object) -> None:
    text = data if isinstance(data, str) else json.dumps(data)
    (project.root / "recursos" / "recursos.json").write_text(text, encoding="utf-8")


def _message(project: Project) -> str:
    with pytest.raises(ProjectError) as info:
        require_approved(project, "recursos/uno-0.png")
    assert info.value.exit_code == 3
    return info.value.message_es


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)


def test_manifest_where_a_wrong_value_names_the_item_and_the_key_and_not_the_value(
    project: Project,
) -> None:
    items = [_item(0), _item(1), _item(2), _item(3, approved_by=VALUE)]
    _write(project, {"schema": "kcut.recursos/1", "items": items})
    message = _message(project)
    assert "items[3].approved_by" in message and str(VALUE) not in message
    assert "recursos/recursos.json" in message and "ábrelo y corrígelo" in message


def test_manifest_where_each_known_key_is_named(project: Project) -> None:
    for key, value in (("kind", 7), ("origin", "otro"), ("obtained", "ayer"), ("license", "")):
        _write(
            project, {"schema": "kcut.recursos/1", "items": [_item(0), _item(1, **{key: value})]}
        )
        assert f"items[1].{key}" in _message(project), key


def test_manifest_where_a_key_that_kcut_does_not_know_is_not_printed(project: Project) -> None:
    _write(project, {"schema": "kcut.recursos/1", "items": [_item(0), _item(1, **{SECRET: 1})]})
    message = _message(project)
    assert "items[1]" in message and "<clave desconocida>" in message
    assert [s for s in SECRET.split("-") if s in message] == [], message


def test_manifest_where_json_that_cannot_be_read_says_the_line_and_the_column(
    project: Project,
) -> None:
    _write(project, '{"schema": "kcut.recursos/1",\n "items": [{"file": ')
    message = _message(project)
    assert "(línea 2, columna " in message
    assert "kcut.recursos" not in message  # nothing of the text of the file


def test_manifest_where_the_top_level_and_the_schema_are_named_too(project: Project) -> None:
    _write(project, {"schema": f"kcut.recursos/{SECRET}", "items": []})
    message = _message(project)
    assert "(schema)" in message and SECRET not in message
    _write(project, [1, 2])
    assert "ábrelo y corrígelo" in _message(project)  # the whole file: no place to name
