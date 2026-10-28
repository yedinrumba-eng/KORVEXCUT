"""An animated image does not go into the graphics (spec S1.8a step 0, 001.35 point 5; row 12).

Chromium plays an APNG or an animated WebP with its own clock, which breaks "same time, same
picture". `assets.image_data_uri` refuses them with a G09 (a fixed text, no path), reading only the
header: a PNG with an `acTL` chunk before `IDAT`, and a WebP whose `VP8X` has the animation flag or
that has an `ANIM` chunk. Collected from `test_gfx_codes.py` (300-line rule); `project` is
its fixture.
"""

import struct
from typing import Any

import pytest
from PIL import Image

from kcut.gfx import assets
from kcut.issues import exit_code
from kcut.project import Project
from tests.unit.gfx_codes_images import _sticker_doc
from tests.unit.gfx_resolve_fakes import errors_of as _errors
from tests.unit.gfx_resolve_fakes import run_resolve, write_graphics, write_manifest

__all__ = [
    "test_gfx_codes_animated_image_a_png_with_actl_is_g09",
    "test_gfx_codes_animated_image_a_still_png_is_not_g09",
    "test_gfx_codes_animated_image_a_still_webp_is_not_g09",
    "test_gfx_codes_animated_image_a_webp_with_frames_is_g09",
    "test_gfx_codes_animated_image_other_formats_are_not_looked_at",
    "test_gfx_codes_animated_image_the_check_runs_before_pillow_decodes",
    "test_gfx_codes_animated_image_the_header_rules_of_a_png",
    "test_gfx_codes_animated_image_the_header_rules_of_a_webp",
]
TEXT = "la imagen está animada; los gráficos usan imágenes fijas"


def _frames() -> tuple[Image.Image, Image.Image]:
    return (
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)),
        Image.new("RGBA", (8, 8), (0, 0, 255, 255)),
    )


def _save(project: Project, name: str, animated: bool, image_format: str) -> str:
    """`recursos/<name>` approved in the manifest: one frame, or two with `save_all`."""
    rel = f"recursos/{name}"
    first, second = _frames()
    path = project.root / rel
    if animated:
        first.save(
            path, format=image_format, save_all=True, append_images=[second], duration=100, loop=0
        )
    else:
        first.save(path, format=image_format)
    write_manifest(project, rel)
    return rel


def _chunk(kind: bytes, payload: bytes) -> bytes:
    """A PNG chunk: length, type, data and a CRC that nobody checks here (a zero)."""
    return struct.pack(">I", len(payload)) + kind + payload + b"\0\0\0\0"


PNG = b"\x89PNG\r\n\x1a\n"


def _riff(*chunks: bytes) -> bytes:
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _webp_chunk(kind: bytes, payload: bytes) -> bytes:
    return kind + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) % 2 else b"")


def test_gfx_codes_animated_image_a_png_with_actl_is_g09(project: Project) -> None:
    """An APNG of two frames, approved: G09 with the fixed text, exit 1, nothing in the page."""
    rel = _save(project, "anim.png", True, "PNG")
    assert b"acTL" in (project.root / rel).read_bytes()  # Pillow did make an APNG
    write_graphics(project, _sticker_doc(rel))
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G09", "cues[0].params.image")]
    assert resolved.issues[0].message_es == TEXT == assets.ANIMATED_IMAGE
    assert "anim.png" not in resolved.issues[0].message_es and resolved.images == {}
    assert exit_code(resolved.issues) == 1


def test_gfx_codes_animated_image_a_still_png_is_not_g09(project: Project) -> None:
    """The same image without `acTL`: no G09, and it goes into the page."""
    rel = _save(project, "fija.png", False, "PNG")
    assert b"acTL" not in (project.root / rel).read_bytes()
    write_graphics(project, _sticker_doc(rel))
    resolved = run_resolve(project)
    assert resolved.issues == [] and rel in resolved.images


def test_gfx_codes_animated_image_a_webp_with_frames_is_g09(project: Project) -> None:
    rel = _save(project, "anim.webp", True, "WEBP")
    data = (project.root / rel).read_bytes()
    assert data[12:16] == b"VP8X" and data[20] & 0x02 and b"ANIM" in data  # a real animated WebP
    write_graphics(project, _sticker_doc(rel))
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G09", "cues[0].params.image")]
    assert resolved.issues[0].message_es == TEXT and resolved.images == {}
    assert exit_code(resolved.issues) == 1


