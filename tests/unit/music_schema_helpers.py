"""Pieces shared by the tests of the schema of `edit/music.json` (spec S1.8b row 3): documents
made from the example of the spec, `parse_music` over the example EDL (345 frames), and a song in
`recursos/` that is, or is not, approved in the manifest."""

import copy
from typing import Any

from kcut.audio.music_model import MusicDoc
from kcut.audio.music_schema import parse_music
from kcut.issues import Issue
from kcut.project import Project
from tests.fixtures.synth_audio import music_plan_document
from tests.unit.gfx_resolve_fakes import write_manifest

FRAMES = 345
SECRET = "Maria-809-555-1234"


def synth_doc(**changes: Any) -> dict[str, Any]:
    doc = copy.deepcopy(music_plan_document())
    doc.update(changes)
    return doc


def with_synth(**changes: Any) -> dict[str, Any]:
    doc = copy.deepcopy(music_plan_document())
    doc["synth"].update(changes)
    return doc


def file_doc(**changes: Any) -> dict[str, Any]:
    file = {"path": "recursos/musica/tema.wav", "loop": True} | changes
    return {"schema": "kcut.music/1", "mode": "file", "file": file}


def parse(project: Project, data: object) -> tuple[MusicDoc | None, list[Issue]]:
    return parse_music(data, project, FRAMES)


def codes(issues: list[Issue]) -> list[tuple[str, str]]:
    return [(i.code, i.path) for i in issues]


def song(project: Project, name: str = "tema.wav", approved: str | None = "test") -> str:
    folder = project.root / "recursos" / "musica"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"RIFF....WAVE")
    rel = f"recursos/musica/{name}"
    if approved is not None:
        write_manifest(project, rel, approved_by=approved)
    return rel
