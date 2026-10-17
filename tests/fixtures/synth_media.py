"""Synthetic raw material for the tests. Everything is generated with ffmpeg lavfi and Pillow.

The synthetic world: "real time" R. Camera A starts at R=0, camera B at R=1.2 s, so B's t=0 falls
at t=1200 ms of A. Tones and beeps are a function of R, so both cameras hear the same events.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from kcut import proc
from kcut.doctor.ffmpeg_caps import parse_filters
from kcut.ff.args import fnum

_QUIET = ["-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
_SPEECH = "flite=text='hello world this is a test':voice=kal"
_FLASH = "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='eq(n,{n})'"
_HLG = "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc"
_BT709_TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
_HLG_TAGS = ["-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc"]
_AAC = ["-c:a", "aac", "-b:a", "128k"]


@dataclass(frozen=True)
class MediaTruth:
    """What the synthetic material contains, in the units the tests assert on."""

    offset_b_ms: int
    flash_a_f: int
    flash_b_f: int
    beeps_real_s: tuple[float, float]
    speech_real_s: float
    has_speech: bool


def tones_expr(shift_s: float) -> str:
    """`aevalsrc` expression of the real-time signal R evaluated at `t + shift_s`."""
    t = f"(t+{fnum(shift_s)})"
    return (
        f"0.4*sin(2*PI*440*{t})*between(mod({t},1.7),0,0.35)"
        f"+0.3*sin(2*PI*660*{t})*between(mod({t},2.3),1.1,1.4)"
        f"+0.6*sin(2*PI*2000*{t})*(between({t},3.0,3.1)+between({t},6.0,6.1))"
    )


def has_flite() -> bool:
    """True if this ffmpeg build has the `flite` text-to-speech source."""
    result = proc.run(
        [str(proc.tool_path("ffmpeg")), "-hide_banner", "-nostdin", "-filters"],
        capture_stderr=True,
    )
    return "flite" in parse_filters(result.stdout.decode("utf-8", errors="replace") + result.stderr)


def make_media(crudo: Path) -> MediaTruth:
    """Create `cam a.mp4`, `cam b.mov`, `pantalla.mp4`, `foto.png` and `brief.txt` in `crudo`."""
    crudo.mkdir(parents=True, exist_ok=True)
    speech = has_flite()
    _cam_a(crudo / "cam a.mp4", speech)
    _cam_b(crudo / "cam b.mov", speech)
    _screen(crudo / "pantalla.mp4")
    _photo(crudo / "foto.png")
    (crudo / "brief.txt").write_text("brief de prueba", encoding="utf-8", newline="\n")
    return MediaTruth(
        offset_b_ms=1200,
        flash_a_f=90,
        flash_b_f=144,
        beeps_real_s=(3.0, 6.0),
        speech_real_s=4.2,
        has_speech=speech,
    )


def make_tagged_mov(dst: Path) -> None:
    """A 2 s `.mov` with GPS location and device model tags, like an iPhone clip (privacy test)."""
    _ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x568:r=30:d=2",
            "-f",
            "lavfi",
            "-i",
            f"aevalsrc='{tones_expr(0.0)}':s=44100:d=2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            *_AAC,
            "-movflags",
            "use_metadata_tags",
            "-metadata",
            "com.apple.quicktime.location.ISO6709=+18.4861-069.9312/",
            "-metadata",
            "com.apple.quicktime.model=iPhone15",
            str(dst),
        ]
    )


def _cam_a(dst: Path, speech: bool) -> None:
    video = f"[0:v]{_FLASH.format(n=90)},format=yuv420p[v]"
    inputs = ["-f", "lavfi", "-i", "testsrc2=s=1440x2560:r=30:d=12"]
    inputs += ["-f", "lavfi", "-i", f"aevalsrc='{tones_expr(0.0)}':s=44100:d=12"]
    if speech:
        inputs += ["-f", "lavfi", "-i", _SPEECH]
        audio = (
            "[2:a]aresample=44100,adelay=4200[sp];"
            "[1:a][sp]amix=inputs=2:normalize=0:duration=first[a]"
        )
    else:
        audio = "[1:a]anull[a]"
    _ffmpeg(
        [
            *inputs,
            "-filter_complex",
            f"{video};{audio}",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            *_BT709_TAGS,
            *_AAC,
            "-t",
            "12",
            str(dst),
        ]
    )


def _cam_b(dst: Path, speech: bool) -> None:
    video = f"[0:v]{_FLASH.format(n=144)},format=yuv420p10le,{_HLG}[v]"
    inputs = ["-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=12"]
    inputs += ["-f", "lavfi", "-i", f"aevalsrc='{tones_expr(1.2)}':s=48000:d=12"]
    inputs += ["-f", "lavfi", "-i", "anoisesrc=a=0.01:r=48000:d=12:seed=42"]
    if speech:
        inputs += ["-f", "lavfi", "-i", _SPEECH]
        audio = (
            "[3:a]aresample=48000,adelay=3000[sp];"
            "[1:a][2:a][sp]amix=inputs=3:normalize=0:duration=first[a]"
        )
    else:
        audio = "[1:a][2:a]amix=inputs=2:normalize=0:duration=first[a]"
    _ffmpeg(
        [
            *inputs,
            "-filter_complex",
            f"{video};{audio}",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-profile:v",
            "high10",
            "-preset",
            "ultrafast",
            "-crf",
            "22",
            *_HLG_TAGS,
            *_AAC,
            "-t",
            "12",
            str(dst),
        ]
    )


def _screen(dst: Path) -> None:
    _ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=1894x866:r=30:d=8",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            *_BT709_TAGS,
            str(dst),
        ]
    )


def _photo(dst: Path) -> None:
    image = Image.new("RGBA", (800, 600), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((200, 100, 600, 500), fill=(229, 255, 31, 255))
    image.save(dst)


def _ffmpeg(tail: list[str]) -> None:
    """Run ffmpeg with an argument list; fail the test with the stderr tail if it errors."""
    args = [str(proc.tool_path("ffmpeg")), *_QUIET, *tail]
    result = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail_text = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise AssertionError(f"ffmpeg fallo generando medios sinteticos:\n{tail_text}")


def make_silent_video(dst: Path) -> None:
    """A 1 s clip whose audio track is digital silence (classified `video_mudo`)."""
    _ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x568:r=30:d=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            *_AAC,
            str(dst),
        ]
    )


def make_audio_track(dst: Path, shift_s: float, speech: bool) -> None:
    """An audio-only recording that started `shift_s` after camera A, like a separate recorder."""
    inputs = ["-f", "lavfi", "-i", f"aevalsrc='{tones_expr(shift_s)}':s=48000:d=12"]
    if speech:
        delay_ms = round((4.2 - shift_s) * 1000)
        inputs += ["-f", "lavfi", "-i", _SPEECH]
        graph = (
            f"[1:a]aresample=48000,adelay={delay_ms}[sp];"
            "[0:a][sp]amix=inputs=2:normalize=0:duration=first[a]"
        )
    else:
        graph = "[0:a]anull[a]"
    _ffmpeg([*inputs, "-filter_complex", graph, "-map", "[a]", *_AAC, "-t", "12", str(dst)])


def make_unrelated_audio(dst: Path) -> None:
    """Twelve seconds of noise bursts that match no camera."""
    burst = "random(0)*0.5*between(mod(t,0.83),0,0.31)+random(1)*0.4*between(mod(t,1.37),0.5,0.9)"
    _ffmpeg(["-f", "lavfi", "-i", f"aevalsrc='{burst}':s=48000:d=12", *_AAC, "-t", "12", str(dst)])
