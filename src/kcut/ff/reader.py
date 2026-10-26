"""Read video frames as numpy arrays through one ffmpeg process (spec S1.4, 001.15).

The color chain is fixed (spec 0.7): YUV to RGB with an explicit bt709 matrix and tv range, the
looks (RGB-only filters, S1.5) in between, then BGR for OpenCV and Pillow's `[:, :, ::-1]`.
`reader_args` and `seek_input` are pure; `FrameReader` runs them.
"""

import io
import threading
from pathlib import Path
from types import TracebackType
from typing import Self, cast

import numpy as np
from numpy.typing import NDArray

from kcut import proc
from kcut.errors import ProjectError, ToolError
from kcut.ff.args import fnum
from kcut.ingest.inventory import Clip
from kcut.timebase import ms_to_f_round

_QUIET = ["-hide_banner", "-nostdin", "-loglevel", "error"]
MAX_FRAME_BYTES = 64 * 1024 * 1024  # `w * h * 3` of a frame the reader accepts (001.20)
FRAME_DEADLINE_S = 60.0  # what ffmpeg has to deliver one frame
CLOSE_WAIT_S = 10.0  # what ffmpeg has to end after its last frame; then it is killed (001.21)
PROXY_MISMATCH = "el proxy no coincide con el inventario; corre kcut ingest"
_PROBE_TIMEOUT_S = 120.0
_TO_RGB = "scale=in_color_matrix=bt709:in_range=tv,format=rgb24"
_CHANNELS = 3


def reader_args(
    ffmpeg: Path,
    inputs: list[str],
    count: int,
    *,
    pre_filters: str = "",
    rgb_filters: str = "",
) -> list[str]:
    """The ffmpeg command that writes `count` raw BGR frames of the first video stream to stdout.

    `inputs` is the whole input part: `seek_input(...)` for a file, or `["-f", "lavfi", "-i",
    "<fixed graph>"]`. `pre_filters` are filters of time only (`fps=1/2:round=up`) and go before
    the color conversion, never a color filter; `rgb_filters` are RGB-only and go inside it.
    """
    if count < 1:
        raise ValueError(f"count tiene que ser al menos 1 (vino {count})")
    chain = f"{pre_filters}," if pre_filters else ""
    chain += _TO_RGB
    chain += f",{rgb_filters}" if rgb_filters else ""
    chain += ",format=bgr24"
    return [
        str(ffmpeg),
        *_QUIET,
        *inputs,
        "-map",
        "0:v:0",
        "-an",
        "-frames:v",
        str(count),
        "-vf",
        chain,
        "-f",
        "rawvideo",
        "-",
    ]


def seek_input(path: Path, start_f: int, fps: int, size: tuple[int, int]) -> list[str]:
    """`-ss <time> -max_pixels <2*w*h> -i <path>`, where the time falls a quarter of a frame
    before frame `start_f` so that the frame asked for is the first one out (technique of the
    pilot). `start_f` is the index inside that file, not the frame of the source clock.

    `size` is the `(w, h)` the caller has already checked the file has. The decoder refuses a
    picture of more than twice its pixels (001.22, point 8): twice lets the coded size through
    (576x960 for a proxy of 540x960) and cuts a stream that grows to 4x or more half way, which
    ffmpeg would otherwise follow, handing back frames of another size than the reader expects.
    """
    width, height = size
    if width < 1 or height < 1:
        raise ValueError(f"el tamaño tiene que ser positivo (vino {width}x{height})")
    return [
        "-ss",
        fnum(max(0, (start_f - 0.25) / fps)),
        "-max_pixels",
        str(2 * width * height),
        "-i",
        str(path),
    ]


def proxy_index(clip: Clip, f: int, fps: int) -> int:
    """The index in the clip's proxy of frame `f` of the source clock (spec 0.6, 001.15 T5):
    the proxy starts at the first frame of video, `ms_to_f_round(video.start_ms, fps)` of the
    clock, so frame `f` of the clip is index `f - vs_f` of its proxy."""
    if clip.video is None:
        raise ProjectError(f"{clip.id} no tiene video")
    return f - ms_to_f_round(clip.video.start_ms, fps)


def proxy_frame_count(path: Path, size: tuple[int, int], log: Path | None) -> int:
    """How many frames a proxy really has, from the header of the mp4 (`nb_frames`); if it is
    not there, ffprobe counts them. The container of a clip may be longer than its video, but
    the proxy only holds what the video has, so this is the number to trust (spec 001.19 point 3
    and 001.20 point 3). The same call asks for the size of the stream: one that is not `size`
    `(w, h)`, what the inventory says, is a ProjectError before ffmpeg is started (001.21,
    point 2). Zero frames, or no number at all, is a ProjectError too."""
    ffprobe = str(proc.tool_path("ffprobe"))
    quiet = [ffprobe, "-v", "error", "-select_streams", "v:0", "-of", "default=noprint_wrappers=1"]
    for flags, entry in (([], "nb_frames"), (["-count_frames"], "nb_read_frames")):
        shows = f"stream=width,height,{entry}"
        args = [*quiet, *flags, "-show_entries", shows, str(path)]
        text = proc.run(args, log=log, timeout_s=_PROBE_TIMEOUT_S).stdout.decode("ascii", "replace")
        found = dict(line.strip().split("=", 1) for line in text.splitlines() if "=" in line)
        real = (found.get("width"), found.get("height"))
        if None not in real and real != (str(size[0]), str(size[1])):
            raise ProjectError(PROXY_MISMATCH)
        if found.get(entry, "").isdigit():
            count = int(found[entry])
            if count < 1:
                raise ProjectError(f"el proxy {path.name} no tiene frames; corre kcut ingest")
            return count
    raise ProjectError(f"no pude contar los frames del proxy {path.name}; corre kcut ingest")


