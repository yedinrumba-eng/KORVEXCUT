"""`edit/music.json` read (spec S1.8b, 001.15): the dataclasses `parse_music` gives back and that
`music_synth`, `music_file` and `mixer` take. Neutral on purpose: it imports nothing from `kcut`,
so the synthesis does not have to import the schema, which reads the project.

A key that the file leaves out has the value of the example of the spec (`synth.bpm` 120, `duck`
as in the example, `gain_db` -8, `fade_out_f` 36...): only `schema`, `mode`, `synth.progression`
and `file.path` have no default.
"""

from dataclasses import dataclass
from typing import Literal

Mode = Literal["synth", "file", "none"]
DEFAULT_GAIN_DB = -8.0


@dataclass(frozen=True)
class Window:
    """A window of the music in frames of the output, with its gain in dB (`windows`)."""

    start: int
    end: int
    gain_db: float


@dataclass(frozen=True)
class SynthCfg:
    """`synth`: the tempo, the chords (one per bar, in a loop), whether there are drums, the
    windows `[start, end)` in frames where they are silent, the frame from which they are silent
    for good (`None`: never) and the frame where the grid of bars begins."""

    bpm: float
    progression: tuple[str, ...]
    drums: bool
    mute_drums: tuple[tuple[int, int], ...]
    stop_drums_f: int | None
    origin_f: int


@dataclass(frozen=True)
class FileCfg:
    """`file`: a song of `recursos/` approved in the manifest, from frame `src_in_f` of the file,
    repeated if `loop`, with a linear fade in and out of that many frames."""

    path: str
    src_in_f: int
    loop: bool
    fade_in_f: int
    fade_out_f: int


@dataclass(frozen=True)
class DuckCfg:
    """`duck`: the sidechain compressor that lowers the music under the voice."""

    enabled: bool
    threshold: float
    ratio: float
    attack_ms: float
    release_ms: float
    makeup: float
    knee: float


DEFAULT_DUCK = DuckCfg(True, 0.03, 10.0, 15.0, 350.0, 1.0, 2.828)


@dataclass(frozen=True)
class MusicDoc:
    """`music.json` read: the `mode`, the gain of the whole music in dB, the `synth` and the `file`
    sections (`None` when the file has none), the ducking and the windows of gain. `mode: synth`
    always has `synth` and `mode: file` always has `file`."""

    mode: Mode
    gain_db: float
    synth: SynthCfg | None
    file: FileCfg | None
    duck: DuckCfg
    windows: tuple[Window, ...]


NO_MUSIC = MusicDoc("none", DEFAULT_GAIN_DB, None, None, DEFAULT_DUCK, ())  # no `edit/music.json`
