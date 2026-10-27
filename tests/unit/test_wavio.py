"""wav and raw float32 file I/O."""

import struct
import time
import tracemalloc
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut import cli
from kcut.audio.wavio import (
    check_wav_extent,
    read_wav_s16_mono,
    wav_duration_ms,
    wav_peak,
    write_wav_s16_mono,
)
from kcut.commands.pack import _energy
from kcut.errors import ProjectError
from kcut.transcribe.cache import wav16_length_ms
from tests.unit.test_pack_command import _ready
from tests.unit.transcribe_fakes import (
    TRUNCATED_WAV,
    FakeClip,
    build_project,
    riff_bytes,
    tone,
)
from tests.unit.wav_fakes import HONEST, LEFT_TO_WAVE, LYING, mutants
from tests.unit.wav_fakes import outcome as _outcome
from tests.unit.wav_fakes import read_all as _read_all

# The tests of `open_wav` live in `wavio_cases.py` (300-line rule) and are collected here.
from tests.unit.wavio_cases import *  # noqa: F403


class TestWav:
    def test_round_trip_within_one_lsb(self, tmp_path: Path) -> None:
        t = np.arange(16000, dtype=np.float32) / 16000
        x = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        write_wav_s16_mono(tmp_path / "a.wav", x, 16000)
        y, sr = read_wav_s16_mono(tmp_path / "a.wav")
        assert sr == 16000
        assert y.dtype == np.float32
        assert np.max(np.abs(x - y)) < 2 / 32768

    def test_values_are_clipped_to_full_scale(self, tmp_path: Path) -> None:
        write_wav_s16_mono(tmp_path / "a.wav", np.array([2.0, -3.0, 0.0], dtype=np.float32), 8000)
        y, _ = read_wav_s16_mono(tmp_path / "a.wav")
        assert y[0] > 0.999 and y[1] < -0.999 and y[2] == 0.0

    def test_writes_parents(self, tmp_path: Path) -> None:
        write_wav_s16_mono(tmp_path / "x" / "y" / "a.wav", np.zeros(4, dtype=np.float32), 8000)
        assert (tmp_path / "x" / "y" / "a.wav").is_file()

    def test_stereo_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "st.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(bytes(16))
        with pytest.raises(ProjectError, match="mono"):
            read_wav_s16_mono(path)

    def test_24_bit_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "b24.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(3)
            wav.setframerate(8000)
            wav.writeframes(bytes(12))
        with pytest.raises(ProjectError, match="16 bits"):
            read_wav_s16_mono(path)

    def test_not_a_wav(self, tmp_path: Path) -> None:
        (tmp_path / "x.wav").write_bytes(b"no soy un wav")
        with pytest.raises(ProjectError):
            read_wav_s16_mono(tmp_path / "x.wav")

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectError):
            read_wav_s16_mono(tmp_path / "no.wav")


def _wav_file(tmp_path: Path, declared: int, payload: bytes, **kw: bytes) -> Path:
    path = tmp_path / "x.wav"
    path.write_bytes(riff_bytes(declared, payload, **kw))
    return path


READERS = [_read_all, wav_duration_ms, wav_peak, wav16_length_ms]


class TestLyingHeader:
    """001.14 point 4: the data a header declares must fit in the real file."""

    @pytest.mark.parametrize("reader", READERS)
    def test_lying_header_declares_more_than_the_file_has(
        self, tmp_path: Path, reader: Any
    ) -> None:
        path = _wav_file(tmp_path, 0xFFFFFFF0, b"\0" * 100)
        with pytest.raises(ProjectError) as info:
            reader(path)
        # 001.28: the message is the template filled with the label of the file: "el wav" for the
        # readers that are given none, and "el wav16" for `wav16_length_ms` (the old text)
        old_label = "el wav16"
        wanted = (
            TRUNCATED_WAV
            if reader is wav16_length_ms
            else TRUNCATED_WAV.replace(old_label, "el wav")
        )
        assert info.value.message_es == wanted

    @pytest.mark.parametrize("reader", READERS)
    def test_lying_header_one_byte_short(self, tmp_path: Path, reader: Any) -> None:
        with pytest.raises(ProjectError, match="truncado"):
            reader(_wav_file(tmp_path, 102, b"\0" * 101))

    @pytest.mark.parametrize("reader", READERS)
    def test_lying_header_an_odd_data_chunk(self, tmp_path: Path, reader: Any) -> None:
        with pytest.raises(ProjectError, match="truncado"):
            reader(_wav_file(tmp_path, 101, b"\0" * 101))

    @pytest.mark.parametrize("reader", READERS)
    def test_lying_header_an_honest_file_reads(self, tmp_path: Path, reader: Any) -> None:
        assert reader(_wav_file(tmp_path, 3200, b"\x01\x00" * 1600)) is not None

    def test_lying_header_a_chunk_before_data_is_fine_and_one_that_lies_is_not(
        self, tmp_path: Path
    ) -> None:
        extra = b"LIST" + struct.pack("<I", 4) + b"INFO"
        samples, rate = read_wav_s16_mono(_wav_file(tmp_path, 200, b"\x01\x00" * 100, extra=extra))
        assert (len(samples), rate) == (100, 16000)
        with pytest.raises(ProjectError, match="truncado"):
            read_wav_s16_mono(_wav_file(tmp_path, 200, b"\x01\x00" * 99, extra=extra))

    def test_lying_header_the_data_may_be_followed_by_other_chunks(self, tmp_path: Path) -> None:
        tail = b"LIST" + struct.pack("<I", 4) + b"INFO"
        samples, _ = read_wav_s16_mono(_wav_file(tmp_path, 200, b"\x01\x00" * 100 + tail))
        assert len(samples) == 100

    @pytest.mark.parametrize("reader", READERS)
    def test_lying_header_reserves_no_memory_for_what_it_declares(
        self, tmp_path: Path, reader: Any
    ) -> None:
        path = _wav_file(tmp_path, 3 * 1024**3, b"\0" * 64)  # "3 GiB" in a 100-byte file
        tracemalloc.start()
        try:
            with pytest.raises(ProjectError):
                reader(path)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert peak < 5 * 1024 * 1024

    def test_lying_header_a_file_that_is_not_a_wav_or_has_no_data(self, tmp_path: Path) -> None:
        (tmp_path / "a.wav").write_bytes(b"not a wav at all")
        (tmp_path / "b.wav").write_bytes(riff_bytes(0, b"")[:36])  # fmt, no data chunk
        for name in ("a.wav", "b.wav"):
            with pytest.raises(ProjectError):
                read_wav_s16_mono(tmp_path / name)

    def test_lying_header_thousands_of_tiny_chunks_are_refused_fast(self, tmp_path: Path) -> None:
        junk = (b"junk" + struct.pack("<I", 0)) * 20000
        started = time.monotonic()
        with pytest.raises(ProjectError):
            read_wav_s16_mono(_wav_file(tmp_path, 2, b"\0\0", extra=junk))
        assert time.monotonic() - started < 1.0


