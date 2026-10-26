"""Shared data of the inventory validation tests: a valid inventory and the sync entries."""

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from kcut.ingest.inventory import Clip, ClipAudio, Inventory, WorkFiles, save_inventory
from tests.unit.media_fakes import make_video

Mutation = Callable[[dict[str, Any]], object]

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
    other = Clip("a2", "crudo/cam b.mp4", "cam-b", "video_voz", "sha256:cccccccc", 10)
    voice = Clip("s2", "crudo/voz.wav", "voz", "audio", "sha256:dddddddd", 10)  # MEMBER / REJECTED
    return Inventory(
        "2026-10-16T10:00:00", 30, (clip, doc, other, voice), id_high={"a": 2, "d": 1, "s": 2}
    )


def written(root: Path, mutate: Mutation | None = None) -> Path:
    path = root / ".kcut" / "inventory.json"
    save_inventory(path, valid_inventory())
    if mutate is not None:
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        path.write_text(json.dumps(data), encoding="utf-8")
    return path


def sync_block(
    rejected: Sequence[dict[str, Any]] = (), members: Sequence[dict[str, Any]] = ()
) -> Mutation:
    """Replace the sync block with the given entries, adding the clips it names (the inventory
    only accepts a sync block whose ids are clips it has, spec 001.14 point 9)."""
    block = {"master": "a1", "members": list(members), "rejected": list(rejected)}
    named = [e["id"] for e in (*members, *rejected)]

    def mutate(d: dict[str, Any]) -> None:
        d["sync"] = block
        for clip_id in named:
            if clip_id not in {clip["id"] for clip in d["clips"]}:
                d["clips"].append(_stub_clip(clip_id))
                d["id_high"][clip_id[0]] = max(d["id_high"].get(clip_id[0], 0), int(clip_id[1:]))

    return mutate


def _stub_clip(clip_id: str) -> dict[str, Any]:
    kind = {"a": "video_voz", "s": "audio"}[clip_id[0]]
    return {
        "id": clip_id,
        "file": f"crudo/{clip_id}.bin",
        "slug": clip_id,
        "class": kind,
        "qhash": "sha256:00000000",
        "size_bytes": 1,
    }


def set_clip(**changes: Any) -> Mutation:
    return lambda d: d["clips"][0].update(changes)


def set_work(**changes: Any) -> Mutation:
    return lambda d: d["clips"][0]["work"].update(changes)
