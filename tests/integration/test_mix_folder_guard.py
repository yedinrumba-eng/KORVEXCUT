"""`kcut mix` looks at `.kcut/build/vN` again before each write (spec S1.8b round 1, 001.37 point 2;
row 25). The mix takes minutes, and the folder can be changed for a junction meanwhile: with
`build/v1` leading out of `.kcut/`, `music.f32` and `sfx.f32` used to land outside (the guard of
`render`, `build_folder`, was only called once at the start). The tests do the swap in process, at
the moment that matters, and the mix has to stop with exit 3 and write nothing through the link:

- the junction leads to a folder outside `.kcut/` (`assert_in_cache` stops it), or
- to a decoy folder inside `.kcut/` (`assert_in_cache` lets it through; only `assert_own_folder`,
  that sees the link itself, stops it).

The hook runs right after the real function of one step returns, so the swap falls between the end
of a step and the write that follows it: before the chain of the voice, after its second pass of
loudnorm, after the synthesis of the music and of the effects, before the graph and the wav. Both
folders have to stay empty, in the two cases.
"""

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.integration.mix_helpers import BUILD, audio_project
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
Match = Callable[[tuple[Any, ...], dict[str, Any]], bool]


def _always(_args: tuple[Any, ...], _kwargs: dict[str, Any]) -> bool:
    return True


def _to_wav_read(_args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
    return bool(kwargs.get("label") == "la mezcla")  # the read of `_to_wav`, not the one of `_fit`


# name: (what is patched, which call of the matching ones, which calls match)
POINTS: dict[str, tuple[str, int, Match]] = {
    "voice_chain": ("kcut.audio.mixer.voice_chain", 1, _always),
    "voice_norm": ("kcut.audio.loudnorm.parse_pass1", 1, _always),
    "music": ("kcut.audio.mixer.synth_music", 1, _always),
    "sfx": ("kcut.audio.mixer.build_sfx_bus", 1, _always),
    "mix_pre": ("kcut.audio.mixer.build_graph", 1, _always),
    "mix_norm": ("kcut.audio.loudnorm.parse_pass1", 2, _always),
    "wav": ("kcut.audio.mixer.read_f32", 1, _to_wav_read),
}


def _arm(monkeypatch: pytest.MonkeyPatch, point: str, swap: Callable[[], None]) -> list[int]:
    """Patch the function of `point` so that, right after the real one returns on the call that
    `POINTS` says, `swap()` runs once. The list gets one item when that happened."""
    target, nth, matches = POINTS[point]
    module_name, name = target.rsplit(".", 1)
    module = importlib.import_module(module_name)
    real = getattr(module, name)
    seen: list[int] = []
    done: list[int] = []

    def hooked(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        if matches(args, kwargs):
            seen.append(1)
            if len(seen) == nth and not done:
                done.append(1)
                swap()
        return result

    monkeypatch.setattr(module, name, hooked)
    return done


def _junction(folder: Path, lead: Path) -> None:
    """Keep `folder` beside it as `<name>-real` and put a junction to `lead` in its place."""
    folder.rename(folder.with_name(f"{folder.name}-real"))
    make_dir_link(folder, lead)


def _restore(folder: Path) -> None:
    remove_dir_link(folder)
    real = folder.with_name(f"{folder.name}-real")
    if real.exists() and not folder.exists():
        real.rename(folder)


@pytest.mark.parametrize("leads_to", ["outside", "decoy"])
@pytest.mark.parametrize("point", list(POINTS))
def test_mix_folder_guard_a_folder_changed_for_a_junction_is_exit_3_and_nothing_goes_through(
    view_fresh: Path,
    kcut_json: Run,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    point: str,
    leads_to: str,
) -> None:
    root = audio_project(view_fresh)
    folder = root / BUILD
    outside, decoy = tmp_path / "ajeno", root / ".kcut" / "senuelo"
    outside.mkdir()
    decoy.mkdir()
    lead = outside if leads_to == "outside" else decoy
    done = _arm(monkeypatch, point, lambda: _junction(folder, lead))
    try:
        code, doc, err = kcut_json("mix", *project_args(root))
    finally:
        _restore(folder)
    assert done == [1]  # the junction went in where the test meant
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert list(outside.iterdir()) == [] and list(decoy.iterdir()) == []  # nothing went through


def test_mix_folder_guard_a_mix_nobody_tampers_with_is_exit_0(
    view_fresh: Path, kcut_json: Run
) -> None:
    root = audio_project(view_fresh)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0 and doc["ok"] is True, (doc, err)
    assert (root / BUILD / "mix.wav").is_file()
