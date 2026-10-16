"""Pilot (throwaway): build edl-v1.json — frame-snapped output timeline.

Timeline items, in order:
  voice: keep A1 audio [a, b] (A1 source seconds); cams = [(src_t, cam, param), ...]
  gap:   silent insert of `dur` seconds; cams = [(rel_t, cam, param), ...]
cam: a1 | a2 (param = zoom) · ferrari (param = ferrari source t) · screen (param = screen source t)
All boundaries snap to the 1/30 s grid; A1 t=53.000 is mezzanine frame 0.
"""
import json
import math
import sys
from pathlib import Path

FPS = 30
T0 = 53.0

def snap_in(t: float) -> float:
    return math.floor(t * FPS + 1e-6) / FPS

def snap_out(t: float) -> float:
    return math.ceil(t * FPS - 1e-6) / FPS

def snap(t: float) -> float:
    return round(t * FPS) / FPS

ITEMS = [
    {"kind": "gap", "dur": 1.8, "why": "hook: Ferrari made with Higgsfield", "cams": [(0.0, "ferrari", 0.3)]},
    {"kind": "voice", "a": 53.80, "b": 55.95, "why": "te da curiosidad de la IA y no sabes (drop 'entonces')",
     "cams": [(53.80, "a1", 1.30, 0.20)]},
    {"kind": "voice", "a": 56.82, "b": 58.38, "why": "con qué empezar, bueno (0.96 s pause cut)",
     "cams": [(56.82, "a1", 1.55, 0.25)]},
    {"kind": "voice", "a": 59.24, "b": 60.24, "why": "ven, que te voy a enseñar (0.91 s pause cut)",
     "cams": [(59.24, "a2", 1.0)]},
    {"kind": "voice", "a": 60.98, "b": 62.10, "why": "a editar con (cut the 'eeeh' plateau after 'con')",
     "cams": [(60.98, "a1", 1.30, 0.32)]},
    {"kind": "voice", "a": 63.30, "b": 64.45, "why": "Higgsfield (title pop)",
     "cams": [(63.30, "a1", 1.55, 0.30)]},
    {"kind": "voice", "a": 65.55, "b": 66.60, "why": "que tú quieras, en el video de hoy",
     "cams": [(65.55, "a2", 1.0)]},
    {"kind": "voice", "a": 67.36, "b": 70.55, "why": "manejar en un Ferrari, un Lamborghini, vamos a hacerlo por ahí",
     "cams": [(67.36, "a1", 1.30, 0.36), (68.58, "ferrari", 12.0), (69.75, "a1", 1.50, 0.35)]},
    {"kind": "voice", "a": 71.22, "b": 72.42, "why": "mira los datos cómo se ven",
     "cams": [(71.22, "a2", 1.0)]},
    {"kind": "voice", "a": 73.18, "b": 73.60, "why": "enséñale = cue: screen enters on the word (Yedin)",
     "cams": [(73.18, "screen", 0.0)]},
    {"kind": "gap", "dur": 3.8, "why": "Higgsfield screen walkthrough", "cams": [(0.0, "screen", 0.42)]},
    {"kind": "voice", "a": 80.15, "b": 85.52, "why": "por cierto quiero destacar que este video está siendo completamente editado con la IA",
     "cams": [(80.15, "a1", 1.20, 0.40), (82.20, "a2", 1.0)]},
    {"kind": "voice", "a": 86.04, "b": 87.70, "why": "para que tengan esos detalles (0.56 s pause cut)",
     "cams": [(86.04, "a1", 1.15, 0.47)]},
    {"kind": "voice", "a": 88.60, "b": 93.32, "why": "o sea que aquí en la mano te pongo el logo de Claude + 0.6 s hold for logo",
     "cams": [(88.60, "a1", 1.0)]},
    {"kind": "voice", "a": 95.78, "b": 97.33, "why": "ahora te pongo un mundo",
     "cams": [(95.78, "a1", 1.0)]},
    {"kind": "voice", "a": 97.74, "b": 99.68, "why": "completamente motion graphic (0.46 s pause cut)",
     "cams": [(97.74, "a1", 1.18, 0.45)]},
    {"kind": "voice", "a": 101.24, "b": 104.02, "why": "aquí te pongo [hands open 101.9 = holo board] la palabra hola (v2: keep gesture, front cam — Yedin)",
     "cams": [(101.24, "a1", 1.0)]},
    {"kind": "voice", "a": 105.40, "b": 107.36, "why": "y todo eso lo está haciendo la IA completa",
     "cams": [(105.40, "a2", 1.0)]},
    {"kind": "voice", "a": 107.74, "b": 109.56, "why": "y únicamente (0.43 s pause cut)",
     "cams": [(107.74, "a1", 1.20, 0.38)]},
    {"kind": "voice", "a": 110.64, "b": 112.28, "why": "por sí sola (1.15 s pause cut)",
     "cams": [(110.64, "a1", 1.45, 0.35)]},
    {"kind": "voice", "a": 114.10, "b": 115.00, "why": "mañana veremos (breaths cut)",
     "cams": [(114.10, "a1", 1.0)]},
    {"kind": "voice", "a": 115.36, "b": 116.90, "why": "con qué vamos a seguir",
     "cams": [(115.36, "a1", 1.18, 0.45)]},
    {"kind": "voice", "a": 118.68, "b": 120.30, "why": "gracias por sintonía (+ tail)",
     "cams": [(118.68, "a2", 1.0)]},
    {"kind": "gap", "dur": 2.6, "why": "outro: Ferrari + parte 2", "cams": [(0.0, "ferrari", 20.4)]},
]

