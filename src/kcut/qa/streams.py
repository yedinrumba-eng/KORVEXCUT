"""The checks that read the container: frames, video stream, audio stream and the difference in
length between them (spec S1.9a). `probe_args` and `parse_probe` are pure; `run_probe` runs ffprobe.

ffprobe asks for the fields it needs and nothing else (`-show_entries`, no `-show_format`, no
tags): the raw answer is never kept or printed (spec 0.8), and what comes out of it is a number or
a short plain word. Everything in the answer is data from outside and none of it is trusted.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kcut import proc
from kcut.config.model import QaSection
from kcut.edl.model import Edl
from kcut.errors import ProjectError
from kcut.qa.report import Check, Status

ENTRIES = (
    "stream=codec_type,codec_name,width,height,r_frame_rate,color_space,"
    "sample_rate,channels,duration,nb_read_frames"
)
PROBE_FLOOR_S = 120.0
PROBE_PER_SECOND_S = 5.0  # seconds allowed for each second of video, besides the floor (001.41)
_TOKEN = re.compile(r"[A-Za-z0-9_./:-]{1,24}")
_VIDEO_CODEC, _AUDIO_CODEC, _AUDIO_RATE, _AUDIO_CHANNELS = "h264", "aac", 48000, 2
_COLOR_SPACE = "bt709"
_MS = 1000


def measure_timeout_s(seconds: float) -> float:
    """What an `ffmpeg` or `ffprobe` that decodes `seconds` of video is given to finish: 120 s and
    5 s more for each second of video (001.41, point 10; it was 30 s, which gave 5 hours to each
    child on a video of 10 minutes). A hung child is killed, not waited for."""
    return PROBE_PER_SECOND_S * seconds + PROBE_FLOOR_S


@dataclass(frozen=True)
class VideoFacts:
    codec: str | None
    width: int | None
    height: int | None
    fps: str | None
    color_space: str | None
    duration_s: float | None
    frames: int | None


@dataclass(frozen=True)
class AudioFacts:
    codec: str | None
    sample_rate: int | None
    channels: int | None
    duration_s: float | None


@dataclass(frozen=True)
class Facts:
    """What the file says of its first video stream and its first audio stream (`None`: none)."""

    video: VideoFacts | None
    audio: AudioFacts | None


def probe_args(ffprobe: Path, video: Path) -> list[str]:
    """`ffprobe` over `video`: the decoded frames and the fields of the two streams, as JSON."""
    return [
        str(ffprobe), "-v", "error", "-count_frames",
        "-show_entries", ENTRIES, "-of", "json", str(video),
    ]  # fmt: skip


def run_probe(video: Path, log: Path | None, timeout_s: float) -> Mapping[str, Any]:
    """The JSON that `ffprobe` gives for `video`. Anything that is not an object is a
    ProjectError that does not repeat what ffprobe said."""
    args = probe_args(proc.tool_path("ffprobe"), video)
    result = proc.run(args, log=log, timeout_s=timeout_s)
    try:
        data = json.loads(result.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        raise ProjectError("ffprobe devolvió una respuesta que no es JSON") from None
    if not isinstance(data, dict):
        raise ProjectError("ffprobe devolvió una respuesta inesperada")
    return data


def facts_of(data: object) -> Facts:
    """The facts of the two streams from the JSON of ffprobe; a ProjectError if it is not an
    object with a list of `streams`."""
    streams = data.get("streams") if isinstance(data, dict) else None
    if not isinstance(streams, list):
        raise ProjectError("ffprobe devolvió una respuesta sin 'streams'")
    typed = [s for s in streams if isinstance(s, dict)]
    video = next((s for s in typed if s.get("codec_type") == "video"), None)
    audio = next((s for s in typed if s.get("codec_type") == "audio"), None)
    return Facts(None if video is None else _video(video), None if audio is None else _audio(audio))


def parse_probe(data: object, edl: Edl, qa: QaSection) -> list[Check]:
    """The checks `frames`, `video_stream`, `audio_stream` and `av_delta`, in that order.

    - `frames`: the frames ffprobe decoded are the `edl.frames`.
    - `video_stream`: h264, the size of the EDL, `r_frame_rate` `<fps>/1` and `color_space` bt709.
    - `audio_stream`: aac, 48000 Hz, 2 channels.
    - `av_delta`: the streams differ in length by at most `qa.max_av_delta_ms`."""
    return checks_of(facts_of(data), edl, qa)


def checks_of(facts: Facts, edl: Edl, qa: QaSection) -> list[Check]:
    """`parse_probe` over facts already read."""
    video, audio = facts.video, facts.audio
    frames = None if video is None else video.frames
    size = None
    if video is not None and video.width is not None and video.height is not None:
        size = f"{video.width}x{video.height}"
    video_value = {
        "codec": None if video is None else video.codec,
        "size": size,
        "fps": None if video is None else video.fps,
        "color_space": None if video is None else video.color_space,
    }
    video_ok = (
        video_value["codec"] == _VIDEO_CODEC
        and size == f"{edl.out_w}x{edl.out_h}"
        and video_value["fps"] == f"{edl.fps}/1"
        and video_value["color_space"] == _COLOR_SPACE
    )
    audio_value = {
        "codec": None if audio is None else audio.codec,
        "sample_rate": None if audio is None else audio.sample_rate,
        "channels": None if audio is None else audio.channels,
    }
    audio_ok = (
        audio_value["codec"] == _AUDIO_CODEC
        and audio_value["sample_rate"] == _AUDIO_RATE
        and audio_value["channels"] == _AUDIO_CHANNELS
    )
    delta = _delta_ms(video, audio)
    return [
        Check("frames", _status(frames == edl.frames), {"value": frames, "expected": edl.frames}),
        Check("video_stream", _status(video_ok), {"value": video_value}),
        Check("audio_stream", _status(audio_ok), {"value": audio_value}),
        Check(
            "av_delta",
            _status(delta is not None and delta <= qa.max_av_delta_ms),
            {"value_ms": None if delta is None else round(delta, 1), "max_ms": qa.max_av_delta_ms},
        ),
    ]


def _status(ok: bool) -> Status:
    return "pass" if ok else "fail"


def _delta_ms(video: VideoFacts | None, audio: AudioFacts | None) -> float | None:
    """`|audio - video|` in milliseconds, or `None` if either length is not known. Rounded to the
    microsecond: the lengths are decimals in text, and `11.525 - 11.5` is not exactly 0.025."""
    if video is None or audio is None or video.duration_s is None or audio.duration_s is None:
        return None
    return round(abs(audio.duration_s - video.duration_s) * _MS, 3)


def _video(s: Mapping[str, Any]) -> VideoFacts:
    return VideoFacts(
        codec=_token(s.get("codec_name")),
        width=_int(s.get("width")),
        height=_int(s.get("height")),
        fps=_token(s.get("r_frame_rate")),
        color_space=_token(s.get("color_space")),
        duration_s=_seconds(s.get("duration")),
        frames=_int(s.get("nb_read_frames")),
    )


def _audio(s: Mapping[str, Any]) -> AudioFacts:
    return AudioFacts(
        codec=_token(s.get("codec_name")),
        sample_rate=_int(s.get("sample_rate")),
        channels=_int(s.get("channels")),
        duration_s=_seconds(s.get("duration")),
    )


def _token(value: object) -> str | None:
    """A short plain word from the file (a codec, a rate), or `?` if it is anything else. The
    report is read by Claude, and a field of the file is not a place for a sentence."""
    if value is None:
        return None
    if isinstance(value, str) and _TOKEN.fullmatch(value) is not None:
        return value
    return "?"


def _int(value: object) -> int | None:
    """A whole number that ffprobe printed as a number or as text; `N/A` and junk give `None`."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def _seconds(value: object) -> float | None:
    """A length in seconds that ffprobe printed as text or as a number; junk gives `None`."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds == seconds and abs(seconds) != float("inf") else None
