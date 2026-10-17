"""Read and write mono audio: 16-bit wav via stdlib `wave`, raw float32 for intermediates (DS4)."""

import wave
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from kcut.errors import ProjectError

_S16_FULL_SCALE = 32768.0
PEAK_BLOCK_FRAMES = 1_048_576


def read_wav_s16_mono(path: Path) -> tuple[NDArray[np.float32], int]:
    """Read a mono 16-bit wav as float32 in [-1, 1) plus its sample rate."""
    try:
        with wave.open(str(path), "rb") as wav:
            channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
            if channels != 1 or width != 2:
                raise ProjectError(
                    f"{path}: se esperaba un wav mono de 16 bits "
                    f"(tiene {channels} canales y {width * 8} bits)"
                )
            raw = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError, OSError) as exc:
        raise ProjectError(f"no pude leer el wav {path}: {exc}") from None
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    return samples / np.float32(_S16_FULL_SCALE), rate


def wav_duration_ms(path: Path) -> int:
    """Real length of a wav in whole milliseconds, from its header (`nframes / rate`)."""
    try:
        with wave.open(str(path), "rb") as wav:
            return (wav.getnframes() * 1000) // wav.getframerate()
    except (wave.Error, EOFError, OSError, ZeroDivisionError) as exc:
        raise ProjectError(f"no pude leer el wav {path}: {exc}") from None


def wav_peak(path: Path, block_frames: int = PEAK_BLOCK_FRAMES) -> float:
    """Linear peak (0..1) of a mono 16-bit wav, read `block_frames` at a time (flat memory)."""
    peak = 0
    try:
        with wave.open(str(path), "rb") as wav:
            channels, width = wav.getnchannels(), wav.getsampwidth()
            if channels != 1 or width != 2:
                raise ProjectError(
                    f"{path}: se esperaba un wav mono de 16 bits "
                    f"(tiene {channels} canales y {width * 8} bits)"
                )
            while block := wav.readframes(block_frames):
                samples = np.frombuffer(block, dtype="<i2").astype(np.int32)
                peak = max(peak, int(np.max(np.abs(samples))))
    except (wave.Error, EOFError, OSError) as exc:
        raise ProjectError(f"no pude leer el wav {path}: {exc}") from None
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