def f_in(t: float) -> int:
    return math.floor(t * FPS + 1e-6)

def f_out(t: float) -> int:
    return math.ceil(t * FPS - 1e-6)

def f_near(t: float) -> int:
    return round(t * FPS)

def main(out_path: str) -> None:
    """Everything is integer frames; seconds are derived only for display."""
    o = 0
    clips, spans = [], []
    for it in ITEMS:
        if it["kind"] == "voice":
            a, b = f_in(it["a"]), f_out(it["b"])
            clips.append({"kind": "voice", "src_in_f": a, "src_out_f": b, "out_in_f": o, "dur_f": b - a, "why": it["why"]})
            cams = it["cams"]
            for k, (st, cam, p, *rest) in enumerate(cams):
                s0 = a if k == 0 else f_near(st)
                s1 = b if k + 1 == len(cams) else f_near(cams[k + 1][0])
                spans.append({"out_in_f": o + (s0 - a), "dur_f": s1 - s0, "cam": cam, "param": p, "src_in_f": s0,
                              "cx": rest[0] if rest else 0.5})
            o += b - a
        else:
            dur = round(it["dur"] * FPS)
            clips.append({"kind": "gap", "out_in_f": o, "dur_f": dur, "why": it["why"]})
            cams = it["cams"]
            for k, (rt, cam, p) in enumerate(cams):
                r0 = f_near(rt)
                r1 = dur if k + 1 == len(cams) else f_near(cams[k + 1][0])
                spans.append({"out_in_f": o + r0, "dur_f": r1 - r0, "cam": cam, "param": p, "src_in_f": None})
            o += dur
    # A screen insert that continues across items keeps advancing its own source clock.
    merged: list[dict] = []
    for s in spans:
        if merged and merged[-1]["cam"] == s["cam"] == "screen":
            merged[-1]["dur_f"] += s["dur_f"]
        else:
            merged.append(dict(s))
    pos = 0
    for s in merged:
        assert s["out_in_f"] == pos and s["dur_f"] > 0, s
        pos += s["dur_f"]
    assert pos == o
    edl = {"fps": FPS, "t0": T0, "frames": o, "total_s": o / FPS, "clips": clips, "video_spans": merged}
    Path(out_path).write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"total={o / FPS:.3f}s frames={o} clips={len(clips)} spans={len(merged)}")
    for s in merged:
        src = f"{s['src_in_f'] / FPS:7.3f}" if s["src_in_f"] is not None else "   -   "
        print(f"  out {s['out_in_f'] / FPS:7.3f} +{s['dur_f'] / FPS:6.3f}  {s['cam']:<8} p={s['param']:<5} src={src}")

if __name__ == "__main__":
    main(sys.argv[1])
