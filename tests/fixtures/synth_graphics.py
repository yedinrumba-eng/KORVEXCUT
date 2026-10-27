"""The graphics of the synthetic project (spec S1.6a): `write_graphics_v1`.

The cues go with the example EDL of S1.5 (345 frames at 30 fps, 1080x1920). Their parameters are
exact and chosen so that each block fits in the strip `y +- 0.1 * H` (+-192 px) with room to spare;
every time is a whole number of frames, so none depends on a transcript or on a Whisper model.
"""

import json
from pathlib import Path
from typing import Any

SCHEMA = "kcut.graphics/1"


def graphics_v1_document() -> dict[str, Any]:
    """`edit/graphics.json` of the synthetic project: four cues and the subtitles on."""
    return {
        "schema": SCHEMA,
        "captions": {"enabled": True},
        "cues": [
            {
                "id": "gancho",
                "component": "kinetic",
                "start": 0,
                "end": 30,
                "params": {
                    "lines": [
                        {"text": "Esto lo hizo", "at_f": 2, "size": 72, "color": "light"},
                        {"text": "kcut", "at_f": 7, "size": 96, "color": "accent"},
                    ],
                    "y": 0.45,
                },
            },
            {
                "id": "titulo",
                "component": "title",
                "start": 40,
                "end": 80,
                "params": {"text": "Higgsfield", "bar": True, "size": 96, "y": 0.6},
            },
            {
                "id": "pill",
                "component": "label",
                "start": 90,
                "end": 150,
                "params": {"text": "hecho con kcut", "size": 40, "y": 0.58},
            },
            {
                "id": "cierre",
                "component": "endcard",
                "start": 315,
                "end": 345,
                "params": {
                    "lines": [{"text": "Fin", "at_f": 0, "size": 96, "color": "light"}],
                    "cta": "sigueme",
                    "cta_at_f": 4,
                    "y": 0.47,
                },
            },
        ],
    }


def write_graphics_v1(root: Path, with_showpieces: bool = False) -> dict[str, Any]:
    """Write `edit/graphics.json` into the project `root` and return the document.

    `with_showpieces=True` is for the showpiece components of S1.7, which do not exist yet:
    asking for it is a ValueError and not a file without them."""
    if with_showpieces:
        raise ValueError(
            "los componentes de lucimiento (steps, sticker, holo_board, globe) son de S1.7"
        )
    document = graphics_v1_document()
    (root / "edit").mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    (root / "edit" / "graphics.json").write_text(text, encoding="utf-8", newline="\n")
    return document
