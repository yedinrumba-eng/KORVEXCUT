"""The audio plans of the synthetic project (spec S1.8): `write_sfx_plan` (S1.8a), and
`write_music_plan` and `write_audio_plans` (S1.8b).

The plan goes with the example EDL of S1.5 (345 frames at 30 fps, 552 000 samples at 48 kHz). It is
the example of `edit/sfx.json` of the spec with every time a whole number of frames, so that none
depends on a transcript, plus a kick and a hi-hat that alternate every 8 frames between frame 210
and frame 270. S1.8b adds `write_music_plan` and `write_audio_plans` (the two), below.
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


MUSIC_SCHEMA = "kcut.music/1"


def music_plan_document() -> dict[str, Any]:
    """`edit/music.json` of the synthetic project: the example of the spec (S1.8b), 120 bpm over
    Am-F-C-G with drums, muted from frame 210 to 270 (where the beats of the SFX are) and for good
    from frame 330, the ducking as written there and a window of +3 dB at the start."""
    return {
        "schema": MUSIC_SCHEMA,
        "mode": "synth",
        "gain_db": -8.0,
        "synth": {
            "bpm": 120,
            "progression": ["Am", "F", "C", "G"],
            "drums": True,
            "mute_drums": [{"start": BEAT_FROM, "end": BEAT_TO}],
            "stop_drums_f": 330,
            "origin_f": 0,
        },
        "file": None,
        "duck": {
            "enabled": True,
            "threshold": 0.03,
            "ratio": 10.0,
            "attack_ms": 15,
            "release_ms": 350,
            "makeup": 1.0,
            "knee": 2.828,
        },
        "windows": [{"start": 0, "end": 30, "gain_db": 3.0}],
    }


def write_music_plan(root: Path) -> dict[str, Any]:
    """Write `edit/music.json` into the project `root` and return the document."""
    document = music_plan_document()
    folder = root / "edit"
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    (folder / "music.json").write_text(text, encoding="utf-8", newline="\n")
    return document


def write_audio_plans(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """`write_sfx_plan` and `write_music_plan`: both files of the audio, `(sfx, music)`."""
    return write_sfx_plan(root), write_music_plan(root)
