"""Read and write mono audio: 16-bit wav via stdlib `wave`, raw float32 for intermediates (DS4)."""

import contextlib
import os
import struct
import wave
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

import numpy as np
from numpy.typing import NDArray

from kcut.errors import ProjectError
from kcut.jsonio import refuse_directory

_S16_FULL_SCALE = 32768.0
PEAK_BLOCK_FRAMES = 1_048_576
# Templates: `{label}` is the phrase that names the file ("el wav48 de a1"), never its path (the
# path has the slug of the original name of the clip, which may hold a phone number; 001.28)
TRUNCATED_WAV = "{label} está truncado o su cabecera miente; corre kcut ingest"
TOO_MANY_CHUNKS = "{label} tiene demasiados bloques antes de los datos; corre kcut ingest"
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


def _reason(exc: Exception) -> str:
    """Why a read failed, in words and with no path: `strerror` of an `OSError`, the text of an
    `EOFError` or of a `wave.Error`, or the name of the class if there is no text. Any other error
    says only its class: the path can be in `str(exc)`, and the name of the file has a phone number
    in it now and then (001.28, point 2)."""
    if isinstance(exc, OSError):
        return exc.strerror or type(exc).__name__
    if isinstance(exc, EOFError | wave.Error):
        return str(exc) or type(exc).__name__
    return type(exc).__name__


def check_wav_extent(path: Path, *, label: str = "el wav") -> None:
    """ProjectError unless the `data` chunk the header declares fits in the real file.

    A header can say "3 GiB" in a 100-byte file and `wave` believes it: `readframes` would ask for
    that much memory (spec 001.14, point 4). The declared size is compared with the size of the
    file before anything is read, and it must be a whole number of sample frames. Only chunk
    headers are read, at most `MAX_CHUNKS`. A file that is not RIFF/WAVE is left to `wave`, which
    says why.

    `label` is the phrase that names the file in the messages (never its path: 001.28, point 2).
    """
    try:
        with path.open("rb") as handle:
            lies = _data_lies(handle, os.fstat(handle.fileno()).st_size, label)
    except OSError as exc:
        raise ProjectError(f"no pude leer {label}: {_reason(exc)}") from None
    if lies:
        raise ProjectError(TRUNCATED_WAV.format(label=label))


def _data_lies(handle: BinaryIO, size: int, label: str) -> bool:
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
    raise ProjectError(TOO_MANY_CHUNKS.format(label=label))


class WavReader:
    """The part of `wave.Wave_read` the readers use. What `wave` raises when it opens the file or
    reads frames is a ProjectError; the rest of the body is the caller's code (spec 001.17, 7)."""

    def __init__(self, wav: wave.Wave_read, label: str) -> None:
        self._wav, self._label = wav, label

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
            raise _unreadable(self._label, exc) from None

    def setpos(self, pos: int) -> None:
        try:
            self._wav.setpos(pos)
        except _WAVE_ERRORS as exc:
            raise _unreadable(self._label, exc) from None


def _unreadable(label: str, exc: Exception) -> ProjectError:
    return ProjectError(f"no pude leer {label}: {_reason(exc)}")


def _require_mono_s16(wav: WavReader, label: str) -> None:
    channels, width = wav.getnchannels(), wav.getsampwidth()
    if channels != 1 or width != 2:
        raise ProjectError(
            f"{label}: se esperaba un wav mono de 16 bits "
            f"(tiene {channels} canales y {width * 8} bits)"
        )


@contextmanager
def open_wav(path: Path, *, label: str = "el wav") -> Iterator[WavReader]:
    """The wav opened for reading, after `check_wav_extent`. Only what `wave.open`, `readframes`
    and the check raise becomes a ProjectError; a bug in the body of the `with` keeps its type
    (and, at the end of the run, its traceback in the log). `label` names the file in the
    messages, never its path (001.28, point 2)."""
    check_wav_extent(path, label=label)
    try:
        wav = wave.open(str(path), "rb")  # noqa: SIM115  (closed below; an open error is told apart)
    except _WAVE_ERRORS as exc:
        raise _unreadable(label, exc) from None
    try:
        yield WavReader(wav, label)
    finally:
        wav.close()


def read_wav_s16_mono(path: Path, *, label: str = "el wav") -> tuple[NDArray[np.float32], int]:
    """Read a mono 16-bit wav as float32 in [-1, 1) plus its sample rate."""
    with open_wav(path, label=label) as wav:
        _require_mono_s16(wav, label)
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    return samples / np.float32(_S16_FULL_SCALE), rate


