"""The music of `mode: file` (spec S1.8b rows 6 and 7, 001.15): a song of `recursos/`, approved in
the manifest, decoded by ffmpeg to raw float32 and laid on the length of the video.

The song of the tests is `recursos/musica/tema.wav`: 2.0 s of 440 Hz made with `write_wav_s16_mono`.
With `loop: true`, `fade_in_f: 15`, `fade_out_f: 36` and 345 frames (552 000 samples) sample
`96000 + k` is sample `k` outside the fades, and the first and the last are 0; without `loop` there
are zeros from sample 96000 and an M06 warning. A song that nobody approved is exit 5 (M04).
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut import proc
from kcut.audio.music_file import load_music_file, music_args
from kcut.audio.music_model import FileCfg
from kcut.audio.wavio import write_wav_s16_mono
from kcut.errors import CheckFailed, GateError, ToolError
from kcut.issues import Issue
from kcut.paths import Layout
from kcut.project import Project
from tests.integration.mix_helpers import BUILD, SAMPLES, SPF, audio_project
from tests.integration.view_frames_helpers import Run, project_args
from tests.unit.edl_fakes import config
from tests.unit.gfx_resolve_fakes import make_project, write_manifest

pytestmark = pytest.mark.ffmpeg
REL = "recursos/musica/tema.wav"
FPS = 30
FADE_IN, FADE_OUT = 15 * SPF, 36 * SPF


def _tone(seconds: float = 2.0) -> NDArray[np.float32]:
    t = np.arange(int(seconds * 48000)) / 48000
    return (0.5 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)


def _song(root: Path, samples: NDArray[np.float32] | None = None, rel: str = REL) -> str:
    """`recursos/musica/tema.wav` (2.0 s of 440 Hz unless `samples` is given), not yet approved."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    write_wav_s16_mono(path, _tone() if samples is None else samples, 48000)
    return rel


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)


def _cfg(**changes: Any) -> FileCfg:
    base: dict[str, Any] = {
        "path": REL, "src_in_f": 0, "loop": False, "fade_in_f": 0, "fade_out_f": 0,
    }  # fmt: skip
    return FileCfg(**(base | changes))


def _load(project: Project, cfg: FileCfg) -> tuple[NDArray[np.float32], list[Issue]]:
    issues: list[Issue] = []
    return load_music_file(project, cfg, SAMPLES, SPF, issues=issues), issues


def test_music_file_with_loop_and_fades_is_552000_samples_and_the_song_repeats(
    project: Project,
) -> None:
    write_manifest(project, _song(project.root))
    cfg = _cfg(loop=True, fade_in_f=15, fade_out_f=36)
    track, issues = _load(project, cfg)
    assert issues == [] and track.dtype == np.float32 and len(track) == SAMPLES == 552000
    low, high = FADE_IN, SAMPLES - FADE_OUT - 96000  # k with k and 96000 + k out of the fades
    assert high > low
    np.testing.assert_allclose(track[96000 + low : 96000 + high], track[low:high], atol=1e-3)
    assert track[0] == 0.0 and track[-1] == 0.0
    assert float(np.abs(track[low : low + 4800]).max()) == pytest.approx(0.5, abs=0.02)


def test_music_file_the_fades_are_linear_ramps(project: Project) -> None:
    write_manifest(project, _song(project.root, np.full(96000, 0.5, dtype=np.float32)))
    track, _ = _load(project, _cfg(loop=True, fade_in_f=15, fade_out_f=36))
    np.testing.assert_allclose(track[:FADE_IN], 0.5 * np.linspace(0, 1, FADE_IN), atol=2e-3)
    np.testing.assert_allclose(track[-FADE_OUT:], 0.5 * np.linspace(1, 0, FADE_OUT), atol=2e-3)
    assert float(track[FADE_IN + 100]) == pytest.approx(0.5, abs=2e-3)


def test_music_file_without_loop_the_rest_is_silence_and_m06_says_so(project: Project) -> None:
    write_manifest(project, _song(project.root))
    track, issues = _load(project, _cfg())
    assert len(track) == SAMPLES and float(np.abs(track[:96000]).max()) > 0.4
    assert not track[96000:].any()  # zeros from the sample 96000 on
    assert [(i.code, i.level, i.path) for i in issues] == [("M06", "warning", "file")]


def test_music_file_a_song_as_long_as_the_video_has_no_warning(project: Project) -> None:
    write_manifest(project, _song(project.root, _tone(12.0)))
    track, issues = _load(project, _cfg())
    assert len(track) == SAMPLES and issues == [] and track[-1000:].any()


def test_music_file_src_in_f_starts_the_song_there(project: Project) -> None:
    ramp = np.linspace(-0.9, 0.9, 96000, dtype=np.float32)  # the sample says where it is
    write_manifest(project, _song(project.root, ramp))
    track, _ = _load(project, _cfg(src_in_f=30))  # 1.0 s into the song
    assert float(track[0]) == pytest.approx(0.0, abs=2e-3)  # the middle of the ramp
    assert float(track[100]) == pytest.approx(ramp[48100], abs=2e-3)
    assert not track[48000:].any()  # one second was left of the song


