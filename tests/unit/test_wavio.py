"""wav and raw float32 file I/O."""

import wave
from pathlib import Path

import numpy as np
import pytest

from kcut.audio.wavio import (
    read_f32,
    read_wav_s16_mono,
    wav_peak,
    write_f32,
    write_wav_s16_mono,
)
from kcut.errors import ProjectError


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


class TestF32:
    def test_round_trip_is_exact_and_not_clipped(self, tmp_path: Path) -> None:
        x = np.array([0.0, 1.5, -2.25, 1e-7], dtype=np.float32)
        write_f32(tmp_path / "v.f32", x)
        assert (tmp_path / "v.f32").stat().st_size == 16
        assert np.array_equal(read_f32(tmp_path / "v.f32"), x)

    def test_little_endian_bytes(self, tmp_path: Path) -> None:
        write_f32(tmp_path / "v.f32", np.array([1.0], dtype=np.float32))
        assert (tmp_path / "v.f32").read_bytes() == bytes.fromhex("0000803f")

    def test_truncated_file(self, tmp_path: Path) -> None:
        (tmp_path / "v.f32").write_bytes(b"123")
        with pytest.raises(ProjectError, match="float32"):
            read_f32(tmp_path / "v.f32")

    def test_result_is_writable(self, tmp_path: Path) -> None:
        write_f32(tmp_path / "v.f32", np.zeros(3, dtype=np.float32))
        y = read_f32(tmp_path / "v.f32")
        y[0] = 1.0
        assert y[0] == 1.0


class TestWavPeak:
    def test_blockwise_peak_equals_the_whole_file_peak(self, tmp_path: Path) -> None:
        rng = np.random.default_rng(5)
        x = (rng.standard_normal(250_000) * 0.2).astype(np.float32)
        x[173_001] = -0.9
        write_wav_s16_mono(tmp_path / "a.wav", x, 16000)
        whole, _ = read_wav_s16_mono(tmp_path / "a.wav")
        assert wav_peak(tmp_path / "a.wav", block_frames=4096) == float(np.max(np.abs(whole)))
        assert wav_peak(tmp_path / "a.wav") == float(np.max(np.abs(whole)))

    def test_the_most_negative_sample_does_not_overflow(self, tmp_path: Path) -> None:
        path = tmp_path / "min.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes((-32768).to_bytes(2, "little", signed=True) * 10)
        assert wav_peak(path) == 1.0

    def test_silence_and_an_empty_file(self, tmp_path: Path) -> None:
        write_wav_s16_mono(tmp_path / "s.wav", np.zeros(100, dtype=np.float32), 8000)
        write_wav_s16_mono(tmp_path / "e.wav", np.zeros(0, dtype=np.float32), 8000)
        assert wav_peak(tmp_path / "s.wav") == 0.0
        assert wav_peak(tmp_path / "e.wav") == 0.0

    def test_it_never_loads_more_than_one_block(self, tmp_path: Path) -> None:
        write_wav_s16_mono(tmp_path / "a.wav", np.full(10_000, 0.5, dtype=np.float32), 8000)
        sizes: list[int] = []
        real_open = wave.open

        class Spy:
            def __init__(self, inner: wave.Wave_read) -> None:
                self.inner = inner

            def __getattr__(self, name: str) -> object:
                return getattr(self.inner, name)

            def __enter__(self) -> "Spy":
                return self

            def __exit__(self, *_: object) -> None:
                self.inner.close()

            def readframes(self, n: int) -> bytes:
                data = self.inner.readframes(n)
                sizes.append(len(data))
                return data

        def spy_open(path: str, mode: str = "rb") -> Spy:
            return Spy(real_open(path, mode))  # type: ignore[arg-type]

        wave.open = spy_open  # type: ignore[assignment]
        try:
            wav_peak(tmp_path / "a.wav", block_frames=1000)
        finally:
            wave.open = real_open
        assert max(sizes) <= 2000
        assert len(sizes) >= 10

    def test_stereo_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "st.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(bytes(16))
        with pytest.raises(ProjectError, match="mono"):
            wav_peak(path)