def test_gfx_codes_animated_image_a_still_webp_is_not_g09(project: Project) -> None:
    rel = _save(project, "fija.webp", False, "WEBP")
    write_graphics(project, _sticker_doc(rel))
    resolved = run_resolve(project)
    assert resolved.issues == [] and rel in resolved.images


def test_gfx_codes_animated_image_the_header_rules_of_a_png() -> None:
    """Only a chunk `acTL` before the first `IDAT` counts, wherever it is among the first chunks."""
    ihdr = _chunk(b"IHDR", b"\0" * 13)
    actl = _chunk(b"acTL", struct.pack(">II", 2, 0))
    idat = _chunk(b"IDAT", b"\x78\x9c")
    iend = _chunk(b"IEND", b"")
    srgb = _chunk(b"sRGB", b"\0")
    animated = {
        "right after IHDR": PNG + ihdr + actl + idat + iend,
        "after other chunks": PNG + ihdr + srgb + srgb + actl + idat + iend,
        "with no IDAT at all": PNG + ihdr + actl,
    }
    for what, data in animated.items():
        assert assets._is_animated(data, "PNG"), what
    still = {
        "plain": PNG + ihdr + srgb + idat + iend,
        "acTL after IDAT": PNG + ihdr + idat + actl + iend,
        "acTL after IEND": PNG + ihdr + idat + iend + actl,
        "signature only": PNG,
        "empty": b"",
        "not a PNG": b"GIF89a" + actl,
        "truncated chunk": PNG + struct.pack(">I", 10**9) + b"sRGB",  # claims more than it has
        "a chunk that says it is huge": PNG + ihdr + struct.pack(">I", 2**32 - 1) + b"zzzz" + actl,
    }
    for what, data in still.items():
        assert not assets._is_animated(data, "PNG"), what


def test_gfx_codes_animated_image_the_header_rules_of_a_webp() -> None:
    """`VP8X` with the animation flag (bit 1 of its first byte), or an `ANIM` chunk."""
    flags_anim, flags_alpha = b"\x02" + b"\0" * 9, b"\x10" + b"\0" * 9  # the A bit, the alpha bit
    vp8 = _webp_chunk(b"VP8 ", b"\0" * 11)  # odd length: a pad byte follows it
    anim = _webp_chunk(b"ANIM", b"\0" * 6)
    animated = {
        "the flag": _riff(_webp_chunk(b"VP8X", flags_anim), vp8),
        "the flag and ANIM": _riff(_webp_chunk(b"VP8X", flags_anim), anim, vp8),
        "ANIM without the flag": _riff(_webp_chunk(b"VP8X", flags_alpha), anim, vp8),
        "ANIM after an odd chunk": _riff(
            _webp_chunk(b"VP8X", flags_alpha), _webp_chunk(b"ICCP", b"\0" * 5), anim, vp8
        ),
    }
    for what, data in animated.items():
        assert assets._is_animated(data, "WEBP"), what
    still = {
        "VP8X with alpha only": _riff(_webp_chunk(b"VP8X", flags_alpha), vp8),
        "a plain VP8": _riff(vp8),
        "ANIM after the image data": _riff(vp8, anim),
        "just the header": b"RIFF" + b"\0\0\0\0" + b"WEBP",
        "not a RIFF": b"PNG\0" * 10,
        "empty": b"",
        "truncated chunk": _riff(_webp_chunk(b"VP8X", flags_alpha))[:-3],
    }
    for what, data in still.items():
        assert not assets._is_animated(data, "WEBP"), what


def test_gfx_codes_animated_image_the_check_runs_before_pillow_decodes(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The header is read as bytes: an APNG is refused without `Image.open` being called."""
    rel = _save(project, "anim.png", True, "PNG")
    write_graphics(project, _sticker_doc(rel))
    opened: list[object] = []
    real = Image.open

    def spy(*args: Any, **kwargs: Any) -> Image.Image:
        opened.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(Image, "open", spy)
    assert _errors(run_resolve(project)) == [("G09", "cues[0].params.image")]
    assert opened == []


def test_gfx_codes_animated_image_other_formats_are_not_looked_at(project: Project) -> None:
    """A JPEG has no animation: it goes through as before (its name has `acTL` in it too)."""
    rel = "recursos/acTL.jpg"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(project.root / rel, format="JPEG")
    write_manifest(project, rel)
    write_graphics(project, _sticker_doc(rel))
    resolved = run_resolve(project)
    assert resolved.issues == [] and rel in resolved.images
