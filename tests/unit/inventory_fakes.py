"""Shared data of the inventory validation tests: a valid inventory and the sync entries."""

from kcut.ingest.inventory import Clip, ClipAudio, Inventory, WorkFiles
from tests.unit.media_fakes import make_video

REJECTED = {
    "id": "s2",
    "score": 0.9,
    "ratio": 4.0,
    "refine_corr": 0.85,
    "reason": "sync_ambiguous: x",
    "lag_a_ms": -2800,
    "lag_b_ms": 4000,
}
MEMBER = {
    "id": "a2",
    "offset_ms": 1200,
    "score": 0.9,
    "second": 0.3,
    "ratio": 3.0,
    "refine_corr": 0.99,
    "drift_ms": 0,
    "drift_windows": 0,
    "method": "envelope+raw",
}
HOSTILE_TEXT = [
    "\x1b]0;pwned\x07",
    "\x1b[2J",
    "a\rb",
    "a\u2028b",
    "a\u202eb",
    "a\u200bb",
    "x" * 301,
]


def valid_inventory() -> Inventory:
    clip = Clip(
        "a1",
        "crudo/cam a.mp4",
        "cam-a",
        "video_voz",
        "sha256:aaaaaaaa",
        10,
        12000,
        360,
        make_video(),
        ClipAudio("aac", 44100, 1, 0, 1, -3.0, False),
        None,
        WorkFiles(".kcut/proxy/a1_cam-a.mp4", ".kcut/wav16/a1_cam-a.wav", 540, 960),
        (),
    )
    doc = Clip("d1", "crudo/brief.txt", "brief", "doc", "sha256:bbbbbbbb", 3)
    return Inventory("2026-10-16T10:00:00", 30, (clip, doc), id_high={"a": 1, "d": 1})
