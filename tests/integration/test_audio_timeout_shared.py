"""Every `ffmpeg` on audio gets the timeout of `audio_timeout_s`, and nothing else (spec 001.38,
point 4; S1.9a row 14). A spy on `proc.run` sees each call of a second `kcut mix` (the first one
builds the wav48 of the voice, which belongs to `ingest` and has its own formula). The two
constants of `loudnorm` are changed for the run: if `mixer` or `music_file` still computed the
time on their own, their calls would keep the old figure and the spy would see it.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut import proc
from kcut.audio import loudnorm
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


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, float | None]]:
    """Every call to `proc.run`: the program and the `timeout_s` it was given."""
    seen: list[tuple[str, float | None]] = []
    real = proc.run

    def run(args: list[str], **kwargs: Any) -> Any:
        seen.append((Path(str(args[0])).stem, kwargs.get("timeout_s")))
        return real(args, **kwargs)

    monkeypatch.setattr(proc, "run", run)
    return seen


def _own_figures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not the figures of the spec: so a copy of the formula somewhere else would not match."""
    monkeypatch.setattr(loudnorm, "_TIMEOUT_PER_AUDIO_S", 3.0)
    monkeypatch.setattr(loudnorm, "_TIMEOUT_FLOOR_S", 7.0)


def test_audio_timeout_shared_the_synthetic_music_mix_uses_the_one_formula(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = audio_project(view_fresh)
    code, doc, err = kcut_json("mix", *project_args(root))  # builds the wav48
    assert code == 0, (doc, err)
    _own_figures(monkeypatch)
    seen = _spy(monkeypatch)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0, (doc, err)
    assert audio_timeout_s(SECONDS) == 3.0 * SECONDS + 7.0  # the patched figures are the ones used
    assert len(seen) >= 8 and {tool for tool, _ in seen} == {"ffmpeg"}
    assert {timeout for _, timeout in seen} == {audio_timeout_s(SECONDS)}, seen


def test_audio_timeout_shared_the_decoding_of_a_song_is_one_second_longer(
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
    code, doc, err = kcut_json("mix", *project_args(root))  # builds the wav48
    assert code == 0 and doc["music"] == "file", (doc, err)
    _own_figures(monkeypatch)
    seen = _spy(monkeypatch)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0, (doc, err)
    timeouts = [timeout for _, timeout in seen]
    assert timeouts.count(audio_timeout_s(SECONDS + 1)) == 1  # the decoding of the song
    assert set(timeouts) == {audio_timeout_s(SECONDS), audio_timeout_s(SECONDS + 1)}, seen