def _outcomes(data: bytes, tmp_path: Path) -> dict[str, str]:
    path = tmp_path / "x.wav"
    path.write_bytes(data)
    readers = [check_wav_extent, _read_all, wav_duration_ms, wav_peak, wav16_length_ms, _energy]
    return {reader.__name__: _outcome(reader, path) for reader in readers}


class TestLyingHeaderV2:
    """001.16 point 7: the block comes from the `fmt ` (channels x bytes of a sample), every chunk
    has to fit in the file and in what the RIFF header says, and `wave` can fail any way."""

    @pytest.mark.parametrize("case", sorted(LYING))
    def test_lying_header_v2_every_reader_says_project_error(
        self, tmp_path: Path, case: str
    ) -> None:
        outcomes = _outcomes(LYING[case], tmp_path)
        if case in LEFT_TO_WAVE:  # the extent check has nothing to say; `wave` refuses them
            outcomes.pop("check_wav_extent")
        assert set(outcomes.values()) == {"ProjectError"}, (case, outcomes)

    @pytest.mark.parametrize("case", sorted(HONEST))
    def test_lying_header_v2_an_honest_file_reads_in_every_reader(
        self, tmp_path: Path, case: str
    ) -> None:
        assert set(_outcomes(HONEST[case], tmp_path).values()) == {"ok"}, case

    def test_lying_header_v2_a_mutated_header_returns_or_says_project_error(
        self, tmp_path: Path
    ) -> None:
        seen = {o for data in mutants() for o in _outcomes(data, tmp_path).values()}
        assert seen <= {"ok", "ProjectError"}, seen

    @pytest.mark.parametrize("raised", [RuntimeError("cannot seek"), EOFError(), ValueError("x")])
    def test_lying_header_v2_whatever_wave_raises_is_a_project_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raised: Exception
    ) -> None:
        path = tmp_path / "x.wav"
        path.write_bytes(HONEST["plain"])

        def boom(*args: object, **kwargs: object) -> None:
            raise raised

        monkeypatch.setattr(wave, "open", boom)
        for reader in (_read_all, wav_duration_ms, wav_peak, wav16_length_ms, _energy):
            assert _outcome(reader, path) == "ProjectError", reader.__name__

    @pytest.mark.parametrize("command", ["pack", "transcribe"])
    @pytest.mark.parametrize(
        "case", ["block_align_1_odd_data", "riff_one_byte_short", "list_4gb_before_data"]
    )
    def test_lying_header_v2_the_commands_exit_3_never_10(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, case: str
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        (root / ".kcut" / "wav16" / "a1_cam.wav").write_bytes(LYING[case])
        flags = ["--force"] if command == "transcribe" else []
        assert cli.main([command, "--project", str(root), *flags]) == 3

    @pytest.mark.parametrize("case", ["block_align_1_odd_data", "riff_one_byte_short"])
    def test_lying_header_v2_pack_stops_even_if_the_clip_was_never_transcribed(
        self, tmp_path: Path, case: str
    ) -> None:
        root = build_project(tmp_path / "p", [FakeClip("a1", tone(2.0))], master="a1").root
        (root / ".kcut" / "wav16" / "a1_cam.wav").write_bytes(LYING[case])
        assert cli.main(["pack", "--project", str(root)]) == 3
