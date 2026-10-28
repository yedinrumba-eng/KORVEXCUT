"""The walk over the chunks of an image stops at 64 (spec S1.8b step 0, 001.36 point 4; row 15).

`assets._png_has_actl` and `_webp_is_animated` walk the chunks of the header, by their lengths,
until the first `IDAT` (or the first `VP8 `, `VP8L` or `ANMF`). A PNG of 20 MiB with 1.75 million
empty chunks cost 3 s each time a cue read it. The walk is now at most 64 chunks after the header
chunk (`IHDR`, or the `VP8X` of a WebP); one more before the image is a G09 with a fixed text, no
path. And `resolve_cues` keeps in the cache of the document the images that were refused too, by
their `rel`: eight cues with the same bad image read it once.
"""

import struct
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from kcut.errors import ProjectError
from kcut.gfx import assets
from kcut.project import Project
from tests.unit.gfx_resolve_fakes import (
    doc_without_captions,
    errors_of,
    make_project,
    run_resolve,
    write_graphics,
    write_manifest,
)

TEXT = "la imagen tiene demasiados bloques; vuelve a exportarla"
PNG_HEAD = 8 + 25  # the signature and the whole `IHDR` chunk (4 + 4 + 13 + 4)


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)


def _text_chunk() -> bytes:
    """An empty `tEXt` chunk with its real CRC (Pillow checks it when it opens the file)."""
    return struct.pack(">I", 0) + b"tEXt" + struct.pack(">I", zlib.crc32(b"tEXt"))


def _png_with(project: Project, name: str, extra_chunks: int) -> str:
    """`recursos/<name>`: a real PNG with `extra_chunks` empty `tEXt` chunks before its `IDAT`,
    approved in the manifest."""
    rel = f"recursos/{name}"
    path = project.root / rel
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(path, format="PNG")
    data = path.read_bytes()
    path.write_bytes(data[:PNG_HEAD] + _text_chunk() * extra_chunks + data[PNG_HEAD:])
    write_manifest(project, rel)
    return rel


def _cues(rel: str, count: int) -> list[dict[str, Any]]:
    return [
        {"id": f"c{i}", "component": "sticker", "start": 0, "end": 30, "params": {"image": rel}}
        for i in range(count)
    ]


def _resolve(project: Project, rel: str, count: int = 1) -> Any:
    write_graphics(project, doc_without_captions(lambda d: d.update(cues=_cues(rel, count))))
    return run_resolve(project)


def test_image_chunk_cap_a_png_with_65_chunks_before_idat_is_g09(project: Project) -> None:
    resolved = _resolve(project, _png_with(project, "muchos.png", 65))
    assert errors_of(resolved) == [("G09", "cues[0].params.image")]
    assert resolved.issues[0].message_es == TEXT == assets.TOO_MANY_CHUNKS
    assert "muchos" not in resolved.issues[0].message_es and resolved.images == {}


def test_image_chunk_cap_a_png_with_64_chunks_is_not_g09(project: Project) -> None:
    rel = _png_with(project, "justos.png", 64)
    resolved = _resolve(project, rel)
    assert resolved.issues == [] and rel in resolved.images


def test_image_chunk_cap_a_png_with_none_goes_through_as_before(project: Project) -> None:
    rel = _png_with(project, "limpia.png", 0)
    resolved = _resolve(project, rel)
    assert resolved.issues == [] and rel in resolved.images


def _chunk(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + b"\0\0\0\0"


def _webp_chunk(kind: bytes, payload: bytes = b"\0" * 10) -> bytes:
    return kind + struct.pack("<I", len(payload)) + payload


def _riff(*chunks: bytes) -> bytes:
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_image_chunk_cap_the_walk_of_a_png_stops_at_64_chunks_after_ihdr() -> None:
    head = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", b"\0" * 13)
    tail = _chunk(b"IDAT", b"\x78\x9c") + _chunk(b"IEND")
    assert assets._is_animated(head + _chunk(b"sRGB") * 64 + tail, "PNG") is False
    with pytest.raises(ProjectError) as info:
        assets._is_animated(head + _chunk(b"sRGB") * 65 + tail, "PNG")
    assert info.value.message_es == TEXT
    # a `acTL` found inside the first 64 is still an animation, and the cap does not hide it
    assert assets._is_animated(head + _chunk(b"sRGB") * 3 + _chunk(b"acTL") + tail, "PNG")
    # with no `IDAT` at all the walk ends at the cap too, and not by running through the file
    with pytest.raises(ProjectError):
        assets._is_animated(head + _chunk(b"sRGB") * 100, "PNG")


@pytest.mark.parametrize("data_chunk", [b"VP8 ", b"VP8L", b"ANMF"])
def test_image_chunk_cap_the_walk_of_a_webp_stops_at_64_chunks_after_the_header(
    data_chunk: bytes,
) -> None:
    head = _webp_chunk(b"VP8X")
    image = _webp_chunk(data_chunk)
    fine = _riff(head, *[_webp_chunk(b"JUNK")] * 64, image)
    assert assets._is_animated(fine, "WEBP") is False
    with pytest.raises(ProjectError) as info:
        assets._is_animated(_riff(head, *[_webp_chunk(b"JUNK")] * 65, image), "WEBP")
    assert info.value.message_es == TEXT


def test_image_chunk_cap_an_image_that_was_refused_is_read_once_for_8_cues(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    rel = _png_with(project, "rechazada.png", 65)
    reads: list[Path] = []
    real: Callable[[Path, int], bytes] = assets.read_capped

    def spy(path: Path, max_bytes: int) -> bytes:
        reads.append(path)
        return real(path, max_bytes)

    monkeypatch.setattr(assets, "read_capped", spy)
    resolved = _resolve(project, rel, 8)
    assert errors_of(resolved) == [("G09", f"cues[{i}].params.image") for i in range(8)]
    assert all(i.message_es == TEXT for i in resolved.issues)
    assert len(reads) == 1  # the image was read once, and the other 7 cues got the same answer


def test_image_chunk_cap_a_good_image_is_read_once_for_8_cues_too(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    rel = _png_with(project, "buena.png", 0)
    reads: list[Path] = []
    real: Callable[[Path, int], bytes] = assets.read_capped

    def spy(path: Path, max_bytes: int) -> bytes:
        reads.append(path)
        return real(path, max_bytes)

    monkeypatch.setattr(assets, "read_capped", spy)
    resolved = _resolve(project, rel, 8)
    assert resolved.issues == [] and len(reads) == 1


def test_image_chunk_cap_a_gate_refusal_is_kept_for_the_other_cues_too(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A G10 (not in the manifest) is a refusal too: the second cue gets it without asking the
    manifest again."""
    rel = "recursos/sin-aprobar.png"
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(project.root / rel, format="PNG")
    asked: list[str] = []
    real = assets.require_approved

    def spy(project: Project, wanted: str) -> Any:
        asked.append(wanted)
        return real(project, wanted)

    monkeypatch.setattr(assets, "require_approved", spy)
    resolved = _resolve(project, rel, 3)
    assert [(i.code, i.path) for i in resolved.issues] == [
        ("G10", f"cues[{i}].params.image") for i in range(3)
    ]
    assert len(asked) == 1
