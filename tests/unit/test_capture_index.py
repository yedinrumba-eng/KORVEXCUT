"""The index of the captured graphics, `index.json` (spec S1.6b row 6, 001.15), and which frames a
capture asks for (`active_frames`): the checks of the index one by one, with no Chromium.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from kcut.gfx.captions import Chunk, ChunkWord
from kcut.gfx.capture import active_frames
from kcut.gfx.capture_index import (
    INDEX_NAME,
    index_document,
    load_index,
    page_hash,
    parse_index,
    png_name,
    read_index,
)
from kcut.gfx.resolve import ResolvedGraphics
from kcut.gfx.resolve_cues import ResolvedCue

DIGEST = "ab" * 32
GOOD: dict[str, Any] = {"fps": 30, "frames": [3, 4, 9], "hash": DIGEST}


def _folder(tmp_path: Path, document: object, frames: list[int] | None = None) -> Path:
    """A folder with `index.json` = `document` and a PNG for each of `frames`."""
    (tmp_path / INDEX_NAME).write_text(json.dumps(document), encoding="utf-8")
    for f in [3, 4, 9] if frames is None else frames:
        (tmp_path / png_name(f)).write_bytes(b"png")
    return tmp_path


def test_capture_index_the_names_and_the_document_are_the_ones_of_the_spec() -> None:
    assert png_name(50) == "000050.png" and png_name(123456) == "123456.png"
    assert index_document(30, [0, 1, 2], DIGEST) == {"fps": 30, "frames": [0, 1, 2], "hash": DIGEST}
    assert len(page_hash("<html></html>")) == 64
    assert page_hash("a") == page_hash("a") and page_hash("a") != page_hash("b")


def test_capture_index_a_good_one_is_read() -> None:
    index = parse_index(GOOD)
    assert index is not None
    assert (index.fps, index.frames, index.hash) == (30, (3, 4, 9), DIGEST)
    assert parse_index({"fps": 30, "frames": [], "hash": DIGEST}) is not None  # no frames is fine


@pytest.mark.parametrize(
    ("what", "change"),
    [
        ("frames out of order", lambda d: d.update(frames=[9, 4, 3])),
        ("frames repeated", lambda d: d.update(frames=[3, 3, 4])),
        ("a negative frame", lambda d: d.update(frames=[-1, 3])),
        ("a bool as a frame", lambda d: d.update(frames=[True, 4])),
        ("a float as a frame", lambda d: d.update(frames=[3.0, 4])),
        ("a string as a frame", lambda d: d.update(frames=["3", 4])),
        ("frames that is not a list", lambda d: d.update(frames="3,4")),
        ("a bool as the fps", lambda d: d.update(fps=True)),
        ("a float as the fps", lambda d: d.update(fps=30.0)),
        ("a hash that is not hex", lambda d: d.update(hash="zz" * 32)),
        ("a hash that is short", lambda d: d.update(hash="ab" * 31)),
        ("a hash that is long", lambda d: d.update(hash="ab" * 33)),
        ("a hash that is a number", lambda d: d.update(hash=12345)),
        ("a key more", lambda d: d.update(extra=1)),
        ("no hash", lambda d: d.pop("hash")),
        ("no frames", lambda d: d.pop("frames")),
        ("no fps", lambda d: d.pop("fps")),
    ],
)
def test_capture_index_what_does_not_have_the_shape_is_none(what: str, change: Any) -> None:
    document = copy.deepcopy(GOOD)
    change(document)
    assert parse_index(document) is None, what


@pytest.mark.parametrize("document", [None, [], "index", 5, [{"fps": 30}]])
def test_capture_index_what_is_not_an_object_is_none(document: object) -> None:
    assert parse_index(document) is None


def test_capture_index_hex_in_capitals_is_hex_and_is_compared_in_lowercase() -> None:
    index = parse_index({"fps": 30, "frames": [], "hash": "AB" * 32})
    assert index is not None and index.hash == "ab" * 32


def test_capture_index_read_index_is_none_for_a_file_that_is_missing_broken_or_huge(
    tmp_path: Path,
) -> None:
    assert read_index(tmp_path / INDEX_NAME) is None
    (tmp_path / INDEX_NAME).write_text("{no es json", encoding="utf-8")
    assert read_index(tmp_path / INDEX_NAME) is None
    (tmp_path / INDEX_NAME).write_bytes(b" " * (1024 * 1024 + 1))  # over the 1 MiB of an index
    assert read_index(tmp_path / INDEX_NAME) is None


def test_capture_index_load_index_gives_a_good_one_and_says_it_is_not_damaged(
    tmp_path: Path,
) -> None:
    index, damaged = load_index(_folder(tmp_path, GOOD), 30, 60)
    assert index is not None and index.frames == (3, 4, 9) and damaged is False


def test_capture_index_load_index_without_a_file_is_none_and_not_damaged(tmp_path: Path) -> None:
    assert load_index(tmp_path, 30, 60) == (None, False)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(fps=25),  # the project's fps is 30
        lambda d: d.update(frames=[3, 4, 60]),  # 60 is not a frame of a video of 60 frames
        lambda d: d.update(frames=[3, 4, 9, 61]),
        lambda d: d.update(frames=[9, 4, 3]),
        lambda d: d.update(hash="not hex at all"),
    ],
    ids=["fps", "frame-at-the-end", "frame-after-the-end", "disordered", "hash"],
)
def test_capture_index_load_index_a_file_that_fails_a_check_is_damaged(
    tmp_path: Path, change: Any
) -> None:
    document = copy.deepcopy(GOOD)
    change(document)
    folder = _folder(tmp_path, document, [3, 4, 9, 60, 61])
    assert load_index(folder, 30, 60) == (None, True)


def test_capture_index_load_index_a_png_that_is_missing_or_not_a_file_is_damaged(
    tmp_path: Path,
) -> None:
    folder = _folder(tmp_path, GOOD)
    (folder / png_name(4)).unlink()
    assert load_index(folder, 30, 60) == (None, True)
    (folder / png_name(4)).mkdir()  # a folder where the PNG goes is not a regular file
    assert load_index(folder, 30, 60) == (None, True)


def test_capture_index_gfx_hardlink_a_png_with_two_names_is_damaged(tmp_path: Path) -> None:
    """001.31 point 3: a hard link is a second name of a file that may be outside the project."""
    (tmp_path / "gfx").mkdir()
    folder = _folder(tmp_path / "gfx", GOOD)
    other_name = tmp_path / "ajeno.png"
    os.link(folder / png_name(4), other_name)
    assert os.stat(other_name).st_nlink == 2
    assert load_index(folder, 30, 60) == (None, True)
    other_name.unlink()  # one name again: the same files are good
    index, damaged = load_index(folder, 30, 60)
    assert index is not None and damaged is False


def test_capture_index_gfx_hardlink_an_index_with_two_names_is_damaged(tmp_path: Path) -> None:
    (tmp_path / "gfx").mkdir()
    folder = _folder(tmp_path / "gfx", GOOD)
    os.link(folder / INDEX_NAME, tmp_path / "otro.json")
    assert load_index(folder, 30, 60) == (None, True)


def test_capture_index_gfx_surrogate_the_hash_is_of_the_bytes_that_are_written() -> None:
    """001.31 point 6: `page_hash` encodes with `errors="replace"`, as `write_text_atomic`
    writes, so a lone surrogate is a `?` in both and is not an exception."""
    page = "<p>a \ud800 b</p>"
    assert page_hash(page) == hashlib.sha256(b"<p>a ? b</p>").hexdigest()
    assert page_hash("plain") == hashlib.sha256(b"plain").hexdigest()  # nothing else changes


def test_capture_index_load_index_a_file_that_is_not_json_is_damaged(tmp_path: Path) -> None:
    (tmp_path / INDEX_NAME).write_text("{no es json", encoding="utf-8")
    assert load_index(tmp_path, 30, 60) == (None, True)


def test_capture_index_the_last_frame_of_the_video_is_valid(tmp_path: Path) -> None:
    folder = _folder(tmp_path, {**GOOD, "frames": [58, 59]}, [58, 59])
    index, damaged = load_index(folder, 30, 60)
    assert index is not None and index.frames == (58, 59) and damaged is False


def _resolved(cues: tuple[ResolvedCue, ...], chunks: list[Chunk], frames: int) -> ResolvedGraphics:
    """A `ResolvedGraphics` of just what `active_frames` reads."""
    return ResolvedGraphics(
        version=1, source="file", fps=30, w=1080, h=1920, frames=frames, brand={}, captions=True,
        captions_cfg=None,  # type: ignore[arg-type]  (not read here)
        style={}, cues=cues, chunks=chunks, shown={}, masked=True, images={}, issues=[],
        notices=[], empty=False,
    )  # fmt: skip


def _cue(start: int, end: int) -> ResolvedCue:
    return ResolvedCue("x", "label", start, end, {})


def test_capture_index_active_frames_are_the_union_of_the_cues_and_the_chunks() -> None:
    chunks = [Chunk(8, 12, [ChunkWord("a1:w0001", "HI", 8)]), Chunk(20, 22, [])]
    resolved = _resolved((_cue(0, 3), _cue(2, 5)), chunks, 100)
    assert active_frames(resolved) == [0, 1, 2, 3, 4, 8, 9, 10, 11, 20, 21]


def test_capture_index_active_frames_leave_out_what_is_not_in_the_video() -> None:
    chunks = [Chunk(-3, 2, []), Chunk(8, 14, [])]  # a chunk may start before or end after
    resolved = _resolved((), chunks, 10)
    assert active_frames(resolved) == [0, 1, 8, 9]


def test_capture_index_active_frames_of_nothing_are_none() -> None:
    assert active_frames(_resolved((), [], 100)) == []
