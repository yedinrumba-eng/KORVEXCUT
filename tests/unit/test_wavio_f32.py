"""Raw float32 file I/O (the intermediates of the audio chain)."""

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut.audio.wavio import read_f32, write_f32, write_f32_blocks
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


class TestWriteInPlaceNever:
    """001.25 point 3 (row 34): the file is written to `<name>.<pid>.partial` and moved over the
    final name, so a hard link at the final name is replaced and the file it pointed to is kept."""

    def test_f32_partial_a_hard_link_is_replaced_not_written_through(self, tmp_path: Path) -> None:
        crudo = tmp_path / "crudo.mp4"
        crudo.write_bytes(b"the footage")
        target = tmp_path / "voice_raw.f32"
        os.link(crudo, target)
        write_f32(target, np.array([1.0, 2.0], dtype=np.float32))
        assert crudo.read_bytes() == b"the footage"
        assert target.read_bytes() == np.array([1.0, 2.0], dtype="<f4").tobytes()
        assert target.stat().st_nlink == 1

    def test_f32_partial_the_blocks_are_written_in_order_and_no_partial_is_left(
        self, tmp_path: Path
    ) -> None:
        blocks = [np.full(3, n, dtype=np.float32) for n in (1, 2, 3)]
        write_f32_blocks(tmp_path / "v.f32", iter(blocks))
        assert np.array_equal(read_f32(tmp_path / "v.f32"), np.repeat([1.0, 2.0, 3.0], 3))
        assert sorted(p.name for p in tmp_path.iterdir()) == ["v.f32"]

    def test_f32_partial_the_name_of_the_partial_carries_the_pid(self, tmp_path: Path) -> None:
        seen: list[str] = []

        def blocks() -> Iterator[np.ndarray[Any, Any]]:
            seen.extend(p.name for p in tmp_path.iterdir())
            yield np.zeros(2, dtype=np.float32)

        write_f32_blocks(tmp_path / "v.f32", blocks())
        assert seen == [f"v.f32.{os.getpid()}.partial"]

    def test_f32_partial_a_failure_in_the_middle_leaves_the_old_file_and_no_partial(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "v.f32"
        write_f32(target, np.array([7.0], dtype=np.float32))

        def blocks() -> Iterator[np.ndarray[Any, Any]]:
            yield np.zeros(4, dtype=np.float32)
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            write_f32_blocks(target, blocks())
        assert np.array_equal(read_f32(target), np.array([7.0], dtype=np.float32))
        assert sorted(p.name for p in tmp_path.iterdir()) == ["v.f32"]

    def test_f32_partial_render_dest_dir_a_folder_at_the_file_or_at_the_partial_is_exit_3(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "voice_raw.f32").mkdir()
        with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo"):
            write_f32(tmp_path / "voice_raw.f32", np.zeros(1, dtype=np.float32))
        (tmp_path / f"other.f32.{os.getpid()}.partial").mkdir()
        with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo"):
            write_f32(tmp_path / "other.f32", np.zeros(1, dtype=np.float32))

    def test_f32_partial_a_stale_partial_of_the_same_pid_is_not_written_through(
        self, tmp_path: Path
    ) -> None:
        crudo = tmp_path / "crudo.mp4"
        crudo.write_bytes(b"the footage")
        os.link(crudo, tmp_path / f"v.f32.{os.getpid()}.partial")
        write_f32(tmp_path / "v.f32", np.zeros(2, dtype=np.float32))
        assert crudo.read_bytes() == b"the footage"


class TestReadErrorIsNotAWriteError:
    """Row 54 (001.26 point 6): an `OSError` that makes a block (it read a wav) says it could not
    read, not that it could not write the file; the partial is never left."""

    def test_voice_read_error_an_oserror_from_the_blocks_names_the_file_it_could_not_read(
        self, tmp_path: Path
    ) -> None:
        wav = tmp_path / "a1_clip.wav"
        target = tmp_path / "voice_raw.f32"
        write_f32(target, np.array([7.0], dtype=np.float32))

        def blocks() -> Iterator[np.ndarray[Any, Any]]:
            yield np.zeros(4, dtype=np.float32)
            raise FileNotFoundError(2, "No such file or directory", str(wav))

        with pytest.raises(ProjectError) as info:
            write_f32_blocks(target, blocks())
        message = info.value.message_es
        assert info.value.exit_code == 3 and message.startswith(f"no pude leer {wav}")
        assert "escribir" not in message
        assert np.array_equal(read_f32(target), np.array([7.0], dtype=np.float32))
        assert sorted(p.name for p in tmp_path.iterdir()) == ["voice_raw.f32"]

    def test_voice_read_error_an_oserror_with_no_file_name_is_still_about_reading(
        self, tmp_path: Path
    ) -> None:
        def blocks() -> Iterator[np.ndarray[Any, Any]]:
            raise PermissionError("denied")
            yield np.zeros(1, dtype=np.float32)  # unreachable: it makes this a generator

        with pytest.raises(ProjectError, match="no pude leer lo que iba a escribir"):
            write_f32_blocks(tmp_path / "v.f32", blocks())
        assert list(tmp_path.iterdir()) == []

    def test_voice_read_error_a_project_error_from_the_blocks_goes_through_as_it_is(
        self, tmp_path: Path
    ) -> None:
        def blocks() -> Iterator[np.ndarray[Any, Any]]:
            raise ProjectError("el wav está dañado")
            yield np.zeros(1, dtype=np.float32)  # unreachable: it makes this a generator

        with pytest.raises(ProjectError, match=re.escape("el wav está dañado")):
            write_f32_blocks(tmp_path / "v.f32", blocks())

    def test_voice_read_error_a_real_failure_to_write_still_says_it_could_not_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def full(_src: object, _dst: object) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(os, "replace", full)
        with pytest.raises(ProjectError, match="no pude escribir") as info:
            write_f32_blocks(tmp_path / "v.f32", [np.zeros(2, dtype=np.float32)])
        assert "no pude leer" not in info.value.message_es
        assert list(tmp_path.iterdir()) == []
