"""The mix of the video (spec S1.8b, 001.15): the voice brought to a level, the music under it with
ducking, the sound effects, all summed and brought to the level of the delivery.

Everything is raw float32 mono at 48 kHz (DS4), in `.kcut/build/vN/`, and nothing is clipped until
`loudnorm` has put the peak where it goes. The steps, each file written through a partial one:

1. `voice_raw.f32`: the voice of the cut (`write_voice`);
2. `voice_chain.f32` (high-pass, noise reduction, compressor) and `voice.f32` (`loudnorm` in two
   passes to `voice_lufs`, with a true peak of -2.0);
3. `music.f32`: the music (`synth` or `file`) with its `gain_db` and its windows;
4. `sfx.f32`: the effects with `bus_gain_db` and their windows;
5. `mix_pre.f32` (the graph of `mix_graph`) and `mix.f32` (`loudnorm` to `target_lufs` and
   `target_tp`);
6. `mix.wav`: 16 bits mono, from `mix.f32`.

After each `ffmpeg` the file is made exactly `frames * spf` samples long: zeros if it is short, cut
if it is long; a difference of more than one frame is an InternalError.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from kcut import proc
from kcut.audio.gain import apply_gain_windows
from kcut.audio.loudnorm import normalize
from kcut.audio.mix_graph import build_graph
from kcut.audio.music_file import load_music_file
from kcut.audio.music_model import NO_MUSIC, MusicDoc
from kcut.audio.music_synth import synth_music
from kcut.audio.sfx_bus import build_sfx_bus
from kcut.audio.sfx_events import SfxEvent
from kcut.audio.voice_track import write_voice
from kcut.audio.wavio import read_f32, write_f32, write_wav_s16_mono
from kcut.config.model import VoiceChain
from kcut.console import Progress
from kcut.edl.model import Edl
from kcut.errors import InternalError, ProjectError
from kcut.ff.args import fnum
from kcut.ingest.cache_guard import assert_in_cache, assert_own_folder, build_folder
from kcut.ingest.inventory import Inventory, Notice
from kcut.issues import Issue
from kcut.jsonio import refuse_directory
from kcut.project import Project
from kcut.render.lock import atomic_replace, discard_partial, prepare_partial
from kcut.timebase import SAMPLE_RATE
from kcut.timebase import spf as samples_per_frame

Track = NDArray[np.float32]
ArgsFor = Callable[[Path], list[str]]
STEPS = 7  # what `progress` counts
VOICE_TP = -2.0  # the true peak of the voice, before it goes into the mix
NO_MEMORY = "no hay memoria para sintetizar los efectos"
NO_MEMORY_MIX = "no hay memoria para mezclar el audio"
FILES = (
    "voice_raw.f32", "voice_chain.f32", "voice.f32", "music.f32", "sfx.f32",
    "mix_pre.f32", "mix.f32", "mix.wav",
)  # fmt: skip
_F32_IN = ["-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", "1"]
_F32_OUT = ["-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", "1"]
_TIMEOUT_FLOOR_S = 60.0
_TIMEOUT_PER_AUDIO_S = 10.0


@dataclass(frozen=True)
class AudioPlan:
    """What `mix` needs of `sfx.json` and `music.json`, already read and resolved: the events in
    frames of the output, the gain of their bus and its windows `(start_f, end_f, gain_db)`, and the
    music (`NO_MUSIC` if there is no `edit/music.json`)."""

    events: tuple[SfxEvent, ...] = ()
    bus_gain_db: float = 0.0
    sfx_windows: tuple[tuple[int, int, float], ...] = ()
    music: MusicDoc = NO_MUSIC


def voice_chain(cfg: VoiceChain) -> str:
    """The filters on the voice: `highpass=f=HP`, `afftdn=nr=NR:nf=NF` (left out with
    `denoise_nr == 0`: `afftdn` does not take less than 0.01) and an `acompressor` whose threshold
    is `comp_threshold_db` as a linear factor."""
    parts = [f"highpass=f={cfg.highpass_hz}"]
    if cfg.denoise_nr > 0:
        parts.append(f"afftdn=nr={fnum(cfg.denoise_nr)}:nf={fnum(cfg.denoise_nf)}")
    threshold = 10 ** (cfg.comp_threshold_db / 20)
    parts.append(
        f"acompressor=threshold={fnum(threshold)}:ratio={fnum(cfg.comp_ratio)}"
        ":attack=10:release=150:makeup=1"
    )
    return ",".join(parts)


def chain_args(ffmpeg: Path, src: Path, dst: Path, filters: str) -> list[str]:
    """`src` through the filter chain `filters`, to raw float32 at `dst` (which must not exist)."""
    return [
        str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error",
        *_F32_IN, "-i", str(src), "-af", filters, *_F32_OUT, str(dst),
    ]  # fmt: skip


def graph_args(ffmpeg: Path, inputs: list[Path], graph: str, dst: Path) -> list[str]:
    """The inputs (raw float32 files) through `graph` (its output is `[mix]`), to `dst`."""
    args = [str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error"]
    for path in inputs:
        args += [*_F32_IN, "-i", str(path)]
    return [*args, "-filter_complex", graph, "-map", "[mix]", *_F32_OUT, str(dst)]


def mix(
    project: Project,
    edl: Edl,
    version: int,
    progress: Progress,
    *,
    plan: AudioPlan,
    inventory: Inventory,
    log: Path | None = None,
    issues: list[Issue] | None = None,
    notices: list[Notice] | None = None,
) -> Path:
    """Make the mix of `edl` in `.kcut/build/v<version>/` and return the path of `mix.wav`.

    `plan` is what `sfx.json` and `music.json` say. `issues` gets M06 if a song without `loop` is
    short; `notices` gets `loudnorm_silence` if the voice or the mix is silent. A `MemoryError` in
    the synthesis of the effects is a ProjectError with its own text, and one in any other step of
    the mix is a ProjectError too (001.37, point 5): the whole mix is in memory, about 6 GB for an
    hour of music, and the answer to that is a clear exit 3 and not a crash (exit 10)."""
    try:
        return _mix(project, edl, version, progress, plan, inventory, log, issues, notices)
    except MemoryError:
        raise ProjectError(NO_MEMORY_MIX) from None


def _mix(
    project: Project,
    edl: Edl,
    version: int,
    progress: Progress,
    plan: AudioPlan,
    inventory: Inventory,
    log: Path | None,
    issues: list[Issue] | None,
    notices: list[Notice] | None,
) -> Path:
    audio = project.config.audio
    spf = samples_per_frame(edl.fps)
    total = edl.frames * spf
    folder = build_folder(project, version)
    path = {name: folder / name for name in FILES}
    for target in path.values():
        assert_in_cache(project, target)
        refuse_directory(target)
    ffmpeg = proc.tool_path("ffmpeg")
    timeout = _TIMEOUT_PER_AUDIO_S * total / SAMPLE_RATE + _TIMEOUT_FLOOR_S
    music = plan.music
    has_music = music.mode != "none"

    def make(dst: Path, args_for: ArgsFor) -> None:
        _through_partial(project, dst, args_for, log, timeout)
        _fit(project, dst, total, spf)

    _look_again(project, path["voice_raw.f32"])
    write_voice(project, edl, inventory, path["voice_raw.f32"], log)
    progress.update(1)
    chain = voice_chain(audio.voice)
    make(path["voice_chain.f32"], lambda out: chain_args(ffmpeg, path["voice_raw.f32"], out, chain))
    normalize(
        project, path["voice_chain.f32"], path["voice.f32"], audio.voice_lufs, VOICE_TP,
        log=log, notices=notices, label="la voz",
    )  # fmt: skip
    _fit(project, path["voice.f32"], total, spf)
    progress.update(2)
    if has_music:
        track = _music_track(project, plan, edl, log, issues)
        _look_again(project, path["music.f32"])  # after the synthesis, right before the write
        write_f32(path["music.f32"], track)
    progress.update(3)
    bus = _sfx_track(plan, total, spf)
    _look_again(project, path["sfx.f32"])
    write_f32(path["sfx.f32"], bus)
    progress.update(4)
    graph, _ = build_graph(has_music, music.duck.enabled, music.duck)
    sources = [path["voice.f32"], *([path["music.f32"]] if has_music else []), path["sfx.f32"]]
    make(path["mix_pre.f32"], lambda out: graph_args(ffmpeg, sources, graph, out))
    progress.update(5)
    normalize(
        project, path["mix_pre.f32"], path["mix.f32"], audio.target_lufs, audio.target_tp,
        log=log, notices=notices, label="la mezcla",
    )  # fmt: skip
    _fit(project, path["mix.f32"], total, spf)
    progress.update(6)
    _to_wav(project, path["mix.f32"], path["mix.wav"])
    progress.update(7)
    return path["mix.wav"]


def _look_again(project: Project, target: Path) -> None:
    """Look at the folder of `target` again right before something is written there (001.37, point
    2), as `render` does with `build_folder`: the mix takes minutes, and `.kcut/build/vN` can be
    changed for a link meanwhile, even to a folder inside `.kcut/`, which `assert_in_cache` alone
    lets through. The folder of the file is the build folder (`build_folder` of the version)."""
    assert_own_folder(project, target.parent)
    assert_in_cache(project, target)


def _through_partial(
    project: Project, dst: Path, args_for: ArgsFor, log: Path | None, timeout: float
) -> None:
    """Run the `ffmpeg` that `args_for` builds for a partial file and move it over `dst`."""
    partial = dst.with_name(f"{dst.name}.{os.getpid()}.partial")
    _look_again(project, partial)
    prepare_partial(partial)
    try:
        proc.run(args_for(partial), log=log, timeout_s=timeout)
        atomic_replace(partial, dst)
    finally:
        discard_partial(partial)


def _fit(project: Project, path: Path, total: int, spf: int) -> None:
    """Make the raw float32 file at `path` exactly `total` samples: zeros at the end if it is short,
    cut if it is long. Over a frame of difference it is a bug of the mix: an InternalError."""
    try:
        have = path.stat().st_size // 4
    except OSError as exc:
        raise ProjectError(f"no pude leer un audio de la mezcla: {exc.strerror}") from None
    if have == total:
        return
    if abs(have - total) > spf:
        raise InternalError(f"un paso de la mezcla dio {have} muestras y se esperaban {total}")
    samples = read_f32(path, label="un audio de la mezcla")
    fixed = np.zeros(total, dtype=np.float32)
    kept = min(len(samples), total)
    fixed[:kept] = samples[:kept]
    _look_again(project, path)
    write_f32(path, fixed)


def _db(x: Track, gain_db: float) -> Track:
    return (x * 10 ** (gain_db / 20)).astype(np.float32)


def _music_track(
    project: Project, plan: AudioPlan, edl: Edl, log: Path | None, issues: list[Issue] | None
) -> Track:
    """The music of `plan` with its gain and its windows, `frames * spf` samples."""
    doc, spf = plan.music, samples_per_frame(edl.fps)
    total = edl.frames * spf
    if doc.mode == "synth" and doc.synth is not None:
        track = synth_music(doc.synth, total, edl.fps, SAMPLE_RATE)
    elif doc.mode == "file" and doc.file is not None:
        track = load_music_file(project, doc.file, total, spf, log=log, issues=issues)
    else:
        raise InternalError("la música no tiene de dónde salir: falta synth o file")
    windows = [(w.start, w.end, w.gain_db) for w in doc.windows]
    return apply_gain_windows(_db(track, doc.gain_db), windows, spf, SAMPLE_RATE)


def _sfx_track(plan: AudioPlan, total: int, spf: int) -> Track:
    """The bus of the effects with `bus_gain_db` and its windows, `total` samples."""
    try:
        bus = build_sfx_bus(plan.events, total, spf, SAMPLE_RATE)
    except MemoryError:
        raise ProjectError(NO_MEMORY) from None
    return apply_gain_windows(_db(bus, plan.bus_gain_db), list(plan.sfx_windows), spf, SAMPLE_RATE)


def _to_wav(project: Project, source: Path, wav: Path) -> None:
    """`source` (raw float32) as 16-bit mono at `wav`, through a partial file."""
    samples = read_f32(source, label="la mezcla")
    partial = wav.with_name(f"{wav.name}.{os.getpid()}.partial")
    _look_again(project, partial)
    prepare_partial(partial)
    try:
        write_wav_s16_mono(partial, samples, SAMPLE_RATE)
        atomic_replace(partial, wav)
    except OSError as exc:
        raise ProjectError(f"no pude escribir la mezcla: {exc.strerror}") from None
    finally:
        discard_partial(partial)
