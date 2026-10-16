"""Pilot (throwaway): map source words to output time; emit cues.json, captions.json, sfx_plan.json.

usage: cues.py edl.json c1_words.json out_dir
"""
import json
import sys
from pathlib import Path

edl = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
words = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["words"]
out = Path(sys.argv[3])
FPS = edl["fps"]
voice = [c for c in edl["clips"] if c["kind"] == "voice"]

def to_out(t: float) -> float | None:
    for c in voice:
        a, b = c["src_in_f"] / FPS, c["src_out_f"] / FPS
        if a <= t <= b:
            return round(c["out_in_f"] / FPS + (t - a), 3)
    return None

def span(cam: str, k: int = 0) -> dict:
    s = [v for v in edl["video_spans"] if v["cam"] == cam][k]
    return {"t": s["out_in_f"] / FPS, "end": (s["out_in_f"] + s["dur_f"]) / FPS}

KEY = {"higgsfield": 63.46, "ferrari": 68.58, "lambo": 69.10, "editado": 84.27, "logo": 92.01,
       "mundo": 96.97, "hola": 103.09, "porsisola": 110.66, "holo": 101.88}
cues = {k: to_out(v) for k, v in KEY.items()}
cues["hook"] = span("ferrari", 0)
cues["screen"] = span("screen", 0)
cues["outro"] = span("ferrari", 2)
cues["total"] = edl["frames"] / FPS
_hs = next(v for v in edl["video_spans"] if v["src_in_f"] is not None
           and v["src_in_f"] / FPS <= 103.09 < (v["src_in_f"] + v["dur_f"]) / FPS)
cues["holo_end"] = (_hs["out_in_f"] + _hs["dur_f"]) / FPS
assert all(v is not None for v in cues.values()), cues

# ---- captions: corrected words mapped to output time ----
FIX = {"Hicksville,": "Higgsfield,", "Cloud,": "Claude,", "ida": "IA"}
FIX_AT = {59.32: "ven,", 65.82: "quieres", 66.06: "hacer en el video", 119.19: "por su"}  # source-time specific fixes (confirmed by Yedin / angle-2 vote)
caps = []
for w in words:
    if not (53.5 < w["s"] < 120.5):
        continue
    txt = FIX_AT.get(round(w["s"], 2), FIX.get(w["w"], w["w"]))
    s_out = None
    for c in voice:  # clamp a stretched word into the clip that holds its start
        a, b = c["src_in_f"] / FPS, c["src_out_f"] / FPS
        if w["e"] > a + 0.08 and w["s"] < b - 0.05:
            s0 = max(w["s"], a)
            e0 = min(w["e"], b, s0 + 0.9)
            s_out = c["out_in_f"] / FPS + (s0 - a)
            e_out = c["out_in_f"] / FPS + (e0 - a)
            break
    if s_out is None:
        continue
    caps.append({"w": txt, "s": round(s_out, 3), "e": round(max(e_out, s_out + 0.12), 3), "clip": c["out_in_f"]})
# drop words that fall inside a removed region (e.g. the cut 'eeeh') — nothing to do: they never map.

# hide captions while big kinetic text is on screen
hide = [(0, cues["hook"]["end"]), (span("ferrari", 1)["t"] - 0.02, span("ferrari", 1)["end"]), (cues["higgsfield"] - 0.05, cues["higgsfield"] + 1.0),
        (cues["screen"]["t"], cues["screen"]["end"]), (cues["editado"] - 0.1, cues["editado"] + 1.3),
        (cues["holo"] - 0.02, cues["holo_end"]), (cues["porsisola"] - 0.05, cues["porsisola"] + 1.6),
        (cues["outro"]["t"], cues["total"])]

# group into chunks of <= 3 words / <= 18 chars, break on punctuation or > 0.35 s gap
chunks, cur = [], []
for w in caps:
    if any(a <= w["s"] < b for a, b in hide):
        if cur:
            chunks.append(cur)
            cur = []
        continue
    if cur and (cur[-1]["clip"] != w["clip"] or len(cur) >= 3 or sum(len(x["w"]) + 1 for x in cur) + len(w["w"]) > 18
                or w["s"] - cur[-1]["e"] > 0.35
                or (cur[-1]["w"].endswith((",", ".", "?")) and cur[-1]["e"] - cur[0]["s"] >= 0.4)):
        chunks.append(cur)
        cur = []
    cur.append(w)
if cur:
    chunks.append(cur)
captions = [{"s": ch[0]["s"], "e": round(min(ch[-1]["e"] + 0.15, ch[-1]["e"] + 0.3), 3),
             "words": [{"w": x["w"].strip(",.?¿").upper(), "s": x["s"]} for x in ch]} for ch in chunks]
for i in range(len(captions) - 1):  # never overlap the next chunk
    captions[i]["e"] = min(captions[i]["e"], captions[i + 1]["s"])
