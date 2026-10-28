"""The voice of the cut, sample by sample (spec S1.5b; technique of `piloto/audio.py`).

The track has exactly `frames * spf` samples (`spf = 48000 // fps`). Each voice clip puts the
samples `[in_f * spf, out_f * spf)` of the 48 kHz wav of its source at `at_f * spf`, with a linear
fade of 5 ms at each edge so a cut does not click. Two clips that follow each other in the
source (the second starts where the first ended, same clip) are one continuous sound: no fade
between them. Clock of the source: spec 0.6; the sample `in_f * spf` is the instant `in_f / fps`.

The track is made in blocks of at most 60 s (`voice_blocks`) so that an hour of voice never has to
be in memory at once: `write_voice` writes them one after the other, and `build_voice` (pure, for
the tests) joins them. A clip that crosses the edge of a block is read and faded in two pieces
that give the same samples as one (001.25, point 5).
"""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from kcut.audio.wavio import read_wav_range, write_f32_blocks
from kcut.edl.model import Edl, VoiceClip
from kcut.errors import CheckFailed, ProjectError
from kcut.ingest import workfiles
from kcut.ingest.inventory import Inventory
from kcut.project import Project
from kcut.timebase import spf as samples_per_frame

SAMPLE_RATE = 48000
FADE_SAMPLES = 240  # 5 ms at 48 kHz
BLOCK_SAMPLES = 60 * SAMPLE_RATE  # the most a block holds: 60 s
SPARE_BYTES = 1 << 30  # what has to stay free on the disk besides the voice track: 1 GiB
# What `kcut mix` leaves in `build/vN` for each sample of the cut (001.37, point 4): seven files of
# raw float32 (28 bytes), `mix.wav` of 16 bits (2) and the partial file in progress (4)
MIX_BYTES_PER_SAMPLE = 34


@dataclass(frozen=True)
class _Placed:
    """A voice clip on the track: where it lands (`at`), which samples of its wav it takes
    (`start`, and `count` of them) and which edges are joined to the clip before or after."""

    index: int
    clip: VoiceClip
    at: int
    start: int
    count: int
    joined_before: bool
    joined_after: bool


def build_voice(
    project: Project, edl: Edl, inv: Inventory, log: Path | None
) -> NDArray[np.float32]:
    """The voice track of `edl` as float32 mono at 48 kHz, `edl.frames * spf` samples long.

    The same samples `write_voice` writes, all in memory: for the tests, not for the render."""
    track = np.zeros(edl.frames * samples_per_frame(edl.fps), dtype=np.float32)
    done = 0
    for block in voice_blocks(project, edl, inv, log):
        track[done : done + len(block)] = block
        done += len(block)
    return track


def require_disk_space(folder: Path, edl: Edl, *, layer_bytes: int = 0) -> None:
    """ProjectError, which says how many bytes are missing, unless the disk of `folder` has room
    for the voice track of `edl` (`frames * spf * 4` bytes of float32), the graphics layer that is
    going to be captured (`layer_bytes`, 0 if there is none to make) and `SPARE_BYTES` more. It
    is asked before the mezzanines are made, so a full disk is told at the start and not half way
    through the render (001.25, point 5; the layer: 001.31, point 5).

    The figures go before the path: `cli` cuts a message to 300 characters, and in a deep folder
    the cut used to take the figure away (001.30, point 4). Without a layer the message is the one
    it always was; with one it says so."""
    needed = edl.frames * samples_per_frame(edl.fps) * 4 + layer_bytes + SPARE_BYTES
    free = shutil.disk_usage(folder).free
    if free < needed:
        asks = "la voz del corte, la capa de gráficos y 1 GiB libre"
        if layer_bytes <= 0:
            asks = "la voz del corte y 1 GiB libre"
        raise ProjectError(
            f"no hay espacio en el disco: faltan {needed - free} bytes ({asks} piden {needed}, "
            f"hay {free}) en {folder}"
        )


def require_mix_space(folder: Path, edl: Edl) -> None:
    """ProjectError, which says how many bytes are missing, unless the disk of `folder` has room
    for the mix of `edl` (`MIX_BYTES_PER_SAMPLE` for each sample of the cut) and `SPARE_BYTES` more
    (001.37, point 4). It is asked before `kcut mix` writes anything: a video of 10 minutes takes
    almost 1 GB, one of an hour about 6 GB, and a full disk used to be told after minutes of work.
    The figures go before the path (001.30, point 4), as in `require_disk_space`."""
    needed = edl.frames * samples_per_frame(edl.fps) * MIX_BYTES_PER_SAMPLE + SPARE_BYTES
    free = shutil.disk_usage(folder).free
    if free < needed:
        raise ProjectError(
            f"no hay espacio en el disco: faltan {needed - free} bytes (la mezcla y 1 GiB libre "
            f"piden {needed}, hay {free}) en {folder}"
        )


