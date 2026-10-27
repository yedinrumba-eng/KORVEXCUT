"""Shared pieces of the EDL unit tests: an inventory of fake clips, a config, and the example EDL.

The inventory has the cameras of the synthetic project (a1 is 1440x2560 and the master of the sync,
a2 is 1080x1920 and starts 1200 ms after it), a camera whose sync was rejected (a3), the screen b1
(no audio), a voice-only clip (s1), a photo and a document.
"""

import copy
from collections.abc import Callable
from typing import Any

from kcut.config.load import parse_config
from kcut.config.model import ProjectConfig
from kcut.config.template import render_template
from kcut.edl.model import Edl
from kcut.edl.parse import parse_edl
from kcut.edl.validate import validate
from kcut.ingest.classify import ClipClass
from kcut.ingest.inventory import (
    Clip,
    ClipAudio,
    ImageMeta,
    Inventory,
    SyncInfo,
    SyncMember,
    SyncRejected,
)
from kcut.issues import Issue
from tests.fixtures.synth_edl import edl_v1_document
from tests.unit.media_fakes import make_video

Doc = dict[str, Any]
AUDIO = ClipAudio("aac", 48000, 1, 0, 1, -3.0, False)
HASHES = {"a1": "sha256:aaaaaaaa", "a2": "sha256:bbbbbbbb", "b1": "sha256:cccccccc"}


def _clip(clip_id: str, clip_class: ClipClass, qhash: str, **fields: Any) -> Clip:
    base: dict[str, Any] = {"duration_ms": 12000, "frames": 360}
    return Clip(
        id=clip_id,
        file=f"crudo/{clip_id}.mp4",
        slug=clip_id,
        clip_class=clip_class,
        qhash=qhash,
        size_bytes=10,
        **{**base, **fields},
    )


def inventory(**sync: Any) -> Inventory:
    """The fake inventory; `sync` replaces fields of its `SyncInfo`."""
    member = SyncMember("a2", 1200, 0.9, 0.3, 3.0, 0, 0, "envelope+raw")
    rejected = SyncRejected("a3", 0.4, 1.2, "sync_low_score")
    clips = (
        _clip("a1", "video_voz", HASHES["a1"], video=make_video(), audio=AUDIO),
        _clip(
            "a2",
            "video_voz",
            HASHES["a2"],
            video=make_video(w=1080, h=1920, display_w=1080, display_h=1920),
            audio=AUDIO,
        ),
        _clip(
            "a3",
            "video_voz",
            "sha256:dddddddd",
            video=make_video(w=1080, h=1920, display_w=1080, display_h=1920),
            audio=AUDIO,
        ),
        _clip(
            "b1",
            "video_mudo",
            HASHES["b1"],
            video=make_video(w=1894, h=866, display_w=1894, display_h=866),
            frames=240,
        ),
        _clip("s1", "audio", "sha256:eeeeeeee", audio=AUDIO),
        _clip("i1", "imagen", "sha256:ffffffff", image=ImageMeta(800, 600, True), frames=None),
        Clip("d1", "crudo/brief.txt", "brief", "doc", "sha256:99999999", 3),
    )
    info = SyncInfo("a1", (member,), (rejected,))
    return Inventory("2026-10-26T10:00:00", 30, clips, SyncInfo(**{**vars(info), **sync}))


def config(preset: str = "9:16", fps: int = 30) -> ProjectConfig:
    text = render_template("prueba", preset, fps, "es", "2026-10-26")
    return parse_config(text, default_name="prueba", source="prueba")


def example_doc() -> Doc:
    """The example EDL of the spec as a fresh dict, with the `qhash`es of `inventory()`."""
    return edl_v1_document(HASHES)


def audio_f() -> dict[str, int]:
    return {"a1": 360, "a2": 360, "a3": 360, "s1": 360}


def edit(change: Callable[[Doc], object]) -> Doc:
    """The example EDL after `change(doc)`."""
    doc = copy.deepcopy(example_doc())
    change(doc)
    return doc


def check(
    doc: Doc | None = None,
    inv: Inventory | None = None,
    audio: dict[str, int] | None = None,
    version: int = 1,
) -> list[Issue]:
    """Parse `doc` (the example if none) and validate it against the fake project."""
    edl = parsed(doc)
    # 001.24 point 9: `{}` is a real answer (no source has a known length), not "use the default"
    known = audio if audio is not None else audio_f()
    return validate(edl, inv or inventory(), config(), version, known)


def parsed(doc: Doc | None = None) -> Edl:
    edl, issues = parse_edl(example_doc() if doc is None else doc)
    assert edl is not None, issues
    return edl


def codes(issues: list[Issue]) -> list[str]:
    return [issue.code for issue in issues]


def only(doc: Doc, wanted: str, **kwargs: Any) -> list[str]:
    """The paths of the issues of code `wanted` that `check(doc, **kwargs)` finds."""
    return [issue.path for issue in check(doc, **kwargs) if issue.code == wanted]
