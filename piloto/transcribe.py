"""Pilot (throwaway): word-level transcription with faster-whisper, timed."""
import json
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel

PROMPT = (
    "Eh, este, o sea, mmm, bueno, pues, ok, mira, entonces, ¿verdad? "
    "Higgsfield, Claude, prompt, Kling, Veo, IA, inteligencia artificial."
)

out_dir = Path(sys.argv[1])
files = sys.argv[2:]
t0 = time.perf_counter()
model = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=8)
print(f"model_load_s={time.perf_counter() - t0:.1f}", flush=True)
for f in files:
    t1 = time.perf_counter()
    segs, info = model.transcribe(
        f,
        language="es",
        word_timestamps=True,
        initial_prompt=PROMPT,
        vad_filter=False,
        condition_on_previous_text=False,
        beam_size=5,
    )
    words, segments = [], []
    for s in segs:
        segments.append({"start": s.start, "end": s.end, "text": s.text.strip()})
        for w in s.words or []:
            words.append({"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 3)})
    dt = time.perf_counter() - t1
    stem = Path(f).stem
    (out_dir / f"{stem}.json").write_text(
        json.dumps({"file": f, "duration": info.duration, "elapsed_s": dt, "segments": segments, "words": words}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"{stem}: audio={info.duration:.1f}s elapsed={dt:.1f}s rtf={dt / info.duration:.2f} words={len(words)}", flush=True)
