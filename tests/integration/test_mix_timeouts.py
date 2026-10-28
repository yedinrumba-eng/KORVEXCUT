"""Every `ffmpeg` that `kcut mix` runs has a timeout (spec S1.8b round 1, 001.37 point 3; row 26).
The final measurement (`ebur128`, in `commands/mix.py`) had none, and a hung `ffmpeg` kept the lock
`build-vN` taken for ever. The formula is the one of `normalize`: 10 s for each second of audio and
60 s at least (`loudnorm.audio_timeout_s`). A spy on `proc.run` sees every call, with a synthetic
music and with a song from a file (that one has the decoding of the song besides).
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut import proc
from kcut.audio.loudnorm import audio_timeout_s
from kcut.audio.wavio import write_wav_s16_mono
from kcut.paths import Layout
from kcut.project import Project
from tests.integration.mix_helpers import SAMPLES, audio_project
from tests.integration.view_frames_helpers import Run, project_args
from tests.unit.edl_fakes import config
from tests.unit.gfx_resolve_fakes import write_manifest

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
SECONDS = SAMPLES / 48000  # 11.5 s
REL = "recursos/musica/tema.wav"


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Every call to `proc.run`: the name of the program and the keywords it was given."""
    seen: list[dict[str, Any]] = []
    real = proc.run

    def run(args: list[str], **kwargs: Any) -> Any:
        flags = [a for a in ("-af", "-filter_complex") if a in args]
        what = args[args.index(flags[0]) + 1][:12] if flags else "-"  # tells the calls apart
        seen.append({"tool": Path(str(args[0])).stem, "what": what, **kwargs})
        return real(args, **kwargs)

    monkeypatch.setattr(proc, "run", run)
    return seen


def test_mix_timeouts_the_formula_is_ten_seconds_per_second_and_a_floor_of_sixty() -> None:
    assert audio_timeout_s(11.5) == 175.0
    assert audio_timeout_s(0.0) == 60.0 and audio_timeout_s(3600.0) == 36060.0


def test_mix_timeouts_every_ffmpeg_of_the_mix_has_one(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = audio_project(view_fresh)
    seen = _spy(monkeypatch)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0 and doc["ok"] is True, (doc, err)
    # the wav48 that a first mix builds, the chain, 2 passes of loudnorm for the voice, the graph,
    # 2 more for the mix and the 2 measurements
    assert [call["tool"] for call in seen] == ["ffmpeg"] * len(seen) and len(seen) >= 8
    assert all(call.get("timeout_s") is not None for call in seen), seen
    measures = [call for call in seen if call["what"].startswith("ebur128")]
    assert [call["timeout_s"] for call in measures] == [audio_timeout_s(SECONDS)] * 2


def test_mix_timeouts_the_decoding_of_a_song_has_one_too(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = audio_project(view_fresh, music=False)
    song = root / REL
    song.parent.mkdir(parents=True)
    tone = (0.5 * np.sin(2 * np.pi * 440.0 * np.arange(96000) / 48000)).astype(np.float32)
    write_wav_s16_mono(song, tone, 48000)
    write_manifest(Project(root, config(), Layout(root)), REL)
    document = {"schema": "kcut.music/1", "mode": "file", "file": {"path": REL, "loop": True}}
    (root / "edit" / "music.json").write_text(json.dumps(document), encoding="utf-8")
    seen = _spy(monkeypatch)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0 and doc["music"] == "file", (doc, err)
    decoding = [call for call in seen if call["what"] == "-"]  # no filter: it is the song
    assert len(decoding) == 1 and decoding[0]["timeout_s"] == 10 * (SECONDS + 1) + 60
    assert all(call.get("timeout_s") is not None for call in seen), seen
