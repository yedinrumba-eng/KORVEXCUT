"""Pure builders of ffmpeg/ffprobe argument lists. They never run anything (spec 0.8)."""

import math
from pathlib import Path
from typing import Literal

_QUIET = ["-hide_banner", "-nostdin", "-loglevel", "error"]
_COLOR_TAGS = [
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
]
_NO_METADATA = ["-map_metadata", "-1"]


def fnum(x: float) -> str:
    """Format a number for a command line: six decimals, no trailing zeros. NaN/inf raise."""
    if not math.isfinite(x):
        raise ValueError(f"numero no finito: {x!r}")
    text = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def ffprobe_args(ffprobe: Path, src: Path) -> list[str]:
    """Probe format and streams as JSON. The raw output is parsed in memory and never stored."""
    return [
        str(ffprobe),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(src),
    ]


def wav_args(
    ffmpeg: Path, src: Path, dst: Path, sr: Literal[16000, 48000], limit_s: float | None = None
) -> list[str]:
    """First audio stream to mono s16 wav at `sr`, timestamps starting at 0, no metadata.

    `limit_s` caps the output length (`-t`): the declared duration of a file is not trusted."""
    return [
        str(ffmpeg),
        *_QUIET,
        *_overwrite(dst),
        "-i",
        str(src),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-af",
        f"aresample={sr}:resampler=soxr:first_pts=0",
        "-c:a",
        "pcm_s16le",
        *_limit(limit_s),
        *_NO_METADATA,
        str(dst),
    ]


def proxy_args(
    ffmpeg: Path, src: Path, dst: Path, chain: str, fps: int, limit_s: float | None = None
) -> list[str]:
    """Small CFR bt709 proxy of the first video stream (no audio, no metadata); `limit_s` as in
    `wav_args`."""
    return [
        str(ffmpeg),
        *_QUIET,
        *_overwrite(dst),
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        chain,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-g",
        str(fps),
        "-keyint_min",
        str(fps),
        "-pix_fmt",
        "yuv420p",
        *_COLOR_TAGS,
        *_limit(limit_s),
        *_NO_METADATA,
        "-movflags",
        "+faststart",
        str(dst),
    ]


def mezz_args(
    ffmpeg: Path, src: Path, dst: Path, chain: str, fps: int, start_f: int, count_f: int
) -> list[str]:
    """High-quality intermediate of `count_f` frames starting at frame `start_f`."""
    return [
        str(ffmpeg),
        *_QUIET,
        *_overwrite(dst),
        "-ss",
        fnum(start_f / fps),
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        chain,
        "-frames:v",
        str(count_f),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "14",
        "-g",
        str(fps),
        "-keyint_min",
        str(fps),
        "-pix_fmt",
        "yuv420p",
        *_COLOR_TAGS,
        *_NO_METADATA,
        str(dst),
    ]


def _overwrite(dst: Path) -> list[str]:
    """`-y` only when the destination is a `.partial` file (spec 0.8)."""
    return ["-y"] if ".partial." in dst.name else []


def _limit(limit_s: float | None) -> list[str]:
    return [] if limit_s is None else ["-t", fnum(limit_s)]
