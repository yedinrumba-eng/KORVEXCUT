"""The measurements with the real ffmpeg (spec S1.8b row 9, 001.15 T3): `ebur128` over a sine of 3 s
(`-f lavfi -i sine=d=3`) gives `I` and `TP` in its `Summary`, and the first pass of `loudnorm` gives
its JSON. Both run at the `info` level, without `-loglevel error` and with `-nostats`; the stderr is
read by the parser and nothing of it is shown.
"""

from pathlib import Path

import numpy as np
import pytest

from kcut import proc
from kcut.audio.loudnorm import ebur128_args, parse_ebur128, parse_pass1, pass1_args

pytestmark = pytest.mark.ffmpeg
RAW = ["-f", "f32le", "-ar", "48000", "-ac", "1"]


def _sine(path: Path, amplitude: float, seconds: int = 3) -> Path:
    t = np.arange(48000 * seconds) / 48000
    (amplitude * np.sin(2 * np.pi * 440.0 * t)).astype("<f4").tofile(path)
    return path


def test_ebur128_live_reads_i_and_tp_of_a_sine_of_3_seconds() -> None:
    args = ebur128_args(proc.tool_path("ffmpeg"), ["-f", "lavfi", "-i", "sine=d=3"])
    found = parse_ebur128(proc.run(args, capture_stderr=True).stderr)
    # the sine of lavfi is 440 Hz at 1/8 of the scale: a peak of -18.06 dBFS and -21.8 LUFS
    assert found.I is not None and pytest.approx(-21.8, abs=0.3) == found.I, found
    assert found.TP is not None and pytest.approx(-18.1, abs=0.3) == found.TP, found
    assert found.LRA is not None and found.LRA >= 0.0


def test_ebur128_live_the_frame_log_is_quiet_and_there_is_one_summary() -> None:
    args = ebur128_args(proc.tool_path("ffmpeg"), ["-f", "lavfi", "-i", "sine=d=3"])
    stderr = proc.run(args, capture_stderr=True).stderr
    assert stderr.count("Summary:") == 1
    assert stderr.count("TARGET:") == 0  # without `framelog=quiet` it prints a line every 100 ms


def test_ebur128_live_reads_a_raw_float32_file(tmp_path: Path) -> None:
    path = _sine(tmp_path / "tono.f32", 0.1)
    args = ebur128_args(proc.tool_path("ffmpeg"), [*RAW, "-i", str(path)])
    found = parse_ebur128(proc.run(args, capture_stderr=True).stderr)
    assert found.TP is not None and pytest.approx(-20.0, abs=0.3) == found.TP  # 0.1 is -20 dBFS
    # -0.691 + 10 * log10(0.1 ** 2 / 2): the K-weighting of 440 Hz is -0.7 dB
    assert found.I is not None and pytest.approx(-23.7, abs=0.3) == found.I


def test_ebur128_live_the_first_pass_of_loudnorm_gives_its_measure(tmp_path: Path) -> None:
    path = _sine(tmp_path / "tono.f32", 0.125)
    args = pass1_args(proc.tool_path("ffmpeg"), path, -16.0, -2.0, 11.0)
    measure = parse_pass1(proc.run(args, capture_stderr=True).stderr)
    assert measure is not None
    assert measure.input_i == pytest.approx(-21.75, abs=0.3)
    assert measure.input_tp == pytest.approx(-18.06, abs=0.3)


def test_ebur128_live_digital_silence_is_not_normalized(tmp_path: Path) -> None:
    silence = tmp_path / "silencio.f32"
    np.zeros(48000 * 2, dtype="<f4").tofile(silence)
    args = pass1_args(proc.tool_path("ffmpeg"), silence, -16.0, -2.0, 11.0)
    assert parse_pass1(proc.run(args, capture_stderr=True).stderr) is None
