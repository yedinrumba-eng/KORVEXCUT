"""Check an EDL file against the project: the reading half of the EDL (spec S1.5a, 001.15).

`check_edl_file` is what `edl check`, `render`, `graphics`, `mix`, `build` and `storyboard` call,
so all of them judge an EDL the same way. It needs the wav16 of the voice clips: the audio really
has the length of that file, not the one the container declared (T6).
"""

from dataclasses import dataclass

from kcut.config.model import ProjectConfig
from kcut.edl.files import find_edl, load_edl
from kcut.edl.model import Edl, VoiceClip
from kcut.edl.validate import validate
from kcut.errors import ProjectError
from kcut.ingest.inventory import Clip, Inventory
from kcut.issues import Issue
from kcut.project import Project
from kcut.timebase import ms_to_f_floor
from kcut.transcribe.cache import wav16_length_ms
from kcut.transcribe.loaded import wav16_or_none


@dataclass(frozen=True)
class EdlCheck:
    """The EDL read from `rel` (version `version`), or `None` if its schema is wrong, and every
    finding: the `E01` of the schema, or those of `validate`."""

    rel: str
    version: int
    edl: Edl | None
    issues: list[Issue]


def clip_audio_frames(project: Project, clip: Clip, fps: int) -> int | None:
    """The voice frames a clip's audio really has: `min(frames of the inventory, frames of its
    wav16)`, with the wav16's length from its samples. `None` for a clip without audio or whose
    wav16 is not there (T6)."""
    wav = wav16_or_none(project, clip) if clip.audio is not None else None
    if wav is None:
        return None
    real = ms_to_f_floor(wav16_length_ms(wav), fps)
    return real if clip.frames is None else min(clip.frames, real)


def audio_frames(project: Project, inv: Inventory, edl: Edl) -> dict[str, int]:
    """`audio_f` for E06: the real voice frames of each `src` that a voice clip uses and that is
    in the inventory with audio. A missing wav16 is a ProjectError (exit 3)."""
    found: dict[str, int] = {}
    for src in dict.fromkeys(c.src for c in edl.clips if isinstance(c, VoiceClip)):
        clip = inv.by_id(src)
        if clip is None or clip.audio is None:
            continue  # E04 / E05 say so
        frames = clip_audio_frames(project, clip, edl.fps)
        if frames is None:
            raise ProjectError(f"falta el wav16 de {src}; corre kcut ingest")
        found[src] = frames
    return found


def check_edl_file(project: Project, inv: Inventory, rel: str | None) -> EdlCheck:
    """`find_edl` + `load_edl` + `audio_frames` + `validate`. With schema errors (`E01`) nothing
    else is checked: there is no EDL to check."""
    path, _ = find_edl(project, rel)
    edl, issues, version = load_edl(project, path)
    if edl is None:
        return EdlCheck(path, version, None, issues)
    cfg: ProjectConfig = project.config
    findings = validate(edl, inv, cfg, version, audio_frames(project, inv, edl))
    return EdlCheck(path, version, edl, findings)
