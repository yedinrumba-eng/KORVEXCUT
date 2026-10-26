"""The example EDL of the spec (S1.5) written into a synthetic project, with its real `qhash`es.

`write_edl_v1(root)` needs a project that went through `kcut ingest` with the media of
`synth_media` (a1 and a2 are the cameras, b1 the screen): it reads their `qhash` from the
inventory and writes `edit/edl-v1.json` and an approved `edit/estrategia.md`.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kcut.ingest.inventory import load_inventory

FRAMES = 345


@dataclass(frozen=True)
class EdlTruth:
    """What the EDL puts on the output, in the units the render tests assert on."""

    frames: int = FRAMES
    flash_out_f: tuple[int, int] = (60, 150)
    beep_out_s: tuple[float, float] = (2.0, 5.0)


def edl_v1_document(qhashes: dict[str, str]) -> dict[str, Any]:
    """The example EDL as a dict; `qhashes` are the real ones of a1, a2 and b1."""
    return {
        "schema": "kcut.edl/1",
        "version": 1,
        "fps": 30,
        "output": {"w": 1080, "h": 1920},
        "frames": FRAMES,
        "look": "neutro",
        "sources": {clip_id: {"qhash": qhash} for clip_id, qhash in qhashes.items()},
        "clips": [
            {"kind": "gap", "at_f": 0, "dur_f": 30, "why": "gancho sobre color"},
            {"kind": "voice", "at_f": 30, "src": "a1", "in_f": 60, "out_f": 240, "why": "frase 1"},
            {"kind": "gap", "at_f": 210, "dur_f": 60, "why": "inserto de pantalla"},
            {
                "kind": "voice",
                "at_f": 270,
                "src": "a1",
                "in_f": 300,
                "out_f": 345,
                "why": "frase 2",
            },
            {"kind": "gap", "at_f": 315, "dur_f": 30, "why": "cierre"},
        ],
        "spans": [
            {"kind": "color", "at_f": 0, "dur_f": 30, "color": "#0B0B0E"},
            {
                "kind": "cam",
                "at_f": 30,
                "dur_f": 60,
                "src": "a1",
                "zoom": 1.3,
                "cx": 0.5,
                "cy": 0.5,
                "anchor": "top",
            },
            {"kind": "cam", "at_f": 90, "dur_f": 90, "src": "a2", "zoom": 1.0, "push": 0.05},
            {
                "kind": "cam",
                "at_f": 180,
                "dur_f": 30,
                "src": "a1",
                "zoom": 1.5,
                "cx": 0.4,
                "look": "calido",
            },
            {
                "kind": "screen",
                "at_f": 210,
                "dur_f": 60,
                "src": "b1",
                "src_f": 0,
                "keys": [
                    {"at_f": 0, "crop": [0.5, 0.5, 1.0], "card": [1040, 476]},
                    {"at_f": 30, "crop": [0.7, 0.4, 0.3], "card": [1000, 760]},
                ],
                "remap": [
                    {"at_f": 0, "src_f": 0, "speed": 1.0},
                    {"at_f": 30, "src_f": 90, "speed": 2.0},
                ],
            },
            {"kind": "cam", "at_f": 270, "dur_f": 45, "src": "a1", "look": "cinematico"},
            {"kind": "color", "at_f": 315, "dur_f": 30, "color": "#0B0B0E", "fade_out_f": 10},
        ],
    }


def write_edl_v1(root: Path) -> EdlTruth:
    """Write `edit/edl-v1.json` (with the `qhash` of a1, a2 and b1 from the inventory) and an
    `edit/estrategia.md` with `aprobado: si`."""
    inventory = load_inventory(root / ".kcut" / "inventory.json", root)
    qhashes: dict[str, str] = {}
    for clip_id in ("a1", "a2", "b1"):
        clip = inventory.by_id(clip_id)
        assert clip is not None, f"el inventario sintético no tiene {clip_id}"
        qhashes[clip_id] = clip.qhash
    edit = root / "edit"
    edit.mkdir(parents=True, exist_ok=True)
    text = json.dumps(edl_v1_document(qhashes), ensure_ascii=False, indent=1) + "\n"
    (edit / "edl-v1.json").write_text(text, encoding="utf-8", newline="\n")
    strategy = "---\nvideo: sintetico\naprobado: si\naprobado_por: pruebas\n---\n# Estrategia\n"
    (edit / "estrategia.md").write_text(strategy, encoding="utf-8", newline="\n")
    return EdlTruth()
