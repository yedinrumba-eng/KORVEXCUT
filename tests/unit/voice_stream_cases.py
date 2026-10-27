"""The voice written in blocks (spec S1.5b rows 36 and 54, 001.25 point 5, 001.26 point 6): the
same samples as the whole track in memory, a block of at most 60 s, a flat memory use, a disk that
is asked first and a wav that cannot be read.

Collected from `test_voice_track.py`, which is at the 300-line limit. The wav48 of the source is
written by hand, as there: sample `n` is the number `n % 30000 + 1`, and `ensure_wav48` is replaced.
"""

import re
import shutil
import tracemalloc
import wave
from collections import namedtuple
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.audio import voice_track, wavio
from kcut.audio.voice_track import BLOCK_SAMPLES, build_voice, require_disk_space, write_voice
from kcut.config.template import render_template
from kcut.errors import CheckFailed, ProjectError
from kcut.ingest import workfiles
from kcut.project import Project, open_project
from tests.unit.edl_fakes import Doc, edit, inventory, parsed

__all__ = ["TestVoiceDiskSpace", "TestVoiceReadError", "TestVoiceStreamed", "streamed"]
SPF = 1600


class Streamed(NamedTuple):
    project: Project
    wav: Path


def _signal(frames: int) -> NDArray[np.int16]:
    return (np.arange(frames * SPF) % 30000 + 1).astype(np.int16)


def _write(path: Path, signal: NDArray[np.int16]) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(48000)
        out.writeframes(signal.astype("<i2").tobytes())


def _project(tmp_path: Path) -> Project:
    root = tmp_path / "proyecto ñandú"
    (root / ".kcut").mkdir(parents=True)
    text = render_template("prueba", "9:16", 30, "es", "2026-10-26")
    (root / "kcut.toml").write_text(text, encoding="utf-8")
    return open_project(str(root))


@pytest.fixture
def streamed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Streamed:
    """A project whose `ensure_wav48` hands out the signal of 360 frames."""
    wav = tmp_path / "wav48.wav"
    _write(wav, _signal(360))
    monkeypatch.setattr(workfiles, "ensure_wav48", lambda *_a, **_k: wav)
    return Streamed(_project(tmp_path), wav)


def _long(minutes: int) -> Doc:
    """An EDL of one voice clip of `minutes` minutes, from the start of the source."""
    frames = minutes * 60 * 30
    return edit(
        lambda d: d.update(
            frames=frames,
            clips=[
                {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 0, "out_f": frames, "why": "x"}
            ],
            spans=[{"kind": "color", "at_f": 0, "dur_f": frames, "color": "#000000"}],
        )
    )


