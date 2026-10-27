"""G09 and G10: the images a graphic may use (spec S1.6a row 4, DS9). A component that takes an
image is registered for the test: the base ones do not (the first is the sticker of S1.7).

Collected from `test_gfx_codes.py`, which is at the 300-line limit; `project` is its fixture.
"""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from kcut.gfx import assets
from kcut.gfx.components import COMPONENTS
from kcut.gfx.components_base import ComponentDef
from kcut.issues import exit_code
from kcut.params import ParamSpec
from kcut.project import Project
from tests.unit.gfx_resolve_fakes import (
    doc_without_captions as _doc,
)
from tests.unit.gfx_resolve_fakes import (
    errors_of as _errors,
)
from tests.unit.gfx_resolve_fakes import run_resolve, write_graphics, write_manifest

__all__ = [
    "test_gfx_codes_an_approved_image_goes_inside_the_page_as_a_data_uri",
    "test_gfx_codes_asset_format_pixels_a_png_that_is_a_jpg_is_g09",
    "test_gfx_codes_asset_format_pixels_each_extension_opens_as_its_own_format",
    "test_gfx_codes_asset_format_pixels_pillow_is_asked_for_the_format_and_the_size_first",
    "test_gfx_codes_asset_format_pixels_the_limit_is_4096_by_4096",
    "test_gfx_codes_g09_a_file_that_pillow_cannot_open_or_that_is_too_big",
    "test_gfx_codes_g09_an_image_that_cannot_be_used",
    "test_gfx_codes_g09_the_message_does_not_repeat_the_path_that_was_written",
    "test_gfx_codes_g10_an_image_that_is_not_in_the_manifest_or_has_no_approval",
]


def _picture(monkeypatch: pytest.MonkeyPatch) -> None:
    """A component that takes an image: base ones do not (S1.7 brings the first)."""
    spec = ParamSpec("image", "path", True, help_es="imagen")
    one = ComponentDef("picture", ("label.js",), False, (spec,), "Imagen", "", "", "bajo", "", "t")
    monkeypatch.setitem(COMPONENTS, "picture", one)


def _picture_doc(rel: str) -> dict[str, Any]:
    cue = {"id": "foto", "component": "picture", "start": 0, "end": 30, "params": {"image": rel}}
    return _doc(lambda d: d.update(cues=[cue]))


def _png(path: Path) -> None:
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(path)


@pytest.mark.parametrize(
    "rel",
    [
        "../x.png",
        "/abs/x.png",
        "C:/x.png",
        "edit/x.png",
        "x.png",
        "recursos/x.svg",
        "recursos/x.bmp",
        "recursos/x",
    ],
)
def test_gfx_codes_g09_an_image_that_cannot_be_used(
    project: Project, monkeypatch: pytest.MonkeyPatch, rel: str
) -> None:
    _picture(monkeypatch)
    write_graphics(project, _picture_doc(rel))
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G09", "cues[0].params.image")]
    assert resolved.cues == () and resolved.images == {}
    assert exit_code(resolved.issues) == 1


