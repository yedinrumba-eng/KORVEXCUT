"""The mix and the render look at the folder again right before they move or delete a partial file
(spec 001.38, point 2; S1.9a row 12).

Between the end of an `ffmpeg` and the `os.replace` that puts its result in place, `.kcut/build/vN`
can be changed for a junction (001.37, point 2 covered the writes; this is the window of the move
and of the delete). `os.replace` followed the junction and moved a file named like the partial out
of somebody else's folder, and `discard_partial` deleted it. The hook below runs right when the
step ends: it moves the real folder away, puts a junction in its place that leads to a folder with
a file called `<name>.<pid>.partial` planted in it, and the run has to stop with exit 3 and leave
that file as it was (same sha256) and its folder with nothing else. Two leads: a folder outside
`.kcut/` and a decoy inside it (`assert_in_cache` lets that one through; only the check of the
folder itself, `assert_own_folder`, stops it).

The second half: `os.replace` that fails with `FileNotFoundError` (any `OSError`, not only
`PermissionError`) is exit 3 and not exit 10.
"""

import hashlib
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.audio import f32write, mixer
from kcut.commands import render as render_command
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.integration.mix_helpers import BUILD, audio_project
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["small", "small_base"]  # the fixtures of the render tests, used by name
pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
Swap = Callable[[], None]
# how each step of the mix ends: the partial file that the step moves, and the hook that fires
# when the step is done (an `ffmpeg` that ended, a wav written, the last block of a raw file)
FFMPEG_STEPS = {
    "voice_chain": "voice_chain.f32",
    "voice_norm": "voice.f32",
    "mix_pre": "mix_pre.f32",
    "mix_norm": "mix.f32",
}
BLOCK_STEPS = {"voice_raw": "voice_raw.f32", "music": "music.f32", "sfx": "sfx.f32"}
WAV_STEP = {"wav": "mix.wav"}
MIX_STEPS = {**FFMPEG_STEPS, **BLOCK_STEPS, **WAV_STEP}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _after_ffmpeg(monkeypatch: pytest.MonkeyPatch, partial_prefix: str, swap: Swap) -> list[int]:
    """`swap()` once, right after the `ffmpeg` that writes `<partial_prefix>...` returns."""
    real = proc.run
    done: list[int] = []

    def run(args: list[str], **kwargs: Any) -> Any:
        result = real(args, **kwargs)
        if not done and Path(str(args[-1])).name.startswith(partial_prefix):
            done.append(1)
            swap()
        return result

    monkeypatch.setattr(proc, "run", run)
    return done


def _after_blocks(
    monkeypatch: pytest.MonkeyPatch, folder: Path, name: str, swap: Swap
) -> list[int]:
    """`swap()` once, when the last block of `<name>` has been written to its partial file and
    before `os.replace` moves it (the partial exists then: it is how the file is told apart)."""
    real = f32write._made
    done: list[int] = []

    def made(blocks: Any) -> Iterator[Any]:
        yield from real(blocks)
        if not done and (folder / f"{name}.{os.getpid()}.partial").exists():
            done.append(1)
            swap()

    monkeypatch.setattr(f32write, "_made", made)
    return done


def _after_wav(monkeypatch: pytest.MonkeyPatch, swap: Swap) -> list[int]:
    real = mixer.write_wav_s16_mono
    done: list[int] = []

    def written(*args: Any, **kwargs: Any) -> None:
        real(*args, **kwargs)
        done.append(1)
        swap()

    monkeypatch.setattr(mixer, "write_wav_s16_mono", written)
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


def _leads(root: Path, tmp_path: Path, leads_to: str, planted: str) -> tuple[Path, str]:
    """The folder the junction will lead to, with the file planted in it, and its sha256."""
    lead = tmp_path / "ajeno" if leads_to == "outside" else root / ".kcut" / "senuelo"
    lead.mkdir()
    (lead / planted).write_bytes(b"this belongs to somebody else")
    return lead, _sha(lead / planted)


def _untouched(lead: Path, planted: str, digest: str) -> None:
    assert [p.name for p in lead.iterdir()] == [planted]  # nothing moved in, nothing went out
    assert _sha(lead / planted) == digest


