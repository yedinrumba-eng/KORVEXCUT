"""A message about the image of a component never repeats its path (spec S1.8a step 0, 001.35 point
1; row 8). The path of a sticker can be a person's: `recursos/Maria-809-555-1234.png`. `Issue.path`
(`cues[N].params.image`) says which cue it is, and the message says only why it was refused.

Through `resolve`, as `tests/unit/gfx_codes_images.py` does (the project is a temporary folder, the
EDL the example of the spec). The CLI side (stdout, stderr and `--json`, exit 5) is in
`tests/integration/test_image_path_not_echoed.py`.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from kcut.gfx import assets, resolve_cues
from kcut.issues import Issue, exit_code
from kcut.project import Project
from tests.fixtures.links import make_dir_link
from tests.unit.gfx_resolve_fakes import (
    doc_without_captions,
    make_project,
    run_resolve,
    write_graphics,
    write_manifest,
)

NAME = "Maria-809-555-1234"
SECRETS = ("Maria", "809", "555", "1234")
WHERE = "cues[0].params.image"
NOT_IN_MANIFEST = (
    "el recurso no está en el manifiesto recursos/recursos.json: pide aprobación antes de usarlo"
)


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)


def _sticker(project: Project, image: str) -> None:
    params = {"image": image}
    cue = {"id": "mascota", "component": "sticker", "start": 0, "end": 30, "params": params}
    write_graphics(project, doc_without_captions(lambda d: d.update(cues=[cue])))


def _png(project: Project, rel: str) -> None:
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(project.root / rel, format="PNG")


def _only_error(project: Project) -> Issue:
    """The one error of the document, after checking that it does not carry the secret name."""
    errors = [i for i in run_resolve(project).issues if i.level == "error"]
    assert len(errors) == 1, errors
    (issue,) = errors
    assert issue.path == WHERE
    shown = f"{issue.path} {issue.message_es}"
    assert [s for s in SECRETS if s in shown] == [], shown
    return issue


def test_image_path_not_echoed_g10_an_image_that_is_not_in_the_manifest(project: Project) -> None:
    _png(project, f"recursos/{NAME}.png")
    _sticker(project, f"recursos/{NAME}.png")
    issue = _only_error(project)  # there is no manifest at all
    assert issue.code == "G10" and issue.message_es == NOT_IN_MANIFEST
    write_manifest(project, "recursos/otra.png")  # a manifest that lists something else
    issue = _only_error(project)
    assert issue.code == "G10" and issue.message_es == NOT_IN_MANIFEST


def test_image_path_not_echoed_g10_an_image_without_approval_says_so_without_the_path(
    project: Project,
) -> None:
    _png(project, f"recursos/{NAME}.png")
    write_manifest(project, f"recursos/{NAME}.png", approved_by="")
    _sticker(project, f"recursos/{NAME}.png")
    resolved = run_resolve(project)
    issue = _only_error(project)
    assert issue.code == "G10" and exit_code(resolved.issues) == 5
    assert issue.message_es == "el recurso no está aprobado: falta approved_by en el manifiesto"


def test_image_path_not_echoed_g09_an_approved_image_that_is_gone(project: Project) -> None:
    write_manifest(project, f"recursos/{NAME}.png")  # approved, but there is no such file
    _sticker(project, f"recursos/{NAME}.png")
    issue = _only_error(project)
    assert issue.code == "G09"
    assert issue.message_es == "el recurso aprobado no existe en el proyecto"


def _manifest_item(rel: str) -> dict[str, str]:
    return {
        "file": rel,
        "kind": "imagen",
        "origin": "propio",
        "license": "propia",
        "obtained": "2026-10-27",
        "approved_by": "test",
    }


@pytest.mark.parametrize(
    "manifest",
    [
        {"schema": "kcut.recursos/1", "items": [_manifest_item(f"../{NAME}.png")]},  # leaves it
        {"schema": "kcut.recursos/1", "items": [_manifest_item(f"edit/{NAME}.png")]},
        {"schema": "kcut.recursos/1", "items": [{**_manifest_item("recursos/x.png"), NAME: 1}]},
        {"schema": f"kcut.recursos/{NAME}", "items": []},
        {"schema": "kcut.recursos/1", "items": [{**_manifest_item("recursos/x.png"), "kind": 7}]},
    ],
    ids=["leaves-the-project", "not-in-recursos", "unknown-key", "schema", "kind"],
)
def test_image_path_not_echoed_g09_a_manifest_that_quotes_it_is_not_repeated(
    project: Project, manifest: dict[str, Any]
) -> None:
    _png(project, f"recursos/{NAME}.png")
    (project.root / "recursos" / "recursos.json").write_text(json.dumps(manifest), encoding="utf-8")
    _sticker(project, f"recursos/{NAME}.png")
    issue = _only_error(project)
    assert issue.code == "G09" and "recursos.json" in issue.message_es


def test_image_path_not_echoed_g09_a_manifest_that_is_not_json(project: Project) -> None:
    _png(project, f"recursos/{NAME}.png")
    (project.root / "recursos" / "recursos.json").write_text('{"Maria-809": ', encoding="utf-8")
    _sticker(project, f"recursos/{NAME}.png")
    assert _only_error(project).code == "G09"


@pytest.mark.parametrize(
    "image",
    [
        f"../{NAME}.png",  # outside the project
        f"/{NAME}.png",
        f"C:/{NAME}.png",
        f"recursos/../../{NAME}.png",
        f"edit/{NAME}.png",  # not in recursos/
        f"{NAME}.png",
        f"recursos/{NAME}.svg",  # not an extension kcut uses
        f"recursos/{NAME}",
        f"recursos/CON.{NAME}.png",  # a reserved name of Windows
    ],
)
def test_image_path_not_echoed_g09_a_path_that_cannot_be_used(project: Project, image: str) -> None:
    _sticker(project, image)
    assert _only_error(project).code == "G09"


def test_image_path_not_echoed_g09_a_link_that_leaves_the_project(
    project: Project, tmp_path: Path
) -> None:
    outside = tmp_path / "ajeno"
    outside.mkdir()
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(outside / "x.png", format="PNG")
    make_dir_link(project.root / "recursos" / NAME, outside)
    write_manifest(project, f"recursos/{NAME}/x.png")
    _sticker(project, f"recursos/{NAME}/x.png")
    assert _only_error(project).code == "G09"


def test_image_path_not_echoed_g09_the_format_the_size_and_the_pixels(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    rel = f"recursos/{NAME}.png"
    write_manifest(project, rel)
    _sticker(project, rel)
    (project.root / rel).write_bytes(b"this is not an image")  # Pillow cannot open it
    assert _only_error(project).message_es == assets.BAD_IMAGE
    Image.new("RGB", (8, 8)).save(project.root / rel, format="JPEG")  # a JPEG called .png
    assert _only_error(project).message_es == assets.BAD_IMAGE
    Image.new("1", (4097, 4096)).save(project.root / rel, format="PNG")  # too many pixels
    assert _only_error(project).message_es == assets.TOO_MANY_PIXELS
    _png(project, rel)
    monkeypatch.setattr(assets, "MAX_IMAGE_BYTES", 10)  # 20 MB, but small for the test
    assert "20 MB" in _only_error(project).message_es


def test_image_path_not_echoed_the_page_total_is_a_fixed_text(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    rel = f"recursos/{NAME}.png"
    _png(project, rel)
    write_manifest(project, rel)
    _sticker(project, rel)
    monkeypatch.setattr(assets, "MAX_PAGE_IMAGE_BYTES", 10)
    assert _only_error(project).message_es == assets.PAGE_IMAGES_TOO_BIG


def test_image_path_not_echoed_g03_a_path_of_100000_characters_never_reaches_the_disk(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`image` has `max_len=200`: more is a G03 with the length message, and nobody asks the file
    system about it (it used to be an exit 10, from the path that Windows cannot take)."""

    def never(*_a: object, **_k: object) -> str:
        raise AssertionError("the image must not be looked up")

    monkeypatch.setattr(resolve_cues, "image_data_uri", never)
    _sticker(project, "recursos/" + "a" * 99_991)
    resolved = run_resolve(project)
    assert [(i.code, i.path) for i in resolved.issues] == [("G03", WHERE)]
    assert resolved.issues[0].message_es == "debe tener como máximo 200 caracteres (tiene 100000)"
    assert exit_code(resolved.issues) == 1


def test_image_path_not_echoed_g03_200_characters_still_reach_the_lookup(project: Project) -> None:
    rel = "recursos/" + "a" * 187 + ".png"
    assert len(rel) == 200
    _png(project, rel)
    write_manifest(project, rel)
    _sticker(project, rel)
    resolved = run_resolve(project)
    assert resolved.issues == [] and list(resolved.images) == [rel]
