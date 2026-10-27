"""The one encode of the picture: raw BGR frames in, an H.264 mp4 out (spec S1.5b, DS2).

Everything that goes in the picture (cameras, cards, graphics) has been composed in numpy before
it gets here, so the video is encoded once, with no second compression. The conversion to YUV is
explicit (bt709, limited range) and the file carries the four bt709/tv tags (lesson 5; 001.4).
"""

import contextlib
from pathlib import Path
from types import TracebackType
from typing import Self

import numpy as np
from numpy.typing import NDArray

from kcut import proc
from kcut.errors import ToolError
from kcut.ff.color import TAGS_BT709

_COLOR_FLAGS = [
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
]
_TO_YUV = "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p," + TAGS_BT709
_CRF = 18
_FINISH_S = 120.0  # what ffmpeg has to close the file once it has the last frame


def encoder_args(ffmpeg: Path, dst: Path, w: int, h: int, fps: int) -> list[str]:
    """The ffmpeg command that reads `w`x`h` raw BGR frames at `fps` from stdin and writes `dst`.
    `-y` only if `dst` is a `.partial` file (spec 0.8)."""
    return [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        *(["-y"] if ".partial." in dst.name else []),
        *("-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"),
        *("-vf", _TO_YUV),
        *("-c:v", "libx264", "-preset", "slow", "-crf", str(_CRF), "-g", str(2 * fps)),
        *("-pix_fmt", "yuv420p"),
        *_COLOR_FLAGS,
        *("-movflags", "+faststart"),
        str(dst),
    ]


class Encoder:
    """Writes frames to an ffmpeg process. Use it as a context manager: if the `with` ends with
    an error ffmpeg is killed, and if it ends without one `close()` is called for you."""

    def __init__(self, dst: Path, W: int, H: int, fps: int, log: Path | None) -> None:
        self._w, self._h = W, H
        self._written = 0
        self._closed = False
        args = encoder_args(proc.tool_path("ffmpeg"), dst, W, H, fps)
        self._child = proc.popen(args, log=log, stdin_pipe=True)

    def write(self, frame_bgr: NDArray[np.uint8]) -> None:
        """One `(H, W, 3)` uint8 BGR frame."""
        if frame_bgr.shape != (self._h, self._w, 3) or frame_bgr.dtype != np.uint8:
            raise ValueError(
                f"el frame tiene que ser ({self._h}, {self._w}, 3) uint8 "
                f"(vino {frame_bgr.shape} {frame_bgr.dtype})"
            )
        stream = self._child.stdin
        if stream is None:
            raise ToolError("el codificador no tiene entrada")
        try:
            stream.write(np.ascontiguousarray(frame_bgr).data)
        except (BrokenPipeError, OSError):
            self._child.wait(timeout_s=_FINISH_S)
            raise ToolError(
                f"ffmpeg se cerró antes de recibir el frame {self._written + 1}. "
                f"Últimas líneas de stderr:\n{self._child.stderr_tail()}"
            ) from None
        self._written += 1

    def close(self) -> int:
        """End the file and return how many frames were written. ffmpeg exiting with an error is
        a ToolError that carries the tail of its stderr."""
        if self._closed:
            return self._written
        self._closed = True
        stream = self._child.stdin
        if stream is not None:
            with contextlib.suppress(OSError):  # ffmpeg already closed it: its exit code says why
                stream.close()
        code = self._child.wait(timeout_s=_FINISH_S)
        if code != 0:
            raise ToolError(
                f"ffmpeg terminó con error (código {code}) al codificar el video. "
                f"Últimas líneas de stderr:\n{self._child.stderr_tail()}"
            )
        return self._written

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None and not self._closed:
            self._closed = True
            self._child.__exit__(exc_type, exc, tb)  # kills ffmpeg and waits for it
        elif not self._closed:
            self.close()