def test_music_file_the_args_have_ss_and_t_and_bound_what_is_decoded(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_manifest(project, _song(project.root))
    seen: list[list[str]] = []
    real = proc.run

    def spy(args: list[str], **kwargs: Any) -> Any:
        seen.append(list(args))
        return real(args, **kwargs)

    monkeypatch.setattr(proc, "run", spy)
    _load(project, _cfg(src_in_f=15))
    (args,) = seen
    assert args[args.index("-ss") + 1] == "0.5" and args[args.index("-t") + 1] == "12.5"
    assert args.index("-ss") < args.index("-i") and args.index("-t") < args.index("-i")
    assert args[1:5] == ["-hide_banner", "-nostdin", "-loglevel", "error"]
    assert args[-8:] == ["-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"]


def test_music_file_the_exact_command_line_of_the_spec() -> None:
    ffmpeg, song = Path("C:/tools/ffmpeg.exe"), Path("C:/p/recursos/musica/tema.wav")
    assert music_args(ffmpeg, song, 0, 30, 552000) == [
        str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error",
        "-ss", "0", "-t", "12.5", "-protocol_whitelist", "file", "-i", str(song),  # 001.37
        "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-",
    ]  # fmt: skip


def test_music_file_protocols_ffmpeg_opens_the_song_with_the_file_protocol_only(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """001.37, point 8 (row 31): `-protocol_whitelist file` goes right before `-i`, so a song that
    is not a file (a playlist that names an address, a `concat:` of paths) cannot make `ffmpeg`
    open anything else. The decoding the command makes carries it."""
    write_manifest(project, _song(project.root))
    seen: list[list[str]] = []
    real = proc.run

    def spy(args: list[str], **kwargs: Any) -> Any:
        seen.append(list(args))
        return real(args, **kwargs)

    monkeypatch.setattr(proc, "run", spy)
    _load(project, _cfg(src_in_f=15))
    (args,) = seen
    at = args.index("-i")
    assert args[at - 2 : at] == ["-protocol_whitelist", "file"]
    assert args.count("-protocol_whitelist") == 1


def test_music_file_a_song_with_no_audio_from_src_in_f_on_is_a_check_failed(
    project: Project,
) -> None:
    write_manifest(project, _song(project.root))
    with pytest.raises(CheckFailed, match="no tiene audio desde src_in_f") as info:
        _load(project, _cfg(src_in_f=90))  # 3.0 s: the song is 2.0 s long
    assert info.value.exit_code == 1


def test_music_file_a_file_that_is_not_audio_is_a_tool_error_that_does_not_name_it(
    project: Project,
) -> None:
    path = project.root / "recursos" / "musica" / "Maria-809-555-1234.wav"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"this is not audio at all" * 100)
    write_manifest(project, "recursos/musica/Maria-809-555-1234.wav")
    with pytest.raises(ToolError) as info:
        _load(project, _cfg(path="recursos/musica/Maria-809-555-1234.wav"))
    assert info.value.exit_code == 4
    assert "Maria" not in info.value.message_es and "809" not in info.value.message_es


def test_music_file_unapproved_load_raises_the_gate_error(project: Project) -> None:
    _song(project.root)  # the file is there, the manifest does not list it
    with pytest.raises(GateError) as info:
        _load(project, _cfg())
    assert info.value.exit_code == 5 and "tema" not in info.value.message_es
    write_manifest(project, REL, approved_by="")
    with pytest.raises(GateError, match="approved_by"):
        _load(project, _cfg())


def _music_json(root: Path, **file: Any) -> None:
    document = {"schema": "kcut.music/1", "mode": "file", "file": {"path": REL, **file}}
    (root / "edit" / "music.json").write_text(json.dumps(document), encoding="utf-8")


@pytest.mark.slow
def test_music_file_unapproved(view_fresh: Path, kcut_json: Run) -> None:
    """Row 6: `kcut mix` with a song that nobody approved is exit 5, an M04 that says where and
    not what the file is called, and nothing is mixed."""
    root = audio_project(view_fresh, music=False)
    _song(root)
    _music_json(root)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 5 and doc["ok"] is False, (doc, err)
    assert [(e["code"], e["path"]) for e in doc["errors"]] == [("M04", "file.path")]
    assert "tema" not in doc["errors"][0]["message"] and doc["mix"] is None
    assert not (root / BUILD / "mix.wav").exists()


@pytest.mark.slow
def test_music_file_happy_path_through_the_command_and_m06_is_only_a_warning(
    view_fresh: Path, kcut_json: Run
) -> None:
    root = audio_project(view_fresh, music=False)
    write_manifest(_project_of(root), _song(root))
    _music_json(root, loop=True, fade_in_f=15, fade_out_f=36)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0 and doc["music"] == "file" and doc["samples"] == SAMPLES, (doc, err)
    assert doc["warnings"] == []
    _music_json(root)  # no loop: 2 s of song for 11.5 s of video
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0 and [w["code"] for w in doc["warnings"]] == ["M06"], (doc, err)


def _project_of(root: Path) -> Project:
    return Project(root, config(), Layout(root))
