"""Pilot (throwaway): QA for a rendered version.

usage: qa.py video.mp4 captions.json out_dir
Checks: stream durations/frames, loudness, black/freeze, re-transcription vs expected words, contact sheet.
"""
import difflib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

video, caps_path, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
rep: dict = {}

def run(cmd: list[str]) -> str:
    """ffmpeg reports filters (ebur128, blackdetect) on stderr."""
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stderr

probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                                   "stream=codec_type,codec_name,duration,nb_read_frames,width,height,r_frame_rate,sample_rate,channels",
                                   "-show_entries", "format=duration,size", "-of", "json", video],
                                  capture_output=True, text=True).stdout)
v = next(s for s in probe["streams"] if s["codec_type"] == "video")
a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
rep["video"] = {"codec": v["codec_name"], "size": f"{v['width']}x{v['height']}", "fps": v["r_frame_rate"],
                "frames": int(v["nb_read_frames"]), "dur": float(v["duration"])}
rep["audio"] = {"codec": a["codec_name"], "sr": a["sample_rate"], "ch": a["channels"], "dur": float(a["duration"])}
rep["av_delta_ms"] = round((float(a["duration"]) - float(v["duration"])) * 1000, 1)
rep["file_mb"] = round(int(probe["format"]["size"]) / 1e6, 2)

e = run(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-af", "ebur128=peak=true", "-f", "null", "-"])
summ = e[e.rfind("Summary:"):]
rep["loudness"] = {"I_LUFS": float(re.search(r"I:\s+(-?[\d.]+)", summ).group(1)),
                   "TP_dBFS": float(re.search(r"Peak:\s+(-?[\d.]+)", summ).group(1)),
                   "LRA": float(re.search(r"LRA:\s+(-?[\d.]+)", summ).group(1))}
bd = run(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-vf", "blackdetect=d=0.15:pix_th=0.06,freezedetect=n=0.002:d=0.6",
          "-an", "-f", "null", "-"])
rep["black"] = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", bd)
rep["freeze"] = re.findall(r"freeze_start: ([\d.]+)", bd)

# re-transcribe and diff against expected caption words
wav = out / "qa_audio.wav"
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video, "-ac", "1", "-ar", "16000", str(wav)], check=True)
from faster_whisper import WhisperModel  # noqa: E402

model = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=8)
segs, _ = model.transcribe(str(wav), language="es", word_timestamps=True, condition_on_previous_text=False,
                           initial_prompt="Higgsfield, Claude, IA, Ferrari, Lamborghini, motion graphic.")
heard = [(w.word.strip(), round(w.start, 2)) for s in segs for w in (s.words or [])]

def norm(x: str) -> str:
    x = unicodedata.normalize("NFD", x.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in x if unicodedata.category(c) != "Mn"))

caps = json.loads(Path(caps_path).read_text(encoding="utf-8"))
expected = [norm(w["w"]) for c in caps for w in c["words"]]
got = [norm(w) for w, _ in heard]
expected = [x for x in expected if x]
got = [x for x in got if x]
sm = difflib.SequenceMatcher(a=expected, b=got, autojunk=False)
diffs = []
for op, i1, i2, j1, j2 in sm.get_opcodes():
    if op != "equal":
        diffs.append({"op": op, "expected": " ".join(expected[i1:i2]), "heard": " ".join(got[j1:j2]),
                      "at_s": heard[min(j1, len(heard) - 1)][1] if heard else None})
rep["transcript_match"] = round(sm.ratio(), 3)
rep["transcript_diffs"] = diffs
rep["heard_text"] = " ".join(w for w, _ in heard)

subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video, "-vf",
                "fps=1/2,scale=216:384,drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':text='%{pts\\:hms}':x=4:y=4:fontsize=16:fontcolor=yellow:box=1:boxcolor=black@0.6,tile=13x2",
                "-frames:v", "1", str(out / "contact.jpg")], check=True)
(out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: rep[k] for k in rep if k != "heard_text"}, ensure_ascii=False, indent=1))
