"""G09 and the size of a WebP (spec S1.6b step 0, 001.30 point 3; row 15): the width and the height
are read from the RIFF header (`VP8 `, `VP8L` or `VP8X`), in the first 30 bytes, before Pillow opens
the image, because Pillow reserves the whole canvas when it opens a WebP: a file of 32 bytes that
says 16384 x 16384 asked for 2 GB of memory.

Collected from `test_gfx_codes.py`, which is at the 300-line limit; `project` is its fixture.
"""

from typing import Any

import pytest
from PIL import Image

from kcut.gfx import assets
from kcut.project import Project
from tests.unit.gfx_codes_images import _saved, _sticker_doc
from tests.unit.gfx_resolve_fakes import (
    errors_of as _errors,
)
from tests.unit.gfx_resolve_fakes import run_resolve, write_graphics, write_manifest

__all__ = [
    "test_gfx_codes_webp_header_a_header_that_is_none_of_the_three_is_g09_without_opening",
    "test_gfx_codes_webp_header_a_real_webp_of_64_by_64_is_not_g09",
    "test_gfx_codes_webp_header_huge_declared_sizes_are_g09_and_pillow_is_never_called",
    "test_gfx_codes_webp_header_the_limit_is_the_one_of_the_other_formats",
    "test_gfx_codes_webp_header_the_size_is_read_from_the_first_30_bytes",
]
RIFF = b"RIFF" + (24).to_bytes(4, "little") + b"WEBP"


def _lossy(w: int, h: int) -> bytes:
    """32 bytes: a `VP8 ` chunk whose frame header says `w` x `h` (14 bits each: at most 16383)."""
    frame = b"\x10\x02\x00" + b"\x9d\x01\x2a" + w.to_bytes(2, "little") + h.to_bytes(2, "little")
    return RIFF + b"VP8 " + (10).to_bytes(4, "little") + frame + b"\x00\x00"


def _lossless(w: int, h: int) -> bytes:
    """32 bytes: a `VP8L` chunk that says `w` x `h` (kept as `w - 1` and `h - 1`, 14 bits each)."""
    bits = (w - 1) | ((h - 1) << 14)
    head = b"\x2f" + bits.to_bytes(4, "little")
    return RIFF + b"VP8L" + (5).to_bytes(4, "little") + head + b"\x00" * 7


