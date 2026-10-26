"""`read_wav_range`: a stretch of a wav, read with `setpos` and never more than was asked
(spec 001.15 T7; the header check of 001.14 point 4 comes first)."""

import wave
from pathlib import Path

import numpy as np
import pytest

from kcut.audio.wavio import WavReader, read_wav_range, read_wav_s16_mono, write_wav_s16_mono
from kcut.errors import ProjectError
from tests.unit.wav_fakes import LYING, PCM, SR, chunk, fmt, wav

N = 20_000


def _samples() -> np.ndarray:
    return np.random.default_rng(7).uniform(-0.9, 0.9, N).astype(np.float32)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    target = tmp_path / "proyecto ñandú" / "voz.wav"
    write_wav_s16_mono(target, _samples(), SR)
    return target


class TestSameSamples:
    def test_wav_range_is_the_same_stretch_as_the_whole_read(self, path: Path) -> None:
        whole, rate = read_wav_s16_mono(path)
        part, part_rate = read_wav_range(path, 1000, 500)
        assert part_rate == rate == SR
        assert part.dtype == np.float32 and part.shape == (500,)
        assert np.array_equal(part, whole[1000:1500])

    @pytest.mark.parametrize(("start", "count"), [(0, N), (0, 1), (N - 1, 1), (7, 0), (12_345, 99)])
    def test_wav_range_every_place_of_the_file(self, path: Path, start: int, count: int) -> None:
        whole, _ = read_wav_s16_mono(path)
        part, _ = read_wav_range(path, start, count)
        assert np.array_equal(part, whole[start : start + count])

    def test_wav_range_past_the_end_gives_less(self, path: Path) -> None:
        whole, _ = read_wav_s16_mono(path)
        part, rate = read_wav_range(path, N - 100, 5000)
        assert rate == SR and np.array_equal(part, whole[N - 100 :]) and len(part) == 100

    @pytest.mark.parametrize("start", [N, N + 1, 10**9])
    def test_wav_range_starting_at_or_after_the_end_is_empty(self, path: Path, start: int) -> None:
        part, rate = read_wav_range(path, start, 100)
        assert part.shape == (0,) and part.dtype == np.float32 and rate == SR

    def test_wav_range_values_are_in_minus_one_to_one(self, path: Path) -> None:
        part, _ = read_wav_range(path, 0, N)
        assert part.min() >= -1.0 and part.max() < 1.0


class TestRefusals:
    @pytest.mark.parametrize(("start", "count"), [(-1, 10), (0, -1), (-5, -5)])
    def test_wav_range_negative_arguments_are_a_value_error(
        self, path: Path, start: int, count: int
    ) -> None:
        with pytest.raises(ValueError):
            read_wav_range(path, start, count)

    @pytest.mark.parametrize("name", sorted(LYING))
    def test_wav_range_a_lying_header_is_a_project_error(self, tmp_path: Path, name: str) -> None:
        target = tmp_path / "miente.wav"
        target.write_bytes(LYING[name])
        with pytest.raises(ProjectError):
            read_wav_range(target, 0, 100)

    def test_wav_range_a_wav_that_is_not_mono_16_bit_is_a_project_error(
        self, tmp_path: Path
    ) -> None:
        stereo = tmp_path / "estereo.wav"
        with wave.open(str(stereo), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(SR)
            handle.writeframes(b"\x01\x02\x03\x04" * 100)
        with pytest.raises(ProjectError, match="mono de 16 bits"):
            read_wav_range(stereo, 0, 10)
        eight_bit = tmp_path / "8bit.wav"
        eight_bit.write_bytes(wav([chunk(b"fmt ", fmt(ba=1, bits=8)), chunk(b"data", PCM)]))
        with pytest.raises(ProjectError, match="mono de 16 bits"):
            read_wav_range(eight_bit, 0, 10)

    def test_wav_range_a_file_that_is_not_a_wav_is_a_project_error(self, tmp_path: Path) -> None:
        target = tmp_path / "no.wav"
        target.write_bytes(b"esto no es un wav" * 10)
        with pytest.raises(ProjectError):
            read_wav_range(target, 0, 10)

    def test_wav_range_a_missing_file_is_a_project_error(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectError):
            read_wav_range(tmp_path / "nada.wav", 0, 10)


class TestNeverMoreThanAsked:
    def _spy(self, monkeypatch: pytest.MonkeyPatch) -> tuple[list[int], list[int]]:
        asked: list[int] = []
        sought: list[int] = []
        read, seek = WavReader.readframes, WavReader.setpos

        def spy_read(self: WavReader, count: int) -> bytes:
            asked.append(count)
            return read(self, count)

        def spy_seek(self: WavReader, pos: int) -> None:
            sought.append(pos)
            seek(self, pos)

        monkeypatch.setattr(WavReader, "readframes", spy_read)
        monkeypatch.setattr(WavReader, "setpos", spy_seek)
        return asked, sought

    @pytest.mark.parametrize(
        ("start", "count", "expected"),
        [(0, 10, 10), (100, 10**12, N - 100), (N - 5, 50, 5), (0, N, N)],
    )
    def test_wav_range_readframes_never_gets_more_than_min_count_and_what_is_left(
        self, path: Path, monkeypatch: pytest.MonkeyPatch, start: int, count: int, expected: int
    ) -> None:
        asked, sought = self._spy(monkeypatch)
        read_wav_range(path, start, count)
        assert asked == [expected] and asked[0] <= min(count, N - start)
        assert sought == [start]  # it jumped there with `setpos`, one read, nothing before

    def test_wav_range_nothing_to_read_asks_for_nothing(
        self, path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked, _ = self._spy(monkeypatch)
        read_wav_range(path, N + 10, 100)
        read_wav_range(path, 5, 0)
        assert all(a == 0 for a in asked)

    def test_wav_range_a_huge_count_on_a_big_header_reserves_nothing_extra(
        self, tmp_path: Path
    ) -> None:
        # the header says 2 GiB of data in a 100-byte file: refused before any read is asked
        big = wav(
            [chunk(b"fmt ", fmt()), b"data" + (0x7FFFFFF0).to_bytes(4, "little") + b"\x00" * 64]
        )
        target = tmp_path / "grande.wav"
        target.write_bytes(big)
        with pytest.raises(ProjectError):
            read_wav_range(target, 0, 10**12)