def write_voice(
    project: Project,
    edl: Edl,
    inv: Inventory,
    dst: Path,
    log: Path | None,
    *,
    block_samples: int = BLOCK_SAMPLES,
) -> None:
    """Write the voice track of `edl` to `dst` as raw float32 (`write_f32_blocks`: through a
    partial file and `os.replace`), one block of at most `block_samples` samples at a time."""
    write_f32_blocks(dst, voice_blocks(project, edl, inv, log, block_samples))


def voice_blocks(
    project: Project,
    edl: Edl,
    inv: Inventory,
    log: Path | None,
    block_samples: int = BLOCK_SAMPLES,
) -> Iterator[NDArray[np.float32]]:
    """The voice track in order, `block_samples` samples at a time (the last one is shorter).

    Each clip reads only its own samples (`read_wav_range`), never the whole wav, and only the
    part that falls in the block. If a wav48 has fewer samples than a clip asks for, that is a
    CheckFailed (exit 1): the audio is not what the EDL expected, and the user is told which clip
    and what to do."""
    if block_samples < 1:
        raise ValueError(f"block_samples tiene que ser positivo (vino {block_samples})")
    spf = samples_per_frame(edl.fps)
    placed = _placed(edl, spf)
    wavs: dict[str, Path] = {}
    total = edl.frames * spf
    for begin in range(0, total, block_samples):
        end = min(total, begin + block_samples)
        block = np.zeros(end - begin, dtype=np.float32)
        for item in placed:
            low, high = max(item.at, begin), min(item.at + item.count, end)
            if low >= high:
                continue
            src = item.clip.src
            if src not in wavs:
                wavs[src] = _wav48(project, inv, src, log)
            inside = low - item.at  # where in the clip this piece starts
            samples = _read(wavs[src], item, inside, high - low)
            block[low - begin : high - begin] = _faded(samples, item, inside)
        yield block


def _placed(edl: Edl, spf: int) -> list[_Placed]:
    """Each voice clip with its place and whether each of its edges joins the next or last clip."""
    clips = list(edl.clips)
    found: list[_Placed] = []
    previous: VoiceClip | None = None
    for i, clip in enumerate(clips):
        if not isinstance(clip, VoiceClip):
            previous = None
            continue
        following = clips[i + 1] if i + 1 < len(clips) else None
        joined_after = isinstance(following, VoiceClip) and _continues(clip, following)
        start, count = clip.in_f * spf, (clip.out_f - clip.in_f) * spf
        joined_before = _continues(previous, clip)
        found.append(_Placed(i, clip, clip.at_f * spf, start, count, joined_before, joined_after))
        previous = clip
    return found


def _read(wav: Path, item: _Placed, inside: int, count: int) -> NDArray[np.float32]:
    """`count` samples of the clip from its sample `inside`, as float32."""
    src = item.clip.src
    start = item.start + inside
    # `wavio` names the file by the phrase it is given, never by its path: the name of the wav48
    # carries the slug of the original clip, which may hold a phone number (001.28, point 2). A
    # wav that was deleted or locked while the track is written comes out as a ProjectError.
    samples, rate = read_wav_range(wav, start, count, label=f"el wav48 de {src}")
    if rate != SAMPLE_RATE:
        raise ProjectError(f"el wav48 de {src} está a {rate} Hz; corre kcut ingest")
    if len(samples) < count:
        have, wants = start + len(samples), item.start + item.count
        raise CheckFailed(
            f"el wav48 de {src} tiene {have} muestras y clips[{item.index}] pide hasta {wants}; "
            "corre kcut ingest o acorta el clip"
        )
    return samples


def _continues(before: VoiceClip | None, after: VoiceClip) -> bool:
    """Does `after` take up the source where `before` left it (same clip, `in_f == out_f`)?"""
    return before is not None and before.src == after.src and before.out_f == after.in_f


def _faded(samples: NDArray[np.float32], item: _Placed, inside: int) -> NDArray[np.float32]:
    """`samples` (the piece of the clip that starts at its sample `inside`) with the part of the
    fade in and of the fade out of `FADE_SAMPLES` (less if the clip is shorter than twice that)
    that falls in it, except at an edge that is joined to the next clip. Each sample is multiplied
    by the same number as if the clip were all in one piece."""
    out = samples.copy()
    n = min(FADE_SAMPLES, item.count // 2)
    if n == 0:
        return out
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    end = inside + len(out)
    if not item.joined_before and inside < n:
        stop = min(n, end)
        out[: stop - inside] *= ramp[inside:stop]
    tail = item.count - n  # the fade out is the last `n` samples of the clip
    if not item.joined_after and end > tail:
        first = max(tail, inside)
        out[first - inside :] *= ramp[::-1][first - tail : end - tail]
    return out


def _wav48(project: Project, inv: Inventory, src: str, log: Path | None) -> Path:
    clip = inv.by_id(src)
    if clip is None or clip.audio is None:
        raise ProjectError(f"el clip {src} no tiene audio; corre kcut edl check")
    return workfiles.ensure_wav48(project, clip, log)
