"""The looks through the real ffmpeg (spec S1.5b row 4): what each chain does to a color, that a
round trip through the encoder and the reader keeps the brand's lime, and that no look makes ffmpeg
convert to or from YUV behind our back (DS3).
"""

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut import proc
from kcut.config.model import BrandSection
from kcut.ff.reader import FrameReader, reader_args
from kcut.render.encoder import Encoder
from kcut.render.looks import LOOKS, look_chain

pytestmark = pytest.mark.ffmpeg
BRAND = BrandSection("#E5FF1F", "#2FA8FF", "#0B0B0E", "#FFFFFF")
SIZE = 64
Frame = NDArray[np.uint8]


def _args(look: str, color: str, *, verbose: bool = False) -> list[str]:
    source = f"color=c={color}:s={SIZE}x{SIZE}:d=0.04"
    args = reader_args(
        proc.tool_path("ffmpeg"),
        ["-f", "lavfi", "-i", source],
        1,
        rgb_filters=look_chain(look, BRAND),
    )
    if verbose:
        args[args.index("-loglevel") + 1] = "verbose"
    return args


def _frame(look: str, color: str) -> Frame:
    """The one BGR frame the reader gives for `color` seen through `look`."""
    out = proc.run(_args(look, color), timeout_s=60).stdout
    assert len(out) == SIZE * SIZE * 3
    return np.frombuffer(out, np.uint8).reshape(SIZE, SIZE, 3)


def _mean(frame: Frame) -> tuple[float, float, float]:
    b, g, r = (float(frame[..., c].mean()) for c in range(3))
    return b, g, r


class TestWhatEachLookDoes:
    def test_looks_neutro_keeps_a_mid_gray_within_two(self) -> None:
        b, g, r = _mean(_frame("neutro", "gray"))
        assert all(abs(c - 128) <= 2 for c in (b, g, r))

    def test_looks_calido_pushes_red_over_blue(self) -> None:
        b, _, r = _mean(_frame("calido", "gray"))
        assert r - b >= 4

    def test_looks_frio_pushes_blue_over_red(self) -> None:
        b, _, r = _mean(_frame("frio", "gray"))
        assert b - r >= 4

    def test_looks_contraste_darkens_64_and_lightens_192(self) -> None:
        dark = _mean(_frame("contraste", "0x404040"))
        light = _mean(_frame("contraste", "0xC0C0C0"))
        assert all(c < 64 for c in dark) and all(c > 192 for c in light)

    def test_looks_cinematico_makes_the_corner_darker_than_the_center(self) -> None:
        frame = _frame("cinematico", "gray").astype(int)
        center = frame[SIZE // 2 - 2 : SIZE // 2 + 2, SIZE // 2 - 2 : SIZE // 2 + 2].mean()
        corner = frame[:2, :2].mean()
        assert center - corner >= 3

    def test_looks_bn_acento_leaves_a_pure_red_gray(self) -> None:
        b, g, r = _mean(_frame("bn-acento", "red"))
        assert max(b, g, r) - min(b, g, r) <= 3

    def test_looks_bn_acento_keeps_the_accent(self) -> None:
        b, g, _ = _mean(_frame("bn-acento", "0xE5FF1F"))
        assert g - b >= 100

    def test_looks_bn_acento_follows_the_accent_of_the_brand(self) -> None:
        red = BrandSection("#FF0000", "#2FA8FF", "#0B0B0E", "#FFFFFF")
        args = reader_args(
            proc.tool_path("ffmpeg"),
            ["-f", "lavfi", "-i", f"color=c=red:s={SIZE}x{SIZE}:d=0.04"],
            1,
            rgb_filters=look_chain("bn-acento", red),
        )
        frame = np.frombuffer(proc.run(args, timeout_s=60).stdout, np.uint8).reshape(SIZE, SIZE, 3)
        b, g, r = _mean(frame)
        assert r - g >= 100 and r - b >= 100  # now it is red that stays

    @pytest.mark.parametrize("look", list(LOOKS))
    def test_looks_every_look_gives_one_frame_of_the_asked_size(self, look: str) -> None:
        assert _frame(look, "gray").shape == (SIZE, SIZE, 3)


class TestColorPath:
    def test_looks_the_lime_of_the_brand_survives_the_encoder_and_the_reader(
        self, tmp_path: Path
    ) -> None:
        lime = np.zeros((SIZE, SIZE, 3), np.uint8)
        lime[:] = (0x1F, 0xFF, 0xE5)  # #E5FF1F in BGR
        video = tmp_path / "carpeta ñandú" / "lima.partial.mp4"
        video.parent.mkdir()
        with Encoder(video, SIZE, SIZE, 30, None) as encoder:
            for _ in range(6):
                encoder.write(lime)
        with FrameReader(video, 0, 1, 30, (SIZE, SIZE), log=None) as reader:
            frame = next(reader)
        found = frame[SIZE // 2, SIZE // 2].astype(int)
        assert np.abs(found - np.array([0x1F, 0xFF, 0xE5])).max() <= 4, found.tolist()

    def test_looks_a_few_colors_make_the_round_trip_within_four(self, tmp_path: Path) -> None:
        for name, bgr in (("rojo", (0, 0, 255)), ("azul", (255, 80, 0)), ("gris", (128, 128, 128))):
            flat = np.zeros((SIZE, SIZE, 3), np.uint8)
            flat[:] = bgr
            video = tmp_path / f"{name}.partial.mp4"
            with Encoder(video, SIZE, SIZE, 30, None) as encoder:
                for _ in range(4):
                    encoder.write(flat)
            with FrameReader(video, 0, 1, 30, (SIZE, SIZE), log=None) as reader:
                found = next(reader)[SIZE // 2, SIZE // 2].astype(int)
            assert np.abs(found - np.array(bgr)).max() <= 4, (name, found.tolist())

    @pytest.mark.parametrize("look", list(LOOKS))
    def test_looks_no_auto_scale_converts_to_or_from_yuv(self, look: str) -> None:
        result = proc.run(_args(look, "gray", verbose=True), timeout_s=60, capture_stderr=True)
        conversions = [
            line
            for line in result.stderr.splitlines()
            if "auto_scale" in line and "fmt:" in line and "->" in line
        ]
        assert not [line for line in conversions if "yuv" in line], conversions
        assert "rgb24" in result.stderr  # the chain did run in RGB
