"""A ceiling for the total weight of the images in the page (spec S1.7 step 0, 001.33 point 8; row
16). Each image has its own ceiling (20 MB and 4096 x 4096), and with 500 cues that name different
images `page.html` could weigh gigabytes. `MAX_PAGE_IMAGE_BYTES` is 64 MiB, counted over what is
written into the page: each different image once (a path that comes twice is one image, the page
shares it) and each file that comes under another path again (it is written again). The weight of
an image is its bytes, not the characters of its data URI: 64 MiB hold three images of the 20 MB
ceiling.

The cue that crosses the ceiling is a G09 (exit 1) with a fixed text, found by `graphics check`
before anything is captured; the images that were already in stay, and a later cue whose image still
fits is fine. The images here are padded after the end of the PNG, so each one is a real image that
Pillow opens and decodes, of 18 MiB. The cues are `sticker` cues, the first component of the project
with an image (001.34: before S1.7 these tests used a component made for the test).
"""

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from kcut.gfx import assets
from kcut.issues import exit_code
from kcut.project import Project
from tests.unit.gfx_resolve_fakes import (
    doc_without_captions,
    errors_of,
    make_project,
    run_resolve,
    write_graphics,
)

MIB = 1024 * 1024
HEAVY = 18 * MIB
MESSAGE = "las imágenes de los gráficos pasan de 64 MiB en total; usa menos o más livianas"


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)


def _image(project: Project, name: str, size: int = HEAVY) -> str:
    """A PNG that Pillow opens, padded after its end so that the file weighs `size` bytes."""
    buffer = io.BytesIO()
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(buffer, format="PNG")
    data = buffer.getvalue()
    rel = f"recursos/{name}"
    (project.root / rel).write_bytes(data + b"\0" * (size - len(data)))
    return rel


def _approve(project: Project, rels: list[str]) -> None:
    items = [
        {
            "file": rel,
            "kind": "imagen",
            "origin": "propio",
            "license": "propia",
            "obtained": "2026-10-27",
            "approved_by": "test",
        }
        for rel in rels
    ]
    text = json.dumps({"schema": "kcut.recursos/1", "items": items})
    (project.root / "recursos" / "recursos.json").write_text(text, encoding="utf-8", newline="\n")


def _cues(project: Project, rels: list[str]) -> None:
    cues = [
        {
            "id": f"foto-{i}",
            "component": "sticker",  # 001.34: the real one (it was a fake `picture` component)
            "start": 10 * i,
            "end": 10 * i + 8,
            "params": {"image": rel},
        }
        for i, rel in enumerate(rels)
    ]
    write_graphics(project, doc_without_captions(lambda d: d.update(cues=cues)))


def test_page_image_total_the_ceiling_is_64_mib() -> None:
    assert assets.MAX_PAGE_IMAGE_BYTES == 64 * 1024 * 1024


def test_page_image_total_four_heavy_images_cross_it_in_the_fourth_cue(project: Project) -> None:
    rels = [_image(project, f"s{i}.png") for i in range(4)]
    _approve(project, rels)
    _cues(project, rels)
    resolved = run_resolve(project)
    assert errors_of(resolved) == [("G09", "cues[3].params.image")]
    assert resolved.issues[0].message_es == MESSAGE
    assert exit_code(resolved.issues) == 1
    assert [c.id for c in resolved.cues] == ["foto-0", "foto-1", "foto-2"]
    assert list(resolved.images) == rels[:3]  # the one that crossed is not in the page


def test_page_image_total_three_heavy_images_fit(project: Project) -> None:
    rels = [_image(project, f"s{i}.png") for i in range(3)]
    _approve(project, rels)
    _cues(project, rels)
    resolved = run_resolve(project)
    assert resolved.issues == [] and list(resolved.images) == rels
    assert exit_code(resolved.issues) == 0


def test_page_image_total_an_image_the_page_shares_counts_once(project: Project) -> None:
    rel = _image(project, "uno.png")
    _approve(project, [rel])
    _cues(project, [rel] * 5)  # five cues, one image: 18 MiB in the page, not 90
    resolved = run_resolve(project)
    assert resolved.issues == [] and list(resolved.images) == [rel]
    assert len(resolved.cues) == 5


def test_page_image_total_the_same_bytes_under_two_paths_are_written_twice(
    project: Project,
) -> None:
    rels = [_image(project, f"copia-{i}.png") for i in range(4)]  # the same bytes, four paths
    _approve(project, rels)
    _cues(project, rels)
    assert errors_of(run_resolve(project)) == [("G09", "cues[3].params.image")]


def test_page_image_total_a_later_cue_whose_image_still_fits_is_fine(project: Project) -> None:
    heavy = [_image(project, f"s{i}.png") for i in range(4)]
    light = _image(project, "ligera.png", size=1024)
    _approve(project, [*heavy, light])
    _cues(project, [*heavy, light])
    resolved = run_resolve(project)
    assert errors_of(resolved) == [("G09", "cues[3].params.image")]  # only the one that crossed
    assert [c.id for c in resolved.cues] == ["foto-0", "foto-1", "foto-2", "foto-4"]


def test_page_image_total_the_ceiling_is_the_one_that_is_set(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assets, "MAX_PAGE_IMAGE_BYTES", 2048)
    rels = [_image(project, f"s{i}.png", size=1024) for i in range(3)]
    _approve(project, rels)
    _cues(project, rels)
    assert errors_of(run_resolve(project)) == [("G09", "cues[2].params.image")]


def test_page_image_total_an_image_that_is_refused_adds_nothing_to_the_total(
    project: Project,
) -> None:
    """The weight is counted for an image that passed every other check: one that is refused
    (not approved, G10) adds nothing to the total."""
    ok = [_image(project, f"s{i}.png") for i in range(3)]
    refused = _image(project, "sin-aprobar.png")
    _approve(project, ok)  # `refused` is not in the manifest
    _cues(project, [*ok, refused])
    resolved = run_resolve(project)
    assert errors_of(resolved) == [("G10", "cues[3].params.image")]
    assert exit_code(resolved.issues) == 5
