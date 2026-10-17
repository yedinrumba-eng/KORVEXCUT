"""Reduce ffprobe JSON to a whitelist of fields; raw output (GPS, device model) never leaves."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from kcut.errors import ProjectError
from kcut.ff.color import is_hdr

_COVER_CODECS = frozenset({"png", "mjpeg", "webp", "bmp", "tiff", "gif"})
_COVER_MAX_S = 0.5
_VFR_TOLERANCE = Fraction(1, 1000)


@dataclass(frozen=True)
class VideoInfo:
    codec: str
    w: int
    h: int
    display_w: int
    display_h: int
    rotation: int
    fps_r: str
    fps_avg: str
    vfr: bool
    pix_fmt: str
    bit_depth: int
    color_transfer: str | None
    color_primaries: str | None
    color_space: str | None
    color_range: str | None
    hdr: str | None
    dolby_vision: bool
    dv_profile: int | None
    start_ms: int


@dataclass(frozen=True)
class AudioInfo:
    codec: str
    sample_rate: int
    channels: int
    start_ms: int
    streams: int


@dataclass(frozen=True)
class MediaInfo:
    duration_ms: int
    size_bytes: int
    format_name: str
    video: VideoInfo | None
    audio: AudioInfo | None


def parse_ffprobe(data: Mapping[str, Any]) -> MediaInfo:
    """Parse `ffprobe -show_format -show_streams` JSON. Only the fields above are kept."""
    fmt = data.get("format")
    streams = data.get("streams")
    if not isinstance(fmt, Mapping) or not isinstance(streams, list):
        raise ProjectError("ffprobe devolvió una respuesta sin 'format' o 'streams'")
    fmt_start = _seconds(fmt.get("start_time")) or 0.0
    fmt_duration = _seconds(fmt.get("duration"))
    typed = [s for s in streams if isinstance(s, Mapping)]
    video_streams = [
        s for s in typed if s.get("codec_type") == "video" and not _is_cover(s, fmt_duration)
    ]
    audio_streams = [s for s in typed if s.get("codec_type") == "audio"]
    return MediaInfo(
        duration_ms=round((fmt_duration or _longest(typed)) * 1000),
        size_bytes=_int(fmt.get("size"), 0),
        format_name=str(fmt.get("format_name", "")),
        video=_video(video_streams[0], fmt_start) if video_streams else None,
        audio=_audio(audio_streams, fmt_start) if audio_streams else None,
    )


def _video(s: Mapping[str, Any], fmt_start: float) -> VideoInfo:
    w, h = _int(s.get("width"), 0), _int(s.get("height"), 0)
    rotation = _rotation(s)
    swap = abs(rotation) in (90, 270)
    dovi = _side_data(s, "dovi configuration record")
    pix_fmt = str(s.get("pix_fmt", ""))
    fps_r, fps_avg = str(s.get("r_frame_rate", "0/0")), str(s.get("avg_frame_rate", "0/0"))
    transfer = _opt_str(s.get("color_transfer"))
    return VideoInfo(
        codec=str(s.get("codec_name", "")),
        w=w,
        h=h,
        display_w=h if swap else w,
        display_h=w if swap else h,
        rotation=rotation,
        fps_r=fps_r,
        fps_avg=fps_avg,
        vfr=_is_vfr(fps_r, fps_avg),
        pix_fmt=pix_fmt,
        bit_depth=_bit_depth(s, pix_fmt),
        color_transfer=transfer,
        color_primaries=_opt_str(s.get("color_primaries")),
        color_space=_opt_str(s.get("color_space")),
        color_range=_opt_str(s.get("color_range")),
        hdr=is_hdr(transfer),
        dolby_vision=dovi is not None,
        dv_profile=_opt_int(dovi.get("dv_profile")) if dovi is not None else None,
        start_ms=_start_ms(s, fmt_start),
    )


def _audio(streams: list[Mapping[str, Any]], fmt_start: float) -> AudioInfo:
    first = streams[0]
    return AudioInfo(
        codec=str(first.get("codec_name", "")),
        sample_rate=_int(first.get("sample_rate"), 0),
        channels=_int(first.get("channels"), 0),
        start_ms=_start_ms(first, fmt_start),
        streams=len(streams),
    )


def _is_cover(s: Mapping[str, Any], fmt_duration: float | None) -> bool:
    """Attached cover art: an image codec that lasts under 0.5 s (or is flagged attached_pic)."""
    if s.get("codec_name") not in _COVER_CODECS:
        return False
    disposition = s.get("disposition")
    if isinstance(disposition, Mapping) and _int(disposition.get("attached_pic"), 0) == 1:
        return True
    duration = _seconds(s.get("duration"))
    return (duration if duration is not None else fmt_duration or 0.0) < _COVER_MAX_S


def _rotation(s: Mapping[str, Any]) -> int:
    for item in _side_data_list(s):
        if str(item.get("side_data_type", "")).lower() == "display matrix":
            value = _seconds(item.get("rotation"))
            if value is not None:
                return round(value)
    tags = s.get("tags")
    if isinstance(tags, Mapping):
        value = _seconds(tags.get("rotate"))
        if value is not None:
            return round(value)
    return 0


def _side_data(s: Mapping[str, Any], kind: str) -> Mapping[str, Any] | None:
    for item in _side_data_list(s):
        if str(item.get("side_data_type", "")).lower() == kind:
            return item
    return None


def _side_data_list(s: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = s.get("side_data_list")
    return [i for i in raw if isinstance(i, Mapping)] if isinstance(raw, list) else []


def _bit_depth(s: Mapping[str, Any], pix_fmt: str) -> int:
    declared = _int(s.get("bits_per_raw_sample"), 0)
    if declared > 0:
        return declared
    return 10 if pix_fmt.endswith(("10le", "10be")) else 8


def _is_vfr(fps_r: str, fps_avg: str) -> bool:
    real, avg = _fraction(fps_r), _fraction(fps_avg)
    if real is None or avg is None:
        return False
    return abs(real - avg) / real > _VFR_TOLERANCE


def _fraction(text: str) -> Fraction | None:
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def _start_ms(s: Mapping[str, Any], fmt_start: float) -> int:
    start = _seconds(s.get("start_time"))
    return 0 if start is None else round((start - fmt_start) * 1000)


def _longest(streams: list[Mapping[str, Any]]) -> float:
    return max((_seconds(s.get("duration")) or 0.0 for s in streams), default=0.0)


def _seconds(value: object) -> float | None:
    """A number that ffprobe printed as a string or a number; `N/A` and junk give None."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _int(value: object, default: int) -> int:
    number = _seconds(value)
    return default if number is None else round(number)


def _opt_int(value: object) -> int | None:
    number = _seconds(value)
    return None if number is None else round(number)


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) and value != "" else None
