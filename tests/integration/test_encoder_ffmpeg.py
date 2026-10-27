"""`Encoder` with the real ffmpeg (spec S1.5b): frames in, an mp4 with the bt709 tags out."""

from pathlib import Path

import numpy as np
import pytest

from kcut.errors import ToolError
from kcut.render.encoder import Encoder
from tests.fixtures.av_probe import stream_tags

pytestmark = pytest.mark.ffmpeg
W, H = 64, 48


def _frame(value: int) -> np.ndarray:
    frame = np.zeros((H, W, 3), np.uint8)
    frame[:] = value
    return frame


def test_encoder_counts_the_frames_it_wrote_and_the_file_has_them(tmp_path: Path) -> None:
    dst = tmp_path / "carpeta ñandú" / "salida.partial.mp4"
    dst.parent.mkdir()
    with Encoder(dst, W, H, 30, None) as encoder:
        for value in range(0, 90, 10):
            encoder.write(_frame(value))
        assert encoder.close() == 9
        assert encoder.close() == 9  # closing twice changes nothing
    tags = stream_tags(dst, "nb_frames,width,height,color_space,color_primaries,color_range")
    assert tags["nb_frames"] == "9" and (tags["width"], tags["height"]) == (str(W), str(H))
    assert (tags["color_space"], tags["color_primaries"], tags["color_range"]) == (
        "bt709",
        "bt709",
        "tv",
    )


def test_encoder_a_with_that_ends_well_closes_the_file(tmp_path: Path) -> None:
    dst = tmp_path / "v.partial.mp4"
    with Encoder(dst, W, H, 24, None) as encoder:
        encoder.write(_frame(200))
    assert stream_tags(dst, "nb_frames")["nb_frames"] == "1"


def test_encoder_a_frame_of_another_size_or_type_is_a_bug_of_the_caller(tmp_path: Path) -> None:
    with Encoder(tmp_path / "v.partial.mp4", W, H, 30, None) as encoder:
        with pytest.raises(ValueError, match="el frame tiene que ser"):
            encoder.write(np.zeros((H + 2, W, 3), np.uint8))
        with pytest.raises(ValueError, match="el frame tiene que ser"):
            encoder.write(np.zeros((H, W, 3), np.float32))
        with pytest.raises(ValueError, match="el frame tiene que ser"):
            encoder.write(np.zeros((H, W), np.uint8))
        encoder.write(_frame(10))


def test_encoder_an_error_inside_the_with_kills_ffmpeg(tmp_path: Path) -> None:
    encoder = Encoder(tmp_path / "v.partial.mp4", W, H, 30, None)
    child = encoder._child
    with pytest.raises(RuntimeError), encoder:
        encoder.write(_frame(10))
        raise RuntimeError("boom")
    assert child._popen.poll() is not None  # not left running


def test_encoder_an_ffmpeg_that_cannot_write_is_a_tool_error_with_its_stderr(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "no existe" / "v.partial.mp4"  # the folder is not there
    encoder = Encoder(missing, W, H, 30, None)
    with pytest.raises(ToolError, match="ffmpeg"):
        for _ in range(200):
            encoder.write(_frame(5))
        encoder.close()
