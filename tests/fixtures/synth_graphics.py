"""The graphics of the synthetic project (spec S1.6a): `write_graphics_v1`.

The cues go with the example EDL of S1.5 (345 frames at 30 fps, 1080x1920). Their parameters are
exact and chosen so that each block fits in the strip `y +- 0.1 * H` (+-192 px) with room to spare;
every time is a whole number of frames, so none depends on a transcript or on a Whisper model.
"""

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

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


LOGO = "recursos/logo.png"


def showpiece_cues() -> list[dict[str, Any]]:
    """The four showpiece cues of S1.7 (001.15): `pasos` steps 210-270 (three steps, at 0, 20 and
    40), `mascota` sticker 180-210 with `recursos/logo.png` that flies to (0.3, 0.4) at frame 20,
    `holo` holo_board 270-315 with `HOLA` typed at frame 30, and `mundo` globe 280-315."""
    steps = [
        {"at_f": 0, "label": "PASO 1", "text": "Abre la app"},
        {"at_f": 20, "label": "PASO 2", "text": "Pega el link"},
        {"at_f": 40, "label": "PASO 3", "text": "Dale a publicar"},
    ]
    fly_to = {"x": 0.3, "y": 0.4, "at_f": 20}
    return [
        {
            "id": "pasos",
            "component": "steps",
            "start": 210,
            "end": 270,
            "params": {"items": steps},
        },
        {
            "id": "mascota",
            "component": "sticker",
            "start": 180,
            "end": 210,
            "params": {"image": LOGO, "exit": "fly_to", "fly_to": fly_to},
        },
        {
            "id": "holo",
            "component": "holo_board",
            "start": 270,
            "end": 315,
            "params": {"text": "HOLA", "type_at_f": 30},
        },
        {"id": "mundo", "component": "globe", "start": 280, "end": 315, "params": {}},
    ]


def write_logo(root: Path) -> None:
    """`recursos/logo.png` (a 256 x 256 RGBA circle) and its entry in the manifest of resources,
    approved by `test`: what the sticker of `mascota` draws (the gate of the images, DS9)."""
    folder = root / "recursos"
    folder.mkdir(parents=True, exist_ok=True)
    logo = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(logo)
    draw.ellipse((8, 8, 247, 247), fill=(217, 119, 87, 255))
    draw.ellipse((72, 72, 183, 183), fill=(255, 236, 210, 255))
    logo.save(root / LOGO, format="PNG")
    item = {
        "file": LOGO,
        "kind": "imagen",
        "origin": "propio",
        "license": "propia",
        "obtained": "2026-10-27",
        "approved_by": "test",
    }
    manifest = folder / "recursos.json"
    document = (
        json.loads(manifest.read_text(encoding="utf-8"))
        if manifest.is_file()
        else {"schema": "kcut.recursos/1", "items": []}
    )
    document["items"] = [i for i in document["items"] if i.get("file") != LOGO] + [item]
    manifest.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")


def write_graphics_v1(root: Path, with_showpieces: bool = False) -> dict[str, Any]:
    """Write `edit/graphics.json` into the project `root` and return the document.

    `with_showpieces=True` adds the four cues of `showpiece_cues()` and writes the logo they use
    (`write_logo`, with its approval in the manifest)."""
    document = graphics_v1_document()
    if with_showpieces:
        document["cues"].extend(showpiece_cues())
        write_logo(root)
    (root / "edit").mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    (root / "edit" / "graphics.json").write_text(text, encoding="utf-8", newline="\n")
    return document
