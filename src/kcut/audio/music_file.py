"""The music of `mode: file`: a song of `recursos/`, decoded and laid on the length of the video
(spec S1.8b, 001.15; the song has to be approved in the manifest, DS9).

`ffmpeg` decodes it to raw float32 mono at 48 kHz into stdout, from `src_in_f` on (`-ss` before
`-i`) and no more than the video needs plus one second (`-t`: it bounds what is decoded and what
comes to memory). The block `B` that comes back already starts at `src_in_f`. With `loop` and a `B`
shorter than the video, `B` is repeated one after the other up to `total`; without it, `B` is
followed by zeros and M06 says so. Then a linear fade in from the first sample and a linear fade out
that ends in the last one.
"""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from kcut import proc
from kcut.audio.music_model import FileCfg
from kcut.errors import CheckFailed
from kcut.ff.args import fnum
from kcut.issues import Issue
from kcut.paths import resolve_in_project
from kcut.project import Project
from kcut.recursos.manifest import require_approved
from kcut.timebase import SAMPLE_RATE

Track = NDArray[np.float32]
M06 = "el archivo de música es más corto que el video y no tiene loop: el resto queda en silencio"
EMPTY = "el archivo de música no tiene audio desde src_in_f"
_TIMEOUT_FLOOR_S = 60.0
_TIMEOUT_PER_AUDIO_S = 10.0


def music_args(ffmpeg: Path, path: Path, src_in_f: int, fps: int, total: int) -> list[str]:
    """The `ffmpeg` that decodes the song: from `src_in_f / fps` seconds, `total / 48000 + 1` of
    them at most, first audio stream, mono, 48 kHz, raw float32 into stdout. The song is opened
    with `-protocol_whitelist file` right before `-i` (001.37, point 8): whatever the file says (a
    playlist that names an address, a `concat:`), `ffmpeg` opens files only."""
    return [
        str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error",
        "-ss", fnum(src_in_f / fps), "-t", fnum(total / SAMPLE_RATE + 1),
        "-protocol_whitelist", "file", "-i", str(path),
        "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-",
    ]  # fmt: skip


def load_music_file(
    project: Project,
    cfg: FileCfg,
    total: int,
    spf: int,
    *,
    log: Path | None = None,
    issues: list[Issue] | None = None,
) -> Track:
    """The song of `cfg` as exactly `total` samples of float32 mono at 48 kHz.

    The song must be approved first (`require_approved`: a GateError, M04, exit 5, if it is not).
    A song with no audio from `src_in_f` on is a CheckFailed. Without `loop`, a song that ends
    before the video adds M06 (a warning) to `issues` and is followed by zeros. `spf` gives the
    frames per second (`48000 // spf`) and the length of the fades in samples."""
    item = require_approved(project, cfg.path)  # M04: a GateError if it is not in the manifest
    path = resolve_in_project(project.root, item.file)
    fps = SAMPLE_RATE // spf
    timeout = _TIMEOUT_PER_AUDIO_S * (total / SAMPLE_RATE + 1) + _TIMEOUT_FLOOR_S
    args = music_args(proc.tool_path("ffmpeg"), path, cfg.src_in_f, fps, total)
    raw = proc.run(args, log=log, timeout_s=timeout).stdout
    block = np.frombuffer(raw[: len(raw) // 4 * 4], dtype="<f4").astype(np.float32)
    if block.size == 0:
        raise CheckFailed(EMPTY)
    track = _fit(block, total, loop=cfg.loop, issues=issues)
    return _fades(track, cfg.fade_in_f * spf, cfg.fade_out_f * spf)


def _fit(block: Track, total: int, *, loop: bool, issues: list[Issue] | None) -> Track:
    """`block` cut or made up to `total` samples: repeated if `loop`, else with zeros and M06."""
    if block.size >= total:
        return block[:total].copy()
    if loop:
        return np.tile(block, -(-total // block.size))[:total].astype(np.float32)
    if issues is not None:
        issues.append(Issue("M06", "warning", "file", M06))
    return np.concatenate([block, np.zeros(total - block.size, dtype=np.float32)])


def _fades(track: Track, fade_in: int, fade_out: int) -> Track:
    """`track` times a linear ramp from 0 to 1 over its first `fade_in` samples and one from 1 to 0
    over its last `fade_out` (each at most as long as the track)."""
    out = track.copy()
    n_in, n_out = min(fade_in, out.size), min(fade_out, out.size)
    if n_in > 0:
        out[:n_in] *= np.linspace(0, 1, n_in, dtype=np.float32)
    if n_out > 0:
        out[out.size - n_out :] *= np.linspace(1, 0, n_out, dtype=np.float32)
    return out
