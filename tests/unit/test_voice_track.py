"""The voice of the cut, sample by sample (spec S1.5b rows 2, 12 and 13, `audio/voice_track.py`).

The wav48 of the source is written by hand: sample `n` is the number `n % 30000 + 1`, so any sample
of the track says which sample of the source it came from. `ensure_wav48` is replaced (no ffmpeg).
"""

import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.audio import voice_track, wavio
from kcut.audio.voice_track import FADE_SAMPLES, build_voice
from kcut.config.template import render_template
from kcut.edl.model import Edl
from kcut.errors import CheckFailed
from kcut.ingest import workfiles
from kcut.project import Project, open_project
from tests.unit.edl_fakes import Doc, edit, inventory, parsed
from tests.unit.voice_stream_cases import *  # noqa: F403  (001.25: 300-line rule)

SPF = 1600  # samples of a frame at 30 fps
SOURCE_FRAMES = 360


def _signal(frames: int, spf: int = SPF) -> NDArray[np.int16]:
    return (np.arange(frames * spf) % 30000 + 1).astype(np.int16)


def _write(path: Path, signal: NDArray[np.int16]) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(48000)
        out.writeframes(signal.astype("<i2").tobytes())


def _project(tmp_path: Path, fps: int = 30) -> Project:
    root = tmp_path / "proyecto ñandú"
    (root / ".kcut").mkdir(parents=True)
    text = render_template("prueba", "9:16", fps, "es", "2026-10-26")
    (root / "kcut.toml").write_text(text, encoding="utf-8")
    return open_project(str(root))


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, Path]:
    """A project whose `ensure_wav48` hands out `wav48.wav`: the signal of 360 frames."""
    project = _project(tmp_path)
    wav = tmp_path / "wav48.wav"
    _write(wav, _signal(SOURCE_FRAMES))
    monkeypatch.setattr(workfiles, "ensure_wav48", lambda *_a, **_k: wav)
    return project, wav


def _voice(project: Project, doc: Doc | None = None) -> NDArray[np.float32]:
    return build_voice(project, parsed(doc), inventory(), None)


def _expected(start: int, count: int) -> NDArray[np.float32]:
    """Samples `[start, start + count)` of the source as floats, as the reader gives them."""
    return (_signal(SOURCE_FRAMES)[start : start + count] / np.float32(32768)).astype(np.float32)


def _voices(*clips: tuple[int, str, int, int]) -> Doc:
    """An EDL of voice clips `(at_f, src, in_f, out_f)`, back to back (the picture is a color)."""
    cursor = 0
    items: list[Doc] = []
    for at_f, src, in_f, out_f in clips:
        assert at_f == cursor
        items.append({"kind": "voice", "at_f": at_f, "src": src, "in_f": in_f, "out_f": out_f,
                      "why": "x"})  # fmt: skip
        cursor += out_f - in_f
    return edit(
        lambda d: d.update(
            frames=cursor,
            clips=items,
            spans=[{"kind": "color", "at_f": 0, "dur_f": cursor, "color": "#000000"}],
        )
    )


class TestLengthAndPlace:
    def test_voice_track_the_length_is_exactly_frames_times_samples_per_frame(
        self, wired: tuple[Project, Path]
    ) -> None:
        track = _voice(wired[0])
        assert track.dtype == np.float32 and track.shape == (345 * 1600,)  # 552000 samples

    @pytest.mark.parametrize(("fps", "spf"), [(24, 2000), (25, 1920), (48, 1000), (60, 800)])
    def test_voice_track_the_length_follows_the_fps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fps: int, spf: int
    ) -> None:
        project = _project(tmp_path, fps)
        wav = tmp_path / "wav48.wav"
        _write(wav, _signal(60, spf))
        monkeypatch.setattr(workfiles, "ensure_wav48", lambda *_a, **_k: wav)
        doc = _voices((0, "a1", 3, 33))
        doc["fps"] = fps
        edl = parsed(doc)
        track = build_voice(project, edl, inventory(), None)
        assert track.shape == (30 * spf,)
        assert np.allclose(track[FADE_SAMPLES : 30 * spf - FADE_SAMPLES],
                           (_signal(60, spf)[3 * spf + FADE_SAMPLES : 33 * spf - FADE_SAMPLES]
                            / np.float32(32768)))  # fmt: skip

    def test_voice_track_a_clip_lands_at_its_frame_and_reads_its_own_samples(
        self, wired: tuple[Project, Path]
    ) -> None:
        track = _voice(wired[0])
        middle = slice(FADE_SAMPLES, 180 * SPF - FADE_SAMPLES)
        first = track[30 * SPF : 210 * SPF]
        assert np.array_equal(first[middle], _expected(60 * SPF, 180 * SPF)[middle])
        second = track[270 * SPF : 315 * SPF]
        inside = slice(FADE_SAMPLES, -FADE_SAMPLES)
        assert np.array_equal(second[inside], _expected(300 * SPF, 45 * SPF)[inside])

    def test_voice_track_the_gaps_are_silence_to_the_sample(
        self, wired: tuple[Project, Path]
    ) -> None:
        track = _voice(wired[0])
        for first, last in ((0, 30), (210, 270), (315, 345)):
            assert not track[first * SPF : last * SPF].any()