class TestVoiceStreamed:
    """`write_voice` gives the bytes of `build_voice`, one block at a time."""

    def test_voice_streamed_the_example_has_the_same_bytes_as_build_voice(
        self, streamed: Streamed, tmp_path: Path
    ) -> None:
        edl = parsed()
        dst = tmp_path / "voice_raw.f32"
        write_voice(streamed.project, edl, inventory(), dst, None)
        whole = build_voice(streamed.project, edl, inventory(), None)
        assert dst.read_bytes() == whole.astype("<f4").tobytes()
        assert dst.stat().st_size == 345 * SPF * 4

    @pytest.mark.parametrize("block", [100, 240, 777, 1600, 4801, 100_000])
    def test_voice_streamed_a_clip_that_crosses_blocks_is_read_and_faded_the_same(
        self, streamed: Streamed, tmp_path: Path, block: int
    ) -> None:
        """The fades (240 samples) and the joins between clips fall inside and across blocks."""
        doc = edit(
            lambda d: d.update(
                frames=150,
                clips=[
                    {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 60, "out_f": 120, "why": "x"},
                    {
                        "kind": "voice",
                        "at_f": 60,
                        "src": "a1",
                        "in_f": 120,
                        "out_f": 150,
                        "why": "x",
                    },
                    {"kind": "gap", "at_f": 90, "dur_f": 20, "why": "x"},
                    {
                        "kind": "voice",
                        "at_f": 110,
                        "src": "a1",
                        "in_f": 200,
                        "out_f": 240,
                        "why": "x",
                    },
                ],
                spans=[{"kind": "color", "at_f": 0, "dur_f": 150, "color": "#000000"}],
            )
        )
        edl = parsed(doc)
        dst = tmp_path / "voice_raw.f32"
        write_voice(streamed.project, edl, inventory(), dst, None, block_samples=block)
        whole = build_voice(streamed.project, edl, inventory(), None)
        assert dst.read_bytes() == whole.astype("<f4").tobytes()

    def test_voice_streamed_a_block_is_never_longer_than_sixty_seconds(
        self, streamed: Streamed
    ) -> None:
        assert BLOCK_SAMPLES == 60 * 48000
        frames = 130 * 30  # 130 s: a voice clip of 10 s and a gap
        doc = edit(
            lambda d: d.update(
                frames=frames,
                clips=[
                    {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 0, "out_f": 300, "why": "x"},
                    {"kind": "gap", "at_f": 300, "dur_f": frames - 300, "why": "x"},
                ],
                spans=[{"kind": "color", "at_f": 0, "dur_f": frames, "color": "#000000"}],
            )
        )
        blocks = voice_track.voice_blocks(streamed.project, parsed(doc), inventory(), None)
        sizes = [len(block) for block in blocks]
        assert sizes == [BLOCK_SAMPLES, BLOCK_SAMPLES, 130 * 48000 - 2 * BLOCK_SAMPLES]

    def test_voice_streamed_the_blocks_of_the_example_are_one_of_the_whole_track(
        self, streamed: Streamed
    ) -> None:
        blocks = list(voice_track.voice_blocks(streamed.project, parsed(), inventory(), None))
        assert [len(b) for b in blocks] == [345 * SPF]

    def test_voice_streamed_a_block_size_that_is_not_positive_is_a_bug_of_the_caller(
        self, streamed: Streamed
    ) -> None:
        with pytest.raises(ValueError, match="block_samples"):
            list(voice_track.voice_blocks(streamed.project, parsed(), inventory(), None, 0))

    @pytest.mark.slow
    def test_voice_streamed_ten_minutes_do_not_raise_the_memory_peak_over_100_mb(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """10 min of voice are 115 MB as float32: all at once would be over the limit."""
        wav = tmp_path / "wav48.wav"
        _write(wav, _signal(10 * 60 * 30))
        monkeypatch.setattr(workfiles, "ensure_wav48", lambda *_a, **_k: wav)
        project = _project(tmp_path)
        edl = parsed(_long(10))
        dst = tmp_path / "voice_raw.f32"
        tracemalloc.start()
        try:
            write_voice(project, edl, inventory(), dst, None)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert dst.stat().st_size == 10 * 60 * 30 * SPF * 4
        assert peak < 100 * 1024 * 1024, f"pico de {peak / 2**20:.0f} MB"

    def test_voice_streamed_a_clip_that_the_wav_cannot_fill_is_a_check_failed_and_no_file(
        self, streamed: Streamed, tmp_path: Path
    ) -> None:
        doc = edit(
            lambda d: d.update(
                frames=100,
                clips=[
                    {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 300, "out_f": 400, "why": "x"}
                ],
                spans=[{"kind": "color", "at_f": 0, "dur_f": 100, "color": "#000000"}],
            )
        )
        dst = tmp_path / "voice_raw.f32"
        message = re.escape("el wav48 de a1 tiene 576000 muestras y clips[0] pide hasta 640000")
        with pytest.raises(CheckFailed, match=message):
            write_voice(streamed.project, parsed(doc), inventory(), dst, None)
        assert not dst.exists() and list(tmp_path.glob("*.partial")) == []


class TestVoiceDiskSpace:
    """`require_disk_space`: the voice and 1 GiB must fit; if not, the bytes that are missing."""

    NEEDED = 345 * SPF * 4 + 2**30

    @staticmethod
    def _free(monkeypatch: pytest.MonkeyPatch, free: int) -> None:
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr(shutil, "disk_usage", lambda _p: usage(10**12, 0, free))

    def test_voice_streamed_disk_enough_room_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._free(monkeypatch, self.NEEDED)
        require_disk_space(tmp_path, parsed())

    def test_voice_streamed_disk_one_byte_short_says_how_many_are_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._free(monkeypatch, self.NEEDED - 1)
        with pytest.raises(ProjectError) as info:
            require_disk_space(tmp_path, parsed())
        assert info.value.exit_code == 3
        assert "faltan 1 bytes" in info.value.message_es
        assert str(self.NEEDED) in info.value.message_es

    def test_voice_streamed_disk_a_full_disk_asks_for_the_whole_voice_and_the_gigabyte(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._free(monkeypatch, 0)
        with pytest.raises(ProjectError, match=f"faltan {self.NEEDED} bytes"):
            require_disk_space(tmp_path, parsed())


class TestVoiceReadError:
    """Row 54 (001.26 point 6): what fails while the wav is read is not told as a failed write."""

    @pytest.mark.parametrize("error", [PermissionError, FileNotFoundError, OSError])
    def test_voice_read_error_an_oserror_reading_the_wav_is_exit_3_that_names_the_wav(
        self,
        streamed: Streamed,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        error: type[OSError],
    ) -> None:
        def broken(*_a: object, **_k: object) -> None:
            raise error("wav48 gone")  # no file name in the error: the voice says which wav

        # 001.28: it patched `voice_track.read_wav_range`, which hid that no `OSError` comes out of
        # it; the real reader runs now and `wave.open` is what fails (same assertions as before)
        monkeypatch.setattr(wave, "open", broken)
        dst = tmp_path / "voice_raw.f32"
        dst.write_bytes(b"the old voice")
        with pytest.raises(ProjectError) as info:
            write_voice(streamed.project, parsed(), inventory(), dst, None)
        message = info.value.message_es
        # 001.27: the clip and the class of the error, not the path of the wav (was `... <wav>`)
        assert info.value.exit_code == 3
        assert message == f"no pude leer el wav48 de a1: {error.__name__}"
        assert str(streamed.wav) not in message
        assert "escribir" not in message and "voice_raw.f32" not in message
        assert dst.read_bytes() == b"the old voice"  # the file that was there is kept
        assert list(tmp_path.glob("*.partial")) == []

    def test_voice_read_error_the_wav_that_goes_away_during_the_write_leaves_no_partial(
        self, streamed: Streamed, tmp_path: Path
    ) -> None:
        """Not a replaced function but the real thing: the wav is deleted after the first block."""
        doc = edit(
            lambda d: d.update(
                frames=150,
                clips=[
                    {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 0, "out_f": 150, "why": "x"}
                ],
                spans=[{"kind": "color", "at_f": 0, "dur_f": 150, "color": "#000000"}],
            )
        )
        dst = tmp_path / "voice_raw.f32"
        blocks = voice_track.voice_blocks(
            streamed.project, parsed(doc), inventory(), None, block_samples=SPF * 50
        )

        def going() -> Iterator[NDArray[np.float32]]:
            yield next(blocks)
            streamed.wav.unlink()
            yield from blocks

        with pytest.raises(ProjectError) as info:
            wavio.write_f32_blocks(dst, going())
        assert "no pude leer" in info.value.message_es and "escribir" not in info.value.message_es
        assert not dst.exists() and list(tmp_path.glob("*.partial")) == []