def read_wav_range(
    path: Path, start: int, count: int, *, label: str = "el wav"
) -> tuple[NDArray[np.float32], int]:
    """Samples `[start, min(start + count, n))` of a mono 16-bit wav as float32 in [-1, 1), and
    its sample rate (spec 001.15, T7). `n` is the number of frames of the file.

    `start` or `count` under 0 is a ValueError (a bug of the caller). The header is checked
    against the real file first (`open_wav`, spec 001.14 point 4), so `n` can be trusted;
    `start >= n` gives an empty array. It seeks with `setpos` and reads once, `min(count,
    n - start)` frames: it never reads or reserves more than that, however long the file is."""
    if start < 0 or count < 0:
        raise ValueError(f"start y count no pueden ser negativos (start={start}, count={count})")
    with open_wav(path, label=label) as wav:
        _require_mono_s16(wav, label)
        rate = wav.getframerate()
        take = min(count, wav.getnframes() - start)
        if take <= 0:
            return np.zeros(0, dtype=np.float32), rate
        wav.setpos(start)
        raw = wav.readframes(take)
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    return samples / np.float32(_S16_FULL_SCALE), rate


def wav_duration_ms(path: Path, *, label: str = "el wav") -> int:
    """Real length of a wav in whole milliseconds, from its header (`nframes / rate`)."""
    with open_wav(path, label=label) as wav:
        rate = wav.getframerate()
        if rate <= 0:
            raise ProjectError(f"{label}: la frecuencia de muestreo es {rate}")
        return (wav.getnframes() * 1000) // rate


def wav_peak(path: Path, block_frames: int = PEAK_BLOCK_FRAMES, *, label: str = "el wav") -> float:
    """Linear peak (0..1) of a mono 16-bit wav, read `block_frames` at a time (flat memory)."""
    peak = 0
    with open_wav(path, label=label) as wav:
        _require_mono_s16(wav, label)
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


def read_f32(path: Path, *, label: str = "el audio") -> NDArray[np.float32]:
    """Read raw float32 little-endian mono samples. `label` names the file in the messages, never
    its path (001.28, point 2)."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ProjectError(f"no pude leer {label}: {_reason(exc)}") from None
    if len(data) % 4 != 0:
        raise ProjectError(f"{label}: tamaño inválido para float32 ({len(data)} bytes)")
    return np.frombuffer(data, dtype="<f4").astype(np.float32)


def write_f32(path: Path, x: NDArray[np.float32]) -> None:
    """Write raw float32 little-endian mono samples (no clipping: peaks survive until loudnorm)."""
    write_f32_blocks(path, [x])


def write_f32_blocks(path: Path, blocks: Iterable[NDArray[np.float32]]) -> None:
    """Write the blocks, one after the other, as raw float32 little-endian mono samples.

    Never in place (001.25, point 3): the samples go to `<name>.<pid>.partial`, created new, and
    `os.replace` puts the finished file over `path`. A hard link or a link planted at `path` is
    replaced and not written through, and two processes do not write the same partial. Only one
    block is in memory at a time. A folder at `path` or at the partial, a file that cannot be
    deleted or replaced, and a disk that fails are a ProjectError; the partial is never left.

    What fails while a block is being made (`blocks` reads a wav) is not a failure to write: an
    `OSError` from `blocks` is a ProjectError that says it could not read (001.26, point 6).
    """
    refuse_directory(path)
    partial = path.with_name(f"{path.name}.{os.getpid()}.partial")
    refuse_directory(partial)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial.unlink(missing_ok=True)  # never write through a stale file or a planted link
        with partial.open("xb") as handle:
            for block in _made(blocks):
                handle.write(np.asarray(block, dtype="<f4").tobytes())
        os.replace(partial, path)
    except PermissionError:
        raise ProjectError(f"cierra el archivo {path} en el reproductor y repite") from None
    except OSError as exc:
        raise ProjectError(f"no pude escribir {path}: {exc}") from None
    finally:
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)


def _made(blocks: Iterable[NDArray[np.float32]]) -> Iterator[NDArray[np.float32]]:
    """`blocks`, one by one; an `OSError` that makes one of them is a ProjectError about reading,
    so `write_f32_blocks` does not call it a write. The message has no path: the one in the error
    can carry the name of the original clip, with a phone number in it (001.27, point 9)."""
    iterator = iter(blocks)
    while True:
        try:
            block = next(iterator)
        except StopIteration:
            return
        except OSError as exc:
            reason = exc.strerror or type(exc).__name__
            raise ProjectError(f"no pude leer el audio de entrada: {reason}") from None
        yield block