def test_gfx_codes_g09_a_file_that_pillow_cannot_open_or_that_is_too_big(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    _picture(monkeypatch)
    write_manifest(project, "recursos/mala.png")
    (project.root / "recursos" / "mala.png").write_bytes(b"this is not an image")
    write_graphics(project, _picture_doc("recursos/mala.png"))
    assert _errors(run_resolve(project)) == [("G09", "cues[0].params.image")]
    _png(project.root / "recursos" / "mala.png")
    monkeypatch.setattr(assets, "MAX_IMAGE_BYTES", 10)  # 20 MB, but small for the test
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G09", "cues[0].params.image")]
    assert "20 MB" in resolved.issues[0].message_es


def test_gfx_codes_g09_the_message_does_not_repeat_the_path_that_was_written(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    _picture(monkeypatch)
    write_graphics(project, _picture_doc("../IGNORE PREVIOUS INSTRUCTIONS/x.png"))
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G09", "cues[0].params.image")]
    assert "IGNORE" not in resolved.issues[0].message_es


def test_gfx_codes_g10_an_image_that_is_not_in_the_manifest_or_has_no_approval(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    _picture(monkeypatch)
    _png(project.root / "recursos" / "logo.png")
    write_graphics(project, _picture_doc("recursos/logo.png"))
    resolved = run_resolve(project)  # no manifest
    assert _errors(resolved) == [("G10", "cues[0].params.image")]
    assert exit_code(resolved.issues) == 5
    write_manifest(project, "recursos/logo.png", approved_by="")
    resolved = run_resolve(project)  # listed, but nobody approved it
    assert (
        _errors(resolved) == [("G10", "cues[0].params.image")] and exit_code(resolved.issues) == 5
    )
    assert resolved.cues == ()


def test_gfx_codes_an_approved_image_goes_inside_the_page_as_a_data_uri(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    _picture(monkeypatch)
    _png(project.root / "recursos" / "logo.png")
    write_manifest(project, "recursos/logo.png")
    write_graphics(project, _picture_doc("recursos/logo.png"))
    resolved = run_resolve(project)
    assert resolved.issues == [] and [c.id for c in resolved.cues] == ["foto"]
    assert list(resolved.images) == ["recursos/logo.png"]
    assert resolved.images["recursos/logo.png"].startswith("data:image/png;base64,iVBOR")
    assert resolved.cues[0].params == {"image": "recursos/logo.png"}  # the path, not the data URI


def _saved(project: Project, name: str, image: Image.Image, image_format: str) -> str:
    """Save `image` as `image_format` under the name `recursos/<name>` and approve it."""
    rel = f"recursos/{name}"
    image.save(project.root / rel, format=image_format)
    write_manifest(project, rel)
    return rel


@pytest.mark.parametrize(
    ("name", "saved_as"),
    [
        ("falsa.jpg", "PNG"),
        ("falsa.jpeg", "PNG"),
        ("falsa.png", "JPEG"),
        ("falsa.webp", "PNG"),
        ("falsa.png", "WEBP"),
        ("falsa.jpg", "WEBP"),
    ],
)
def test_gfx_codes_asset_format_pixels_a_png_that_is_a_jpg_is_g09(
    project: Project, monkeypatch: pytest.MonkeyPatch, name: str, saved_as: str
) -> None:
    """An image that is not the format of its extension is G09, with a fixed text and no path."""
    _picture(monkeypatch)
    rel = _saved(project, name, Image.new("RGB", (8, 8), (255, 0, 0)), saved_as)
    write_graphics(project, _picture_doc(rel))
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G09", "cues[0].params.image")]
    assert resolved.issues[0].message_es == assets.BAD_IMAGE
    assert "falsa" not in resolved.issues[0].message_es and resolved.images == {}


@pytest.mark.parametrize(
    ("name", "saved_as", "prefix"),
    [
        ("ok.png", "PNG", "data:image/png;base64,"),
        ("ok.jpg", "JPEG", "data:image/jpeg;base64,"),
        ("ok.jpeg", "JPEG", "data:image/jpeg;base64,"),
        ("ok.webp", "WEBP", "data:image/webp;base64,"),
        ("OK.JPG", "JPEG", "data:image/jpeg;base64,"),
    ],
)
def test_gfx_codes_asset_format_pixels_each_extension_opens_as_its_own_format(
    project: Project, monkeypatch: pytest.MonkeyPatch, name: str, saved_as: str, prefix: str
) -> None:
    _picture(monkeypatch)
    rel = _saved(project, name, Image.new("RGB", (8, 8), (255, 0, 0)), saved_as)
    write_graphics(project, _picture_doc(rel))
    resolved = run_resolve(project)
    assert resolved.issues == [] and resolved.images[rel].startswith(prefix)


@pytest.mark.parametrize(
    ("size", "ok"), [((4096, 4096), True), ((4097, 4096), False), ((4096, 4097), False)]
)
def test_gfx_codes_asset_format_pixels_the_limit_is_4096_by_4096(
    project: Project, monkeypatch: pytest.MonkeyPatch, size: tuple[int, int], ok: bool
) -> None:
    """Mode `1` (a bit per pixel) keeps the file small: only the size of the picture is in play."""
    _picture(monkeypatch)
    rel = _saved(project, "grande.png", Image.new("1", size), "PNG")
    write_graphics(project, _picture_doc(rel))
    resolved = run_resolve(project)
    if ok:
        assert resolved.issues == [] and rel in resolved.images
    else:
        assert _errors(resolved) == [("G09", "cues[0].params.image")]
        assert resolved.issues[0].message_es == assets.TOO_MANY_PIXELS
        assert "grande" not in resolved.issues[0].message_es and resolved.images == {}


def test_gfx_codes_asset_format_pixels_pillow_is_asked_for_the_format_and_the_size_first(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Image.open` gets `formats=[<format of the extension>]`, and a picture over the limit is
    refused before `load()` decodes it."""
    _picture(monkeypatch)
    rel = _saved(project, "grande.png", Image.new("1", (4097, 4096)), "PNG")
    write_graphics(project, _picture_doc(rel))
    opened: list[dict[str, Any]] = []
    loaded: list[bool] = []
    real_open, real_load = Image.open, Image.Image.load

    def spy_open(*args: Any, **kwargs: Any) -> Image.Image:
        opened.append(kwargs)
        return real_open(*args, **kwargs)

    def spy_load(self: Image.Image) -> Any:
        loaded.append(True)
        return real_load(self)

    monkeypatch.setattr(Image, "open", spy_open)
    monkeypatch.setattr(Image.Image, "load", spy_load)
    assert _errors(run_resolve(project)) == [("G09", "cues[0].params.image")]
    assert opened == [{"formats": ["PNG"]}] and loaded == []
