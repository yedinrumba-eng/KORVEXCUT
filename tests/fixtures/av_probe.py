"""Reading a rendered video back to see where its flashes and beeps are (spec S1.5b rows 7, 14).

A frame is a flash if its mean gray is at least 170 and beats the average of the frames three
before and three after it by 60 or more. A beep is a 2 kHz tone: the audio goes through a
Butterworth band-pass of 1800 to 2200 Hz (scipy), its envelope is taken at 5 ms and the beep
starts where the envelope crosses half of its maximum.
"""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from kcut import proc
from kcut.ff.reader import reader_args, seek_input

SAMPLE_RATE = 48000
FLASH_MIN_GRAY = 170.0
FLASH_MARGIN = 60.0
FLASH_NEIGHBOURS = 3
BAND_HZ = (1800.0, 2200.0)
ENVELOPE_S = 0.005
MIN_SEPARATION_S = 0.05  # two beeps closer than this are one


def gray_per_frame(
    video: Path,
    frames: int,
    source: tuple[int, int] = (1080, 1920),
    size: tuple[int, int] = (54, 96),
) -> list[float]:
    """The mean gray of each of the first `frames` frames of `video` (of `source` size, which
    the decoder is told so), scaled down to `size` by ffmpeg before they cross the pipe."""
    args = reader_args(
        proc.tool_path("ffmpeg"),
        seek_input(video, 0, 30, source),
        frames,
        pre_filters=f"scale={size[0]}:{size[1]}",
    )
    raw = proc.run(args, timeout_s=300).stdout
    pictures = np.frombuffer(raw, dtype=np.uint8).reshape(-1, size[1], size[0], 3)
    return [float(picture.mean()) for picture in pictures]


def flash_frames(grays: list[float]) -> list[int]:
    """The frames of `grays` that are a flash: bright, and 60 above their six neighbours."""
    found: list[int] = []
    for f, gray in enumerate(grays):
        around = [
            grays[g]
            for g in range(f - FLASH_NEIGHBOURS, f + FLASH_NEIGHBOURS + 1)
            if g != f and 0 <= g < len(grays)
        ]
        if gray >= FLASH_MIN_GRAY and around and gray - sum(around) / len(around) >= FLASH_MARGIN:
            found.append(f)
    return found


def beep_onsets(samples: NDArray[np.float32], rate: int = SAMPLE_RATE) -> list[float]:
    """The seconds at which each 2 kHz beep of `samples` starts."""
    sos = signal.butter(4, BAND_HZ, btype="bandpass", fs=rate, output="sos")
    band = signal.sosfiltfilt(sos, samples.astype(np.float64))
    width = max(1, round(ENVELOPE_S * rate))
    envelope = np.convolve(np.abs(band), np.ones(width) / width, mode="same")
    peak = float(envelope.max())
    if peak <= 0:
        return []
    loud = np.flatnonzero(envelope >= 0.5 * peak)
    onsets: list[float] = []
    previous = -10 * rate
    for n in loud:
        if n - previous > MIN_SEPARATION_S * rate:
            onsets.append(float(n) / rate)
        previous = int(n)
    return onsets


def decode_audio(video: Path) -> NDArray[np.float32]:
    """The audio of `video` as float32 mono at 48 kHz, decoded by ffmpeg."""
    args = [
        str(proc.tool_path("ffmpeg")),
        *("-hide_banner", "-nostdin", "-loglevel", "error"),
        *("-i", str(video)),
        *("-vn", "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"),
    ]
    return np.frombuffer(proc.run(args, timeout_s=120).stdout, dtype="<f4").astype(np.float32)


def stream_tags(video: Path, entries: str, stream: str = "v:0") -> dict[str, str]:
    """`ffprobe -show_entries stream=<entries>` of one stream, as a dict (no file names)."""
    args = [
        str(proc.tool_path("ffprobe")),
        *("-v", "error", "-select_streams", stream),
        *("-show_entries", f"stream={entries}", "-of", "default=noprint_wrappers=1"),
        str(video),
    ]
    text = proc.run(args, timeout_s=60).stdout.decode("utf-8", "replace")
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


__all__ = [
    "beep_onsets",
    "decode_audio",
    "flash_frames",
    "gray_per_frame",
    "stream_tags",
]
