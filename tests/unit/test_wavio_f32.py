"""Raw float32 file I/O (the intermediates of the audio chain)."""

from pathlib import Path

import numpy as np
import pytest

from kcut.audio.wavio import read_f32, write_f32
from kcut.errors import ProjectError


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
