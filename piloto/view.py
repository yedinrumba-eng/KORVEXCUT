"""Pilot (throwaway): timeline view PNG = RMS envelope + silence bands + word labels.

usage: view.py voice.wav words.json t_offset start end out.png
  voice.wav timeline: file t=0 <=> source time t_offset
"""
import json
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

wav, words_json, t_off, a, b, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
with wave.open(wav, "rb") as w:
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
hop = int(sr * 0.01)
i0, i1 = int((a - t_off) * sr), int((b - t_off) * sr)
seg = x[i0:i1]
n = len(seg) // hop
db = 20 * np.log10(np.sqrt((seg[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
W, H = 2400, 420
img = Image.new("RGB", (W, H), (18, 18, 22))
d = ImageDraw.Draw(img)
font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
def tx(t: float) -> float:
    return (t - a) / (b - a) * W
thr = -42.0
sil = db < thr
# silence bands >= 0.25 s
run = 0
for k in range(n + 1):
    if k < n and sil[k]:
        run += 1
        continue
    if run >= 25:
        x0, x1 = tx(a + (k - run) * 0.01), tx(a + k * 0.01)
        d.rectangle([x0, 40, x1, 300], fill=(60, 20, 20))
        d.text((x0 + 2, 42), f"{run / 100:.2f}s", fill=(255, 120, 120), font=small)
    run = 0
for k in range(n):
    v = max(0.0, (db[k] + 70) / 70)
    xx = tx(a + k * 0.01)
    d.line([xx, 300, xx, 300 - v * 250], fill=(120, 200, 255))
d.line([0, 300 - (thr + 70) / 70 * 250, W, 300 - (thr + 70) / 70 * 250], fill=(255, 80, 80))
t = np.ceil(a * 2) / 2
while t < b:
    d.line([tx(t), 300, tx(t), 310], fill=(200, 200, 200))
    d.text((tx(t) - 14, 312), f"{t:.1f}", fill=(200, 200, 200), font=small)
    t += 0.5
ws = [w for w in json.load(open(words_json, encoding="utf-8"))["words"] if w["e"] > a and w["s"] < b]
for j, w in enumerate(ws):
    y = 335 + (j % 3) * 26
    x0, x1 = tx(w["s"]), tx(w["e"])
    d.rectangle([x0, y, x1, y + 20], outline=(255, 220, 90))
    d.text((x0 + 2, y + 2), w["w"], fill=(255, 230, 140), font=font)
img.save(out)
print(out)
