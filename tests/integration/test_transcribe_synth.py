"""`kcut transcribe` and `kcut pack` on one synthetic voice, with the real model.

The voice is flite's `slt` saying "hello world this is a test", delayed 1 s, 6 s long, no tones.
`slt` is the first of slt, rms, awb, kal16 and kal (spec 001.11, point 2) with which Whisper
`medium` writes "hello" and "world" literally; with `kal16` and `kal` it writes "well" for "world".
Skipped (cleanly) when ffmpeg, the flite filter or the local `medium` model are missing.
"""

import json
import subprocess
from pathlib import Path

import pytest

from kcut import proc
from kcut.project import open_project
from kcut.text.normalize import norm_token
from kcut.transcribe.cache import load_transcript
from tests.conftest import run_kcut

pytestmark = [pytest.mark.ffmpeg, pytest.mark.flite, pytest.mark.whisper, pytest.mark.slow]

VOICE = "slt"
# Measured on this audio with kcut's own energy analysis: the voice starts at 1.25 s (flite's
# 0.25 s of lead-in plus the 1 s delay) and runs on until 1.98 s without a pause between the two
# words, so "world" starts about 0.4 s after "hello" (an estimate, hence the wide tolerance).
HELLO_MS = 1250
WORLD_MS = 1650
TOLERANCE_MS = 400


def _speech(dst: Path) -> None:
    args = [
        str(proc.tool_path("ffmpeg")),
        *("-hide_banner", "-nostdin", "-loglevel", "error", "-y"),
        *("-f", "lavfi", "-i", f"flite=text='hello world this is a test':voice={VOICE}"),
        *("-af", "adelay=1000,apad", "-t", "6", "-ar", "16000", "-ac", "1"),
        str(dst),
    ]
    subprocess.run(args, check=True, capture_output=True)


def test_transcribe_synth_voice_gets_its_language_and_times_then_hits_the_cache(
    tmp_path: Path,
) -> None:
    root = tmp_path / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    _speech(root / "crudo" / "voz.wav")
    assert run_kcut("ingest", "--project", str(root), "--no-proxy").returncode == 0

    first = run_kcut("transcribe", "--project", str(root), "--json")
    assert first.returncode == 0, first.stderr
    clip = json.loads(first.stdout)["clips"][0]
    assert (clip["id"], clip["cached"], clip["language"]) == ("s1", False, "en")
    assert clip["words"] >= 5 and clip["language_p"] > 0.5

    transcript = load_transcript(open_project(str(root)), "s1")
    assert transcript is not None and transcript.duration_ms == 6000
    words = transcript.words
    by_text = {norm_token(w.text): w for w in words}
    assert {"hello", "world"} <= by_text.keys(), words  # both written literally
    assert abs(by_text["hello"].s_ms - HELLO_MS) <= TOLERANCE_MS, words
    assert abs(by_text["world"].s_ms - WORLD_MS) <= TOLERANCE_MS, words
    assert by_text["hello"].s_ms < by_text["world"].s_ms
    assert all(0 <= w.s_ms < w.e_ms <= 6000 for w in words)

    second = run_kcut("transcribe", "--project", str(root), "--json")
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["clips"][0]["cached"] is True

    packed = run_kcut("pack", "--project", str(root))
    assert packed.returncode == 0, packed.stderr
    md = (root / "edit" / "transcripcion.md").read_text(encoding="utf-8")
    assert "## s1 - `crudo/voz.wav` - 6.00 s - idioma en (" in md
    tsv = (root / "edit" / "palabras.tsv").read_text(encoding="utf-8").splitlines()
    assert len(tsv) == 1 + len(words) and all(row.split("\t")[1] == "s1" for row in tsv[1:])
    assert md.count("\n[f") >= 1