for c in captions:  # never run into a hidden (big-graphic) window
    for a, b in hide:
        if c["s"] < a < c["e"]:
            c["e"] = round(a, 3)

# ---- SFX plan ----
def W(t: float, dur: float = 0.45, gain: float = 0.45, seed: int = 1) -> dict:
    return {"type": "whoosh", "t": round(t - dur * 0.55, 3), "dur": dur, "gain": gain, "seed": seed}

cut_times = sorted({v["out_in_f"] / FPS for v in edl["video_spans"]})
sfx = [{"type": "boom", "t": 0.0, "gain": 0.75},
       W(cues["hook"]["end"], 0.5, 0.5, 2),
       {"type": "pop", "t": cues["higgsfield"], "freq": 700, "gain": 0.6},
       W(span("ferrari", 1)["t"], 0.4, 0.45, 3), W(span("ferrari", 1)["end"], 0.35, 0.35, 4),
       W(cues["screen"]["t"], 0.6, 0.6, 5),
       {"type": "click", "t": round(cues["screen"]["t"] + 1.5, 3), "gain": 0.7},
       W(cues["screen"]["end"], 0.45, 0.45, 6),
       {"type": "pop", "t": cues["editado"], "freq": 560, "gain": 0.6},
       {"type": "shimmer", "t": cues["logo"], "dur": 1.3, "gain": 0.8},
       W(cues["mundo"], 0.5, 0.4, 7), {"type": "shimmer", "t": cues["mundo"] + 0.1, "dur": 1.0, "gain": 0.5},
       {"type": "powerup", "t": cues["holo"], "gain": 0.7},
       W(cues["holo_end"] - 0.05, 0.35, 0.35, 9),
       {"type": "blip8", "t": cues["logo"], "gain": 0.7},
       {"type": "pop", "t": round(cues["logo"] + 0.24, 3), "freq": 240, "gain": 0.75},
       W(30.733 + 0.22, 0.4, 0.4, 10),
       *[{"type": "key", "t": round(cues["hola"] - 0.36 + 0.12 * i, 3), "seed": i, "gain": 0.6} for i in range(4)],
       {"type": "pop", "t": round(cues["hola"] + 0.03, 3), "freq": 1040, "gain": 0.55},
       {"type": "pop", "t": cues["porsisola"], "freq": 640, "gain": 0.55},
       W(cues["outro"]["t"], 0.55, 0.55, 8), {"type": "boom", "t": cues["outro"]["t"], "gain": 0.6}]

S = cues["screen"]
import math
g0 = math.ceil((S["t"] + 0.35) / 0.25) * 0.25  # snap to the music's 8th-note grid (120 BPM, origin t=0)
if round(g0 / 0.25) % 2:  # start on a beat so kicks land on beats
    g0 += 0.25
k = 0
while g0 + k * 0.25 < S["end"] - 0.05:
    tt = round(g0 + k * 0.25, 3)
    if k % 2 == 0:
        sfx.append({"type": "kick", "t": tt, "gain": 0.9})
    else:
        sfx.append({"type": "hat", "t": tt, "seed": k, "gain": 0.95})
    k += 1
sfx += [{"type": "pad", "t": round(g0, 3), "dur": round(S["end"] - g0 + 0.15, 3), "gain": 0.55},
        {"type": "click", "t": round(S["t"] + 2.55, 3), "gain": 0.7},
        {"type": "typing", "t": round(S["t"] + 2.62, 3), "dur": 0.85, "gain": 0.85},
        {"type": "riser", "t": round(S["t"] + 3.0, 3), "dur": 0.5, "gain": 0.45},
        {"type": "shimmer", "t": round(S["t"] + 3.5, 3), "dur": 0.8, "gain": 0.6}]

# a few extra accents: soft whooshes on angle changes, riser into EDITADO
spans_v = edl["video_spans"]
for prev, nxt in zip(spans_v, spans_v[1:]):
    if {prev["cam"], nxt["cam"]} == {"a1", "a2"}:
        sfx.append(W(nxt["out_in_f"] / FPS, 0.3, 0.22, 20 + nxt["out_in_f"] % 7))
sfx.append({"type": "riser", "t": round(cues["editado"] - 0.5, 3), "dur": 0.5, "gain": 0.4})

(out / "cues.json").write_text(json.dumps(cues, indent=1), encoding="utf-8")
(out / "captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=1), encoding="utf-8")
(out / "sfx_plan.json").write_text(json.dumps(sfx, indent=1), encoding="utf-8")
print(json.dumps(cues))
print(f"caption chunks={len(captions)} words={sum(len(c['words']) for c in captions)} sfx={len(sfx)}")
for c in captions:
    print(f"  {c['s']:6.2f}-{c['e']:6.2f} " + " ".join(w["w"] for w in c["words"]))