class TestFades:
    def test_voice_track_each_edge_has_a_linear_fade_of_240_samples(
        self, wired: tuple[Project, Path]
    ) -> None:
        track = _voice(wired[0])
        clip = track[30 * SPF : 210 * SPF]
        source = _expected(60 * SPF, 180 * SPF)
        ramp = np.linspace(0.0, 1.0, FADE_SAMPLES, dtype=np.float32)
        assert FADE_SAMPLES == 240
        assert np.allclose(clip[:FADE_SAMPLES], source[:FADE_SAMPLES] * ramp)
        assert np.allclose(clip[-FADE_SAMPLES:], source[-FADE_SAMPLES:] * ramp[::-1])
        assert clip[0] == 0.0 and clip[-1] == 0.0
        assert clip[FADE_SAMPLES] == source[FADE_SAMPLES]  # the 241st sample is not touched
        assert clip[-FADE_SAMPLES - 1] == source[-FADE_SAMPLES - 1]

    def test_voice_track_only_the_samples_of_the_fades_are_changed(
        self, wired: tuple[Project, Path]
    ) -> None:
        clip = _voice(wired[0])[270 * SPF : 315 * SPF]
        source = _expected(300 * SPF, 45 * SPF)
        changed = np.flatnonzero(clip != source)
        assert changed.min() == 0 and changed.max() == len(clip) - 1  # both edges are faded
        assert all(n < FADE_SAMPLES or n >= len(clip) - FADE_SAMPLES for n in changed)

    def test_voice_track_two_clips_that_follow_each_other_in_the_source_have_no_fade_between(
        self, wired: tuple[Project, Path]
    ) -> None:
        doc = _voices((0, "a1", 60, 120), (60, "a1", 120, 180))  # 120 is where the first ends
        track = _voice(wired[0], doc)
        joint = 60 * SPF
        around = slice(joint - 2 * FADE_SAMPLES, joint + 2 * FADE_SAMPLES)
        assert np.array_equal(track[around], _expected(60 * SPF + joint - 2 * FADE_SAMPLES,
                                                       4 * FADE_SAMPLES))  # fmt: skip
        assert track[0] == 0.0 and track[-1] == 0.0  # the outer edges still fade

    def test_voice_track_a_jump_in_the_source_fades_both_sides_of_the_cut(
        self, wired: tuple[Project, Path]
    ) -> None:
        doc = _voices((0, "a1", 60, 120), (60, "a1", 130, 190))
        track = _voice(wired[0], doc)
        joint = 60 * SPF
        assert track[joint - 1] == 0.0 and track[joint] == 0.0
        assert track[joint - FADE_SAMPLES - 1] == _expected(120 * SPF - FADE_SAMPLES - 1, 1)[0]

    def test_voice_track_the_same_frame_of_another_clip_is_not_a_continuation(
        self, wired: tuple[Project, Path]
    ) -> None:
        doc = _voices((0, "a1", 60, 120), (60, "a2", 120, 180))
        track = _voice(wired[0], doc)
        assert track[60 * SPF - 1] == 0.0 and track[60 * SPF] == 0.0

    def test_voice_track_a_gap_between_two_clips_of_the_source_keeps_both_fades(
        self, wired: tuple[Project, Path]
    ) -> None:
        def change(d: Doc) -> None:
            d["frames"] = 150
            d["clips"] = [
                {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 60, "out_f": 120, "why": "x"},
                {"kind": "gap", "at_f": 60, "dur_f": 30, "why": "x"},
                {"kind": "voice", "at_f": 90, "src": "a1", "in_f": 120, "out_f": 180, "why": "x"},
            ]
            d["spans"] = [{"kind": "color", "at_f": 0, "dur_f": 150, "color": "#000000"}]

        track = _voice(wired[0], edit(change))
        assert track[60 * SPF - 1] == 0.0 and track[90 * SPF] == 0.0

    def test_voice_track_a_clip_of_one_frame_fades_inside_itself(
        self, wired: tuple[Project, Path]
    ) -> None:
        track = _voice(wired[0], _voices((0, "a1", 100, 101)))
        assert track.shape == (SPF,) and track[0] == 0.0 and track[-1] == 0.0
        assert track[FADE_SAMPLES] == _expected(100 * SPF + FADE_SAMPLES, 1)[0]


