"""A `MemoryError` in a step of the mix is exit 3, not exit 10 (spec S1.8b round 1, 001.37 point 5;
row 28). The whole mix is in memory (about 6 GB for an hour of music), so a long video can run out;
`mixer.mix` turns the error into a ProjectError with a fixed text and no partial file is left. The
synthesis of the effects has its own text (row 13 of step 0, `no hay memoria para sintetizar los
efectos`) and keeps it. The steps are patched where `mixer` calls them (`kcut.audio.mixer.<name>`).
"""

from pathlib import Path
from typing import Any

import pytest

from tests.integration.mix_helpers import BUILD, audio_project
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
TEXT = "no hay memoria para mezclar el audio"


def _no_memory(*_args: Any, **_kwargs: Any) -> Any:
    raise MemoryError


@pytest.mark.parametrize("step", ["synth_music", "apply_gain_windows", "write_wav_s16_mono"])
def test_mix_memory_error_in_a_step_of_the_mix_is_exit_3_with_a_fixed_text(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    root = audio_project(view_fresh)
    monkeypatch.setattr(f"kcut.audio.mixer.{step}", _no_memory)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert doc["error"]["message"] == TEXT
    assert not (root / BUILD / "mix.wav").exists()
    assert not list((root / BUILD).glob("*.partial*"))  # nothing is left half done


def test_mix_memory_error_the_gain_windows_of_the_effects_are_a_step_of_the_mix_too(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no music the first call of `apply_gain_windows` is the one of the effects bus."""
    root = audio_project(view_fresh, music=False)
    monkeypatch.setattr("kcut.audio.mixer.apply_gain_windows", _no_memory)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 3 and doc["error"]["message"] == TEXT, (doc, err)
    assert not list((root / BUILD).glob("*.partial*"))


def test_mix_memory_error_the_synthesis_of_the_effects_keeps_its_own_text(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = audio_project(view_fresh)
    monkeypatch.setattr("kcut.audio.mixer.build_sfx_bus", _no_memory)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert doc["error"]["message"] == "no hay memoria para sintetizar los efectos"