class FrameReader:
    """An iterator of BGR frames `(h, w, 3)` (uint8) from one ffmpeg process; a context manager.

    `size` is `(w, h)` of the frames as they come out, after `pre_filters`. It asks ffmpeg for
    `count` frames starting at index `start_f` of the file and reads exactly `w * h * 3` bytes
    for each, into one buffer that the frame then uses. A frame of more than `MAX_FRAME_BYTES`
    is a ProjectError before anything starts (a size from the inventory is not trusted). If
    ffmpeg ends with fewer frames, the next one is a `ToolError` that says how many came; if it
    takes more than `deadline_s` to deliver a frame it is killed and that is a `ToolError` too.
    Every wait for the process has a deadline, `CLOSE_WAIT_S` (001.21, point 7): after the last
    frame, or when ffmpeg closes its output, and when leaving the `with` (spec 0.8). A process
    still running then is killed and reported, never left behind and never waited for forever.
    """

    def __init__(
        self,
        path: Path,
        start_f: int,
        count: int,
        fps: int,
        size: tuple[int, int],
        *,
        pre_filters: str = "",
        rgb_filters: str = "",
        deadline_s: float = FRAME_DEADLINE_S,
        log: Path | None,
    ) -> None:
        width, height = size
        if width < 1 or height < 1 or width * height * _CHANNELS > MAX_FRAME_BYTES:
            raise ProjectError(
                f"un frame de {width} x {height} pasa de {MAX_FRAME_BYTES // 2**20} MB; "
                "el tamaño del proxy no es el que kcut ingest da; corre kcut ingest"
            )
        self._count = count
        self._width, self._height = width, height
        self._given = 0
        self._deadline_s = deadline_s
        self._expired = False
        args = reader_args(
            proc.tool_path("ffmpeg"),
            seek_input(path, start_f, fps, size),
            count,
            pre_filters=pre_filters,
            rgb_filters=rgb_filters,
        )
        self._child = proc.popen(args, stdout_pipe=True, log=log, grace_s=CLOSE_WAIT_S)

    def __enter__(self) -> Self:
        self._child.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._child.__exit__(exc_type, exc, tb)

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> NDArray[np.uint8]:
        if self._given >= self._count:
            raise StopIteration
        buffer = self._read_frame(self._width * self._height * _CHANNELS)
        if buffer is None:
            self._child.wait(timeout_s=CLOSE_WAIT_S)  # ffmpeg closed its output: it ends, or dies
            if self._expired:
                raise ToolError(
                    f"ffmpeg no entregó el frame {self._given + 1} en {self._deadline_s:g} s; "
                    "se mató"
                )
            tail = self._child.stderr_tail()
            detail = f". Últimas líneas de stderr:\n{tail}" if tail else ""
            raise ToolError(
                f"ffmpeg entregó {self._given} de {self._count} frames del video{detail}"
            )
        self._given += 1
        return np.frombuffer(buffer, dtype=np.uint8).reshape(self._height, self._width, _CHANNELS)

    def _read_frame(self, size: int) -> bytearray | None:
        """`size` bytes from ffmpeg in one buffer, or None if it ends (or is killed for being
        slow) before. A timer kills the process if the frame is not there in time."""
        stream = self._child.stdout
        if stream is None:
            raise ToolError("el lector de frames no tiene salida")
        source = cast(io.BufferedReader, stream)
        buffer = bytearray(size)
        view = memoryview(buffer)
        self._expired = False
        timer = threading.Timer(self._deadline_s, self._expire)
        timer.daemon = True
        timer.start()
        try:
            got = 0
            while got < size:
                step = source.readinto(view[got:])
                if not step:
                    return None
                got += step
        finally:
            timer.cancel()
        return buffer

    def _expire(self) -> None:
        """The deadline passed: kill ffmpeg, so the read that waits on it comes back."""
        self._expired = True
        self._child.kill()


def grab(
    path: Path,
    f: int,
    fps: int,
    size: tuple[int, int],
    *,
    rgb_filters: str = "",
    log: Path | None,
) -> NDArray[np.uint8]:
    """One BGR frame: index `f` of the file."""
    with FrameReader(path, f, 1, fps, size, rgb_filters=rgb_filters, log=log) as reader:
        return next(reader)