class TestFailures:
    def test_voice_track_short_wav_is_a_check_failed_that_names_the_clip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _project(tmp_path)
        wav = tmp_path / "wav48.wav"
        _write(wav, _signal(300))  # 300 frames: the second clip asks for up to 345
        monkeypatch.setattr(workfiles, "ensure_wav48", lambda *_a, **_k: wav)
        with pytest.raises(CheckFailed) as info:
            build_voice(project, parsed(), inventory(), None)
        assert info.value.exit_code == 1
        assert info.value.message_es == (
            f"el wav48 de a1 tiene {300 * SPF} muestras y clips[3] pide hasta {345 * SPF}; "
            "corre kcut ingest o acorta el clip"
        )

    def test_voice_track_short_wav_a_clip_that_ends_exactly_with_the_wav_is_fine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _project(tmp_path)
        wav = tmp_path / "wav48.wav"
        _write(wav, _signal(345))
        monkeypatch.setattr(workfiles, "ensure_wav48", lambda *_a, **_k: wav)
        assert build_voice(project, parsed(), inventory(), None).shape == (345 * SPF,)

    def test_voice_track_short_wav_one_sample_short_is_a_check_failed_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _project(tmp_path)
        wav = tmp_path / "wav48.wav"
        _write(wav, _signal(345)[:-1])
        monkeypatch.setattr(workfiles, "ensure_wav48", lambda *_a, **_k: wav)
        with pytest.raises(CheckFailed, match=f"tiene {345 * SPF - 1} muestras"):
            build_voice(project, parsed(), inventory(), None)

    def test_voice_track_a_wav48_at_another_rate_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _project(tmp_path)
        wav = tmp_path / "wav48.wav"
        with wave.open(str(wav), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(44100)
            out.writeframes(_signal(360).tobytes())
        monkeypatch.setattr(workfiles, "ensure_wav48", lambda *_a, **_k: wav)
        with pytest.raises(Exception, match="44100 Hz"):
            build_voice(project, parsed(), inventory(), None)


class TestUsesRange:
    """Row 13 (T7): each clip reads only its own samples, with `read_wav_range`."""

    def test_voice_track_uses_range_no_full_reader_name_and_the_whole_wav_is_never_read(
        self, wired: tuple[Project, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert not hasattr(voice_track, "read_wav_s16_mono")  # 001.25, row 45
        expected = _voice(wired[0])

        def boom(*_a: Any, **_k: Any) -> None:
            raise AssertionError("read_wav_s16_mono reads the whole wav")

        monkeypatch.setattr(wavio, "read_wav_s16_mono", boom)
        monkeypatch.setattr(voice_track, "read_wav_range", voice_track.read_wav_range)
        assert np.array_equal(_voice(wired[0]), expected)

    def test_voice_track_uses_range_one_call_per_clip_with_its_start_and_count(
        self, wired: tuple[Project, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[int, int]] = []
        real = wavio.read_wav_range

        def spy(path: Path, start: int, count: int, **kw: Any) -> tuple[NDArray[np.float32], int]:
            calls.append((start, count))
            assert kw == {"label": "el wav48 de a1"}  # 001.28: the phrase, never the path
            return real(path, start, count, **kw)

        monkeypatch.setattr(voice_track, "read_wav_range", spy)
        _voice(wired[0])
        assert calls == [(60 * SPF, 180 * SPF), (300 * SPF, 45 * SPF)]

    def test_voice_track_uses_range_a_source_is_prepared_once_however_many_clips_use_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _project(tmp_path)
        wav = tmp_path / "wav48.wav"
        _write(wav, _signal(SOURCE_FRAMES))
        prepared: list[str] = []

        def ensure(_project: Project, clip: Any, _log: Any = None, _n: Any = None) -> Path:
            prepared.append(clip.id)
            return wav

        monkeypatch.setattr(workfiles, "ensure_wav48", ensure)
        doc = _voices((0, "a1", 0, 30), (30, "a1", 60, 90), (60, "a1", 120, 150))
        edl: Edl = parsed(doc)
        build_voice(project, edl, inventory(), None)
        assert prepared == ["a1"]