@pytest.mark.parametrize("leads_to", ["outside", "decoy"])
@pytest.mark.parametrize("step", list(MIX_STEPS))
def test_replace_guard_mix_a_folder_changed_after_the_step_is_exit_3_and_moves_nothing(
    view_fresh: Path,
    kcut_json: Run,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    step: str,
    leads_to: str,
) -> None:
    root = audio_project(view_fresh)
    folder, name = root / BUILD, MIX_STEPS[step]
    planted = f"{name}.{os.getpid()}.partial"
    lead, digest = _leads(root, tmp_path, leads_to, planted)

    def swap() -> None:
        _junction(folder, lead)

    if step in FFMPEG_STEPS:
        done = _after_ffmpeg(monkeypatch, f"{name}.", swap)
    elif step in BLOCK_STEPS:
        done = _after_blocks(monkeypatch, folder, name, swap)
    else:
        done = _after_wav(monkeypatch, swap)
    try:
        code, doc, err = kcut_json("mix", *project_args(root))
    finally:
        _restore(folder)
    assert done == [1]  # the junction went in where the test meant
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    _untouched(lead, planted, digest)


RENDER_STEPS = {
    "picture": "video.partial.mp4",
    "voice": "voice_raw.f32",
    "mux": "render.partial.mp4",
}


@pytest.mark.parametrize("leads_to", ["outside", "decoy"])
@pytest.mark.parametrize("step", list(RENDER_STEPS))
def test_replace_guard_render_a_folder_changed_after_the_step_is_exit_3_and_moves_nothing(
    small: Path,
    kcut_json: Run,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    step: str,
    leads_to: str,
) -> None:
    folder = small / BUILD
    partial_name = RENDER_STEPS[step]
    planted = f"{partial_name}.{os.getpid()}.partial" if step == "voice" else partial_name
    lead, digest = _leads(small, tmp_path, leads_to, planted)

    def swap() -> None:
        _junction(folder, lead)

    if step == "picture":
        real = render_command.compose_video
        done: list[int] = []

        def composed(*args: Any, **kwargs: Any) -> Any:
            result = real(*args, **kwargs)
            done.append(1)
            swap()
            return result

        monkeypatch.setattr(render_command, "compose_video", composed)
    elif step == "voice":
        done = _after_blocks(monkeypatch, folder, partial_name, swap)
    else:
        done = _after_ffmpeg(monkeypatch, "render.partial", swap)
    try:
        code, doc, err = kcut_json("render", "--no-graphics", *project_args(small))
    finally:
        _restore(folder)
    assert done == [1]
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    _untouched(lead, planted, digest)


def _replace_fails_for(monkeypatch: pytest.MonkeyPatch, name: str) -> list[int]:
    """`os.replace` onto a file called `name` fails with `FileNotFoundError`, as if the partial
    had been taken away; any other move goes through."""
    real = os.replace
    hit: list[int] = []

    def replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
        if Path(dst).name == name:
            hit.append(1)
            raise FileNotFoundError()
        real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)
    return hit


@pytest.mark.parametrize(
    "name", ["voice_chain.f32", "voice.f32", "mix_pre.f32", "mix.f32", "mix.wav"]
)
def test_replace_guard_mix_a_move_that_fails_with_file_not_found_is_exit_3_not_10(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = audio_project(view_fresh)
    hit = _replace_fails_for(monkeypatch, name)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert hit == [1]
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert doc["error"]["message"] == "no pude mover el archivo (FileNotFoundError)"
    assert not list((root / BUILD).glob("*.partial*"))


@pytest.mark.parametrize("name", ["video.mp4", "render.mp4"])
def test_replace_guard_render_a_move_that_fails_with_file_not_found_is_exit_3_not_10(
    small: Path,
    kcut_json: Run,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    hit = _replace_fails_for(monkeypatch, name)
    code, doc, err = kcut_json("render", "--no-graphics", *project_args(small))
    assert hit == [1]
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert doc["error"]["message"] == "no pude mover el archivo (FileNotFoundError)"
    assert not list((small / BUILD).glob("*.partial*"))
