"""Read and write mono audio: 16-bit wav via stdlib `wave`, raw float32 for intermediates (DS4)."""

import os
import struct
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

import numpy as np
from numpy.typing import NDArray

from kcut.errors import ProjectError

_S16_FULL_SCALE = 32768.0
PEAK_BLOCK_FRAMES = 1_048_576
TRUNCATED_WAV = "el wav16 está truncado o su cabecera miente; corre kcut ingest"
TOO_MANY_CHUNKS = "el wav16 tiene demasiados bloques antes de los datos; corre kcut ingest"
MAX_CHUNKS = 256  # chunks looked at before `data`: a real wav has two or three
# Everything `wave` (or the code around it) may raise on a file that is not what its header says
_WAVE_ERRORS = (
    wave.Error,
    EOFError,
    OSError,
    RuntimeError,  # `wave.Chunk.seek` raises it when a chunk size runs past the end
    ValueError,
    OverflowError,
    ZeroDivisionError,
    struct.error,
)


def check_wav_extent(path: Path) -> None:
    """ProjectError unless the `data` chunk the header declares fits in the real file.

    A header can say "3 GiB" in a 100-byte file and `wave` believes it: `readframes` would ask for
    that much memory (spec 001.14, point 4). The declared size is compared with the size of the
    file before anything is read, and it must be a whole number of sample frames. Only chunk
    headers are read, at most `MAX_CHUNKS`. A file that is not RIFF/WAVE is left to `wave`, which
    says why.
    """
    try:
        with path.open("rb") as handle:
            lies = _data_lies(handle, os.fstat(handle.fileno()).st_size)
    except OSError as exc:
        raise ProjectError(f"no pude leer el wav {path}: {exc}") from None
    if lies:
        raise ProjectError(TRUNCATED_WAV)


def _data_lies(handle: BinaryIO, size: int) -> bool:
    """True if a chunk runs past the end of the file or of what the RIFF header says (spec
    001.16, point 7), if the `fmt ` is missing, short or empty, or if the `data` chunk is not a
    whole number of sample frames. The frame is `channels x bytes of a sample`, from the `fmt `:
    the `block_align` it also holds is one more thing a header can lie about."""
    riff = handle.read(12)
    if riff[8:] != b"WAVE":
        return False
    limit = min(size, 8 + int.from_bytes(riff[4:8], "little"))
    frame = 0  # bytes per sample frame, known once the `fmt ` has been read
    for _ in range(MAX_CHUNKS):
        head = handle.read(8)
        if len(head) < 8:
            return False  # no `data` chunk at all: `wave` says so
        name, length = head[:4], int.from_bytes(head[4:], "little")
        start = handle.tell()
        if start + length > limit:
            return True
        if name == b"fmt ":
            if length < 16:
                return True
            body = handle.read(16)
            frame = int.from_bytes(body[2:4], "little") * (
                (int.from_bytes(body[14:16], "little") + 7) // 8
            )
        elif name == b"data":
            return frame == 0 or length % frame != 0
        handle.seek(start + length + (length & 1))  # chunks are padded to an even size
    raise ProjectError(TOO_MANY_CHUNKS)


class WavReader:
    """The part of `wave.Wave_read` the readers use. What `wave` raises when it opens the file or
    reads frames is a ProjectError; the rest of the body is the caller's code (spec 001.17, 7)."""

    def __init__(self, wav: wave.Wave_read, path: Path, label: str) -> None:
        self._wav, self._path, self._label = wav, path, label

    def getnchannels(self) -> int:
        return self._wav.getnchannels()

    def getsampwidth(self) -> int:
        return self._wav.getsampwidth()

    def getframerate(self) -> int:
        return self._wav.getframerate()

    def getnframes(self) -> int:
        return self._wav.getnframes()

    def readframes(self, count: int) -> bytes:
        try:
            return self._wav.readframes(count)
        except _WAVE_ERRORS as exc:
            raise _unreadable(self._label, self._path, exc) from None


def _unreadable(label: str, path: Path, exc: Exception) -> ProjectError:
    return ProjectError(f"no pude leer el {label} {path}: {exc}")


@contextmanager
def open_wav(path: Path, label: str = "wav") -> Iterator[WavReader]:
    """The wav opened for reading, after `check_wav_extent`. Only what `wave.open`, `readframes`
    and the check raise becomes a ProjectError; a bug in the body of the `with` keeps its type
    (and, at the end of the run, its traceback in the log)."""
    check_wav_extent(path)
    try:
        wav = wave.open(str(path), "rb")  # noqa: SIM115  (closed below; an open error is told apart)
    except _WAVE_ERRORS as exc:
        raise _unreadable(label, path, exc) from None
    try:
        yield WavReader(wav, path, label)
    finally:
        wav.close()


def read_wav_s16_mono(path: Path) -> tuple[NDArray[np.float32], int]:
    """Read a mono 16-bit wav as float32 in [-1, 1) plus its sample rate."""
    with open_wav(path) as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        if channels != 1 or width != 2:
            raise ProjectError(
                f"{path}: se esperaba un wav mono de 16 bits "
                f"(tiene {channels} canales y {width * 8} bits)"
            )
        raw = wav.readframes(wav.getnframes())
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    return samples / np.float32(_S16_FULL_SCALE), rate


def wav_duration_ms(path: Path) -> int:
    """Real length of a wav in whole milliseconds, from its header (`nframes / rate`)."""
    with open_wav(path) as wav:
        rate = wav.getframerate()
        if rate <= 0:
            raise ProjectError(f"no pude leer el wav {path}: la frecuencia de muestreo es {rate}")
        return (wav.getnframes() * 1000) // rate


def wav_peak(path: Path, block_frames: int = PEAK_BLOCK_FRAMES) -> float:
    """Linear peak (0..1) of a mono 16-bit wav, read `block_frames` at a time (flat memory)."""
    peak = 0
    with open_wav(path) as wav:
        channels, width = wav.getnchannels(), wav.getsampwidth()
        if channels != 1 or width != 2:
            raise ProjectError(
                f"{path}: se esperaba un wav mono de 16 bits "
                f"(tiene {channels} canales y {width * 8} bits)"
            )
        while block := wav.readframes(block_frames):
            samples = np.frombuffer(block, dtype="<i2").astype(np.int32)
            peak = max(peak, int(np.max(np.abs(samples))))
    return peak / _S16_FULL_SCALE


def write_wav_s16_mono(path: Path, x: NDArray[np.float32], sr: int) -> None:
    """Write mono 16-bit wav; values are clipped to [-1, 1] first."""
    clipped = np.clip(np.asarray(x, dtype=np.float64), -1.0, 1.0)
    pcm = np.round(clipped * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())


def read_f32(path: Path) -> NDArray[np.float32]:
    """Read raw float32 little-endian mono samples."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ProjectError(f"no pude leer {path}: {exc}") from None
    if len(data) % 4 != 0:
        raise ProjectError(f"{path}: tamaño inválido para float32 ({len(data)} bytes)")
    return np.frombuffer(data, dtype="<f4").astype(np.float32)


def write_f32(path: Path, x: NDArray[np.float32]) -> None:
    """Write raw float32 little-endian mono samples (no clipping: peaks survive until loudnorm)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(np.asarray(x, dtype="<f4").tobytes())
