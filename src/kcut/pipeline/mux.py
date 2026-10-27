"""Join the picture and the sound in one mp4 (spec S1.5b): copy the video, encode the sound."""

from pathlib import Path

_F32_INPUT = ["-f", "f32le", "-ar", "48000", "-ac", "1"]


def mux_args(
    ffmpeg: Path, video: Path, audio: Path, dst: Path, *, audio_f32: bool = False
) -> list[str]:
    """The ffmpeg command that copies the video of `video`, encodes `audio` as AAC 192k stereo
    at 48 kHz and writes `dst`. With `audio_f32` the audio is the raw float32 mono 48 kHz file
    of the voice track (DS4), which has no header to say so. `-y` only if `dst` is a `.partial`
    file (spec 0.8)."""
    return [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        *(["-y"] if ".partial." in dst.name else []),
        *("-i", str(video)),
        *(_F32_INPUT if audio_f32 else []),
        *("-i", str(audio)),
        *("-map", "0:v:0", "-map", "1:a:0"),
        *("-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"),
        *("-movflags", "+faststart"),
        str(dst),
    ]
