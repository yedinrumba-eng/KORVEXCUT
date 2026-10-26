"""A synthetic clip whose video starts after its audio (spec S1.4-14, 0.6, 001.15 T5).

One `.mov` made with ffmpeg lavfi: the video input carries `-itsoffset 0.5`, so the first frame of
video is at 0.5 s of the container and the audio starts at 0. A white flash fills the video's own
frame 30, which is the instant 1.5 s of the source clock, i.e. frame 45 at 30 fps (index 30 of the
proxy, whose first frame is frame 15 of the clock).
"""

from pathlib import Path

from tests.fixtures.synth_media import _ffmpeg, tones_expr

VIDEO_DELAY_S = 0.5
FLASH_VIDEO_FRAME = 30  # the flash, counting from the first frame of video
FLASH_CLOCK_FRAME = 45  # the same instant, counting from the start of the container at 30 fps
_FLASH = "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='eq(n,{n})'"


def make_late_video(dst: Path) -> None:
    """A 5 s `.mov`: audible tones from t = 0, 4.5 s of video from t = 0.5 s (so both end together
    at 5 s, and the 150 frames of the container are the frames the clock has), a flash on 30."""
    flash = _FLASH.format(n=FLASH_VIDEO_FRAME)
    _ffmpeg(
        [
            *("-itsoffset", str(VIDEO_DELAY_S)),
            *("-f", "lavfi", "-i", f"testsrc2=s=320x568:r=30:d=4.5,{flash},format=yuv420p"),
            *("-f", "lavfi", "-i", f"aevalsrc='{tones_expr(0.0)}':s=44100:d=5"),
            *("-map", "0:v", "-map", "1:a"),
            *("-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p"),
            *("-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"),
            *("-c:a", "aac", "-b:a", "128k"),
            *("-t", "5"),
            str(dst),
        ]
    )


SHORT_VIDEO_FRAMES = 90  # 3 s at 30 fps: the proxy of `make_short_video` has frames 0..89


def make_short_video(dst: Path) -> None:
    """A 5 s `.mov` whose video is only 3 s long and starts with the audio: the container says
    150 frames, the video holds 90 (S1.4-23: the proxy, not the container, says what is real)."""
    _ffmpeg(
        [
            *("-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=3,format=yuv420p"),
            *("-f", "lavfi", "-i", f"aevalsrc='{tones_expr(0.0)}':s=44100:d=5"),
            *("-map", "0:v", "-map", "1:a"),
            *("-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p"),
            *("-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"),
            *("-c:a", "aac", "-b:a", "128k"),
            *("-t", "5"),
            str(dst),
        ]
    )