def _extended(w: int, h: int) -> bytes:
    """32 bytes: a `VP8X` chunk with a canvas of `w` x `h` (stored as `w - 1` and `h - 1`)."""
    canvas = (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little")
    return RIFF + b"VP8X" + (10).to_bytes(4, "little") + b"\x00" * 4 + canvas + b"\x00\x00"


def _spy_open(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """A list that counts the calls to `Image.open` (the real function still runs)."""
    opened: list[dict[str, Any]] = []
    real = Image.open

    def spy(*args: Any, **kwargs: Any) -> Image.Image:
        opened.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(Image, "open", spy)
    return opened


def _planted(project: Project, name: str, data: bytes) -> str:
    rel = f"recursos/{name}"
    (project.root / rel).write_bytes(data)
    write_manifest(project, rel)
    write_graphics(project, _sticker_doc(rel))
    return rel


@pytest.mark.parametrize(
    ("data", "pixels"),
    [
        (_lossy(64, 48), 64 * 48),
        (_lossy(16383, 16383), 16383 * 16383),
        (_lossless(64, 48), 64 * 48),
        (_lossless(16384, 16384), 16384 * 16384),
        (_extended(64, 48), 64 * 48),
        (_extended(16384, 16384), 16384 * 16384),
        (_extended(100000, 3), 300000),
    ],
    ids=["lossy", "lossy-max", "lossless", "lossless-max", "extended", "extended-max", "wide"],
)
def test_gfx_codes_webp_header_the_size_is_read_from_the_first_30_bytes(
    data: bytes, pixels: int
) -> None:
    assert len(data) == 32
    assert assets._webp_pixels(data) == pixels
    assert assets._webp_pixels(data[: assets.WEBP_HEADER_BYTES]) == pixels


@pytest.mark.parametrize(
    ("data", "pixels"),
    [
        (_lossy(4096, 4096), 4096 * 4096),
        (_lossless(4096, 4096), 4096 * 4096),
        (_extended(4096, 4096), 4096 * 4096),
        (_lossless(4097, 4096), 4097 * 4096),
    ],
    ids=["lossy", "lossless", "extended", "lossless-one-over"],
)
def test_gfx_codes_webp_header_the_limit_is_the_one_of_the_other_formats(
    data: bytes, pixels: int
) -> None:
    """4096 x 4096 is the limit, as for PNG and JPEG: the header of 4096 x 4096 is not refused
    for its size (the fake file is refused later, by Pillow, for being a fake)."""
    declared = assets._webp_pixels(data)
    assert declared == pixels and (declared > assets.MAX_ASSET_PIXELS) == (pixels > 4096 * 4096)


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("lossy.webp", _lossy(16383, 16383)),
        ("lossless.webp", _lossless(16384, 16384)),
        ("extended.webp", _extended(16384, 16384)),
    ],
    ids=["lossy", "lossless", "extended"],
)
def test_gfx_codes_webp_header_huge_declared_sizes_are_g09_and_pillow_is_never_called(
    project: Project, monkeypatch: pytest.MonkeyPatch, name: str, data: bytes
) -> None:
    """A file of 32 bytes that declares a canvas of hundreds of millions of pixels is G09 with the
    fixed text of the size, and `Image.open` is not called (a spy counts it). The lossy header
    cannot say 16384 (14 bits), so it says 16383, the most it can."""
    _planted(project, name, data)
    opened = _spy_open(monkeypatch)
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G09", "cues[0].params.image")]
    assert resolved.issues[0].message_es == assets.TOO_MANY_PIXELS
    assert name not in resolved.issues[0].message_es and resolved.images == {}
    assert opened == []


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"RIFF",
        _lossy(8, 8)[:29],  # `VP8 ` needs 30 bytes
        _extended(8, 8)[:29],  # `VP8X` needs 30 bytes
        RIFF + b"VP8Z" + b"\x00" * 16,  # a chunk that is none of the three
        RIFF + b"ALPH" + b"\x00" * 16,
        b"RIFX" + RIFF[4:] + b"VP8L" + (5).to_bytes(4, "little") + b"\x2f" + b"\x00" * 10,
        b"RIFF" + (24).to_bytes(4, "little") + b"WAVE" + b"VP8L" + b"\x00" * 16,
        _lossy(8, 8).replace(b"\x9d\x01\x2a", b"\x00\x00\x00"),  # no start code
        _lossless(8, 8).replace(b"\x2f", b"\x00", 1),  # no signature byte
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 24,
    ],
    ids=[
        "empty", "riff-only", "lossy-short", "extended-short", "vp8z", "alph", "rifx", "wave",
        "no-start-code", "no-signature", "png-bytes",
    ],
)  # fmt: skip
def test_gfx_codes_webp_header_a_header_that_is_none_of_the_three_is_g09_without_opening(
    project: Project, monkeypatch: pytest.MonkeyPatch, data: bytes
) -> None:
    _planted(project, "rara.webp", data)
    opened = _spy_open(monkeypatch)
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G09", "cues[0].params.image")]
    assert resolved.issues[0].message_es == assets.BAD_IMAGE and resolved.images == {}
    assert opened == []


@pytest.mark.parametrize(
    ("mode", "options", "kind"),
    [
        ("RGB", {}, b"VP8 "),
        ("RGB", {"lossless": True}, b"VP8L"),
        ("RGBA", {}, b"VP8X"),
    ],
    ids=["lossy", "lossless", "extended"],
)
def test_gfx_codes_webp_header_a_real_webp_of_64_by_64_is_not_g09(
    project: Project,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    options: dict[str, Any],
    kind: bytes,
) -> None:
    """Real files of the three kinds that Pillow writes pass: they are opened, as WEBP only."""
    image = Image.new(mode, (64, 64), (255, 0, 0, 128)[: len(mode)])
    rel = _saved(project, "real.webp", image, "WEBP")  # lossy; RGBA gets an extended header
    if options:
        image.save(project.root / rel, format="WEBP", **options)
    assert (project.root / rel).read_bytes()[12:16] == kind  # the test covers what it says
    assert assets._webp_pixels((project.root / rel).read_bytes()) == 64 * 64
    write_graphics(project, _sticker_doc(rel))
    opened = _spy_open(monkeypatch)
    resolved = run_resolve(project)
    assert resolved.issues == [] and resolved.images[rel].startswith("data:image/webp;base64,")
    assert opened == [{"formats": ["WEBP"]}]
