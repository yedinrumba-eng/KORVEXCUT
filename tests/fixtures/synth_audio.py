"""The audio plans of the synthetic project (spec S1.8): `write_sfx_plan` (S1.8a).

The plan goes with the example EDL of S1.5 (345 frames at 30 fps, 552 000 samples at 48 kHz). It is
the example of `edit/sfx.json` of the spec with every time a whole number of frames, so that none
depends on a transcript, plus a kick and a hi-hat that alternate every 8 frames between frame 210
and frame 270. S1.8b adds `write_music_plan` and `write_audio_plans` (the two).
"""

import json
from pathlib import Path
from typing import Any

SFX_SCHEMA = "kcut.sfx/1"
BEAT_FROM, BEAT_TO, BEAT_EVERY = 210, 270, 8  # frames: kick, hat, kick, hat...


def sfx_plan_document() -> dict[str, Any]:
    """`edit/sfx.json` of the synthetic project: five events of the example of the spec (the `pop`
    that the example anchors to a word is at frame 60) and eight beats, 13 in all, and one window
    of +4 dB over the beats."""
    events: list[dict[str, Any]] = [
        {"type": "boom", "at": 0},
        {"type": "whoosh", "at": 30, "dur_f": 14, "align": "center", "seed": 2},
        {"type": "pop", "at": 60, "freq": 700},
        {"type": "riser", "at": 210, "dur_f": 15, "align": "end"},
        {"type": "typing", "at": 285, "dur_f": 25, "gain": 0.85},
    ]
    for i, frame in enumerate(range(BEAT_FROM, BEAT_TO, BEAT_EVERY)):
        events.append({"type": "kick" if i % 2 == 0 else "hat", "at": frame})
    return {
        "schema": SFX_SCHEMA,
        "bus_gain_db": 0.0,
        "events": events,
        "windows": [{"start": BEAT_FROM, "end": BEAT_TO, "gain_db": 4.0}],
    }


def write_sfx_plan(root: Path) -> dict[str, Any]:
    """Write `edit/sfx.json` into the project `root` and return the document."""
    document = sfx_plan_document()
    folder = root / "edit"
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    (folder / "sfx.json").write_text(text, encoding="utf-8", newline="\n")
    return document
