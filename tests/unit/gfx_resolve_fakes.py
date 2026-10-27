"""Pieces for the tests of `gfx.resolve` that need no ffmpeg and no transcript on disk: a project in
a temporary folder, the example EDL, `kept_words` replaced by one that gives what the test says,
and the writers of `edit/graphics.json` and of the manifest of resources."""

import copy
import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from kcut.edl.kept import KeptWords
from kcut.edl.model import Edl
from kcut.edl.words import KeptWord
from kcut.gfx import resolve as resolve_module
from kcut.gfx.resolve import ResolvedGraphics, resolve
from kcut.paths import Layout
from kcut.project import Project
from tests.fixtures.synth_graphics import graphics_v1_document
from tests.unit.edl_fakes import config, inventory, parsed


def make_project(tmp_path: Path) -> Project:
    """A project folder with `edit/` and `recursos/`, and the config of the unit tests."""
    root = tmp_path / "proyecto ñandú"
    (root / "edit").mkdir(parents=True)
    (root / "recursos").mkdir()
    return Project(root, config(), Layout(root))


def with_captions(project: Project, **changes: Any) -> Project:
    """The same project with `[captions]` of its config changed (`enabled=False`, `y=0.3`...)."""
    cfg = project.config
    captions = dataclasses.replace(cfg.captions, **changes)
    return Project(project.root, dataclasses.replace(cfg, captions=captions), project.layout)


def with_privacy(project: Project, mask_pii: bool) -> Project:
    cfg = project.config
    privacy = dataclasses.replace(cfg.privacy, mask_pii=mask_pii)
    return Project(project.root, dataclasses.replace(cfg, privacy=privacy), project.layout)


def word(i: int, text: str, out_s: int, out_e: int, clip_index: int = 1) -> KeptWord:
    return KeptWord(f"a1:w{i:04d}", text, clip_index, out_s, out_e, "a1", 0, 0)


def fake_kept(
    monkeypatch: pytest.MonkeyPatch,
    words: list[KeptWord] | None = None,
    shown: dict[str, str] | None = None,
    missing: tuple[str, ...] = (),
) -> list[int]:
    """`kept_words` gives `words` (their `shown` text is their own unless `shown` says otherwise);
    returns a list that gets one item each time it is called."""
    given = words or []
    calls: list[int] = []

    def fake(*_a: Any, **_k: Any) -> KeptWords:
        calls.append(1)
        text = {w.id: w.text for w in given} | (shown or {})
        return KeptWords(words=given, shown=text, missing=missing, masked=True)

    monkeypatch.setattr(resolve_module, "kept_words", fake)
    return calls


def write_graphics(project: Project, document: object) -> None:
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    (project.root / "edit" / "graphics.json").write_text(text, encoding="utf-8", newline="\n")


def write_manifest(project: Project, rel: str, approved_by: str = "test") -> None:
    item = {
        "file": rel,
        "kind": "imagen",
        "origin": "propio",
        "license": "propia",
        "obtained": "2026-10-27",
        "approved_by": approved_by,
    }
    document = {"schema": "kcut.recursos/1", "items": [item]}
    path = project.root / "recursos" / "recursos.json"
    path.write_text(json.dumps(document), encoding="utf-8", newline="\n")


def doc_without_captions(change: Any = None) -> dict[str, Any]:
    """The fixture document with the subtitles off (the tests of the cues are not about them),
    after `change(document)` if given."""
    document = copy.deepcopy(graphics_v1_document())
    document["captions"] = {"enabled": False}
    if change is not None:
        change(document)
    return document


def errors_of(resolved: ResolvedGraphics) -> list[tuple[str, str]]:
    """`(code, path)` of the errors only."""
    return [(i.code, i.path) for i in resolved.issues if i.level == "error"]


def run_resolve(project: Project, edl: Edl | None = None) -> ResolvedGraphics:
    return resolve(project, edl or parsed(), 1, inventory=inventory())


def codes(resolved: ResolvedGraphics) -> list[tuple[str, str]]:
    """`(code, path)` of every issue, in order."""
    return [(i.code, i.path) for i in resolved.issues]
