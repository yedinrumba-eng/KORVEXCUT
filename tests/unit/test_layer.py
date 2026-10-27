"""`ensure_layer` and the page of the graphics (spec S1.6b): capture once, reuse while the page is
the same, rebuild when it is not or when the index is not valid, and clean only what is the layer's.
Chromium is replaced by a double that records what it was asked for and writes the PNGs it keeps.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut.console import Out
from kcut.errors import CheckFailed, GateError, ProjectError, ToolError
from kcut.gfx import capture as gfx_capture
from kcut.gfx.captions import Chunk, ChunkWord
from kcut.gfx.capture_index import INDEX_NAME, page_hash, png_name
from kcut.gfx.layer import ensure_layer, page_for, raise_for_errors, warnings_json
from kcut.gfx.resolve import ResolvedGraphics
from kcut.gfx.resolve_cues import ResolvedCue
from kcut.ingest.inventory import Notice
from kcut.issues import Issue
from kcut.project import Project
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.unit.gfx_resolve_fakes import make_project


def _resolved(
    cues: tuple[ResolvedCue, ...] = (ResolvedCue("pill", "label", 3, 6, {"text": "x"}),),
    *,
    captions: bool = False,
    chunks: list[Chunk] | None = None,
    shown: dict[str, str] | None = None,
    issues: list[Issue] | None = None,
    notices: list[Notice] | None = None,
    empty: bool = False,
) -> ResolvedGraphics:
    from tests.unit.edl_fakes import config

    return ResolvedGraphics(
        version=1, source="file", fps=30, w=1080, h=1920, frames=60, brand={}, captions=captions,
        captions_cfg=config().captions, style={}, cues=cues, chunks=chunks or [],
        shown=shown or {}, masked=True, images={}, issues=issues or [], notices=notices or [],
        empty=empty,
    )  # fmt: skip


class _Calls:
    """The double of `capture`: it records the frames it was asked for and keeps the odd ones
    (the even ones are "empty": nothing is drawn there)."""

    def __init__(self) -> None:
        self.asked: list[list[int]] = []
        self.pages: list[str] = []

    def __call__(
        self,
        page_html: str,
        work_dir: Path,
        frames: list[int],
        fps: int,
        size: tuple[int, int],
        out_dir: Path,
        progress: Any,
        guard: Any = None,  # 001.31: `ensure_layer` passes the guard of the folders
    ) -> list[int]:
        self.asked.append(list(frames))
        self.pages.append(page_html)
        kept = [f for f in frames if f % 2 == 1]
        for f in kept:
            (out_dir / png_name(f)).write_bytes(b"png")
        return kept


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)


@pytest.fixture
def build(project: Project) -> Path:
    return project.layout.build_dir(1)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> _Calls:
    double = _Calls()
    monkeypatch.setattr(gfx_capture, "capture", double)
    return double


def _index(build: Path) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((build / "gfx" / INDEX_NAME).read_text(encoding="utf-8"))
    return result


def test_layer_nothing_to_draw_is_none_and_writes_nothing(
    project: Project, build: Path, calls: _Calls
) -> None:
    assert ensure_layer(project, _resolved(empty=True), build, force=False, notices=[]) is None
    assert calls.asked == [] and not build.exists()


def test_layer_the_first_time_it_captures_the_active_frames_and_writes_the_index(
    project: Project, build: Path, calls: _Calls
) -> None:
    resolved = _resolved()
    layer = ensure_layer(project, resolved, build, force=False, notices=[])
    assert layer is not None and layer.captured is True and layer.frames == 2
    assert layer.index_path == build / "gfx" / INDEX_NAME
    assert calls.asked == [[3, 4, 5]]  # the frames of the cue; the double keeps 3 and 5
    digest = page_hash(page_for(resolved, masked=False))
    assert _index(build) == {"fps": 30, "frames": [3, 5], "hash": digest}


def test_layer_the_same_page_is_reused_and_force_captures_again(
    project: Project, build: Path, calls: _Calls
) -> None:
    ensure_layer(project, _resolved(), build, force=False, notices=[])
    notices: list[Notice] = []
    again = ensure_layer(project, _resolved(), build, force=False, notices=notices)
    assert again is not None and again.captured is False and again.frames == 2
    assert len(calls.asked) == 1 and notices == []
    forced = ensure_layer(project, _resolved(), build, force=True, notices=notices)
    assert forced is not None and forced.captured is True and len(calls.asked) == 2


def test_layer_a_changed_page_is_captured_again_and_the_old_frames_are_gone(
    project: Project, build: Path, calls: _Calls
) -> None:
    ensure_layer(project, _resolved(), build, force=False, notices=[])
    moved = _resolved((ResolvedCue("pill", "label", 10, 14, {"text": "x"}),))  # frames 10 to 13
    layer = ensure_layer(project, moved, build, force=False, notices=[])
    assert layer is not None and layer.captured is True and layer.frames == 2
    assert sorted(p.name for p in (build / "gfx").glob("*.png")) == ["000011.png", "000013.png"]
    assert _index(build)["frames"] == [11, 13]


@pytest.mark.parametrize("damage", ["not json", "[]", '{"fps": 30}'])
def test_layer_an_index_that_is_not_valid_is_rebuilt_with_the_notice(
    project: Project, build: Path, calls: _Calls, damage: str
) -> None:
    ensure_layer(project, _resolved(), build, force=False, notices=[])
    (build / "gfx" / INDEX_NAME).write_text(damage, encoding="utf-8")
    notices: list[Notice] = []
    layer = ensure_layer(project, _resolved(), build, force=False, notices=notices)
    assert layer is not None and layer.captured is True
    assert [n.code for n in notices] == ["cache_rebuilt"]
    assert "gráficos" in notices[0].detail and str(build) not in notices[0].detail


def test_layer_without_an_index_there_is_no_notice(
    project: Project, build: Path, calls: _Calls
) -> None:
    notices: list[Notice] = []
    ensure_layer(project, _resolved(), build, force=False, notices=notices)
    assert notices == []


def test_layer_it_only_deletes_the_index_and_the_pngs_of_frames(
    project: Project, build: Path, calls: _Calls
) -> None:
    folder = build / "gfx"
    (folder / "stills").mkdir(parents=True)
    (folder / "stills" / "still_000060.png").write_bytes(b"keep")
    (folder / "000099.png").write_bytes(b"old")
    (folder / "notes.txt").write_text("keep", encoding="utf-8")
    (folder / "12345.png").write_bytes(b"keep")  # not 6 digits: not a frame of the layer
    ensure_layer(project, _resolved(), build, force=False, notices=[])
    assert not (folder / "000099.png").exists()
    assert (folder / "stills" / "still_000060.png").read_bytes() == b"keep"
    assert (folder / "notes.txt").read_text(encoding="utf-8") == "keep"
    assert (folder / "12345.png").read_bytes() == b"keep"


def test_layer_a_capture_that_fails_leaves_no_index(
    project: Project, build: Path, calls: _Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old index goes before the capture: if the capture fails, there is none that describes
    a layer that is half of one thing and half of another."""
    ensure_layer(project, _resolved(), build, force=False, notices=[])
    assert (build / "gfx" / INDEX_NAME).is_file()

    def broken(*_a: object, **_k: object) -> list[int]:
        raise ToolError("Chromium se murió")

    monkeypatch.setattr(gfx_capture, "capture", broken)
    moved = _resolved((ResolvedCue("pill", "label", 10, 13, {"text": "x"}),))
    with pytest.raises(ToolError, match="se murió"):
        ensure_layer(project, moved, build, force=False, notices=[])
    assert not (build / "gfx" / INDEX_NAME).exists()


def test_layer_with_the_subtitles_on_and_no_frame_to_draw_chromium_is_not_started(
    project: Project, build: Path, calls: _Calls
) -> None:
    resolved = _resolved((), captions=True)  # not `empty`, but no cue and no chunk
    layer = ensure_layer(project, resolved, build, force=False, notices=[])
    assert layer is not None and layer.captured is True and layer.frames == 0
    assert calls.asked == [] and _index(build)["frames"] == []
    again = ensure_layer(project, resolved, build, force=False, notices=[])
    assert again is not None and again.captured is False  # an index with no frames is valid


def test_layer_a_gfx_folder_that_leaves_the_cache_is_refused(
    project: Project, build: Path, calls: _Calls, tmp_path: Path
) -> None:
    build.mkdir(parents=True)
    outside = tmp_path / "ajeno"
    outside.mkdir()
    make_dir_link(build / "gfx", outside)
    try:
        with pytest.raises(ProjectError, match=r"fuera de \.kcut"):
            ensure_layer(project, _resolved(), build, force=False, notices=[])
    finally:
        remove_dir_link(build / "gfx")
    assert list(outside.iterdir()) == [] and calls.asked == []


def test_layer_the_page_of_the_render_has_the_text_raw_and_the_one_of_a_still_masked() -> None:
    chunk = Chunk(5, 20, [ChunkWord("a1:w0001", "3211", 5), ChunkWord("a1:w0002", "ya", 12)])
    resolved = _resolved(
        (), captions=True, chunks=[chunk], shown={"a1:w0001": "**11", "a1:w0002": "ya"}
    )
    raw, masked = page_for(resolved, masked=False), page_for(resolved, masked=True)
    assert '"text":"3211"' in raw and '"text":"**11"' not in raw
    assert '"text":"**11"' in masked and '"text":"3211"' not in masked


def test_layer_the_page_includes_the_script_of_each_component_it_uses() -> None:
    page = page_for(_resolved(), masked=False)
    assert 'KC.register("label"' in page and 'KC.register("title"' not in page
    assert page.count("window.KC = {") == 1  # the runtime, once


def test_layer_raise_for_errors_is_silent_without_errors_and_exit_1_with_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = Out(json_mode=False)
    raise_for_errors(out, _resolved(issues=[Issue("G11", "warning", "", "aviso")]))
    errors = [Issue("G07", "error", "cues[0]", "fuera"), Issue("G03", "error", "cues[1]", "mal")]
    capsys.readouterr()
    with pytest.raises(CheckFailed) as info:
        raise_for_errors(out, _resolved(issues=errors))
    assert info.value.message_es == (
        "los gráficos tienen 2 errores (G03, G07); corre kcut graphics check y corrígelos"
    )
    printed = capsys.readouterr().out
    assert "[ERROR] G07 cues[0]: fuera" in printed and "[ERROR] G03 cues[1]: mal" in printed


def test_layer_raise_for_errors_with_a_g10_is_exit_5() -> None:
    errors = [Issue("G10", "error", "cues[0].params.image", "sin aprobar")]
    with pytest.raises(GateError) as info:
        raise_for_errors(Out(json_mode=True), _resolved(issues=errors))
    assert info.value.exit_code == 5 and "G10" in info.value.message_es


def test_layer_raise_for_errors_names_at_most_5_errors() -> None:
    errors = [Issue("G03", "error", f"cues[{i}]", "mal") for i in range(9)]
    with pytest.raises(CheckFailed, match="9 errores"):
        raise_for_errors(Out(json_mode=True), _resolved(issues=errors))


def test_layer_warnings_json_has_the_warnings_and_then_the_notices() -> None:
    resolved = _resolved(
        issues=[Issue("G11", "warning", "", "uno"), Issue("G07", "error", "x", "no va")],
        notices=[Notice("pii_unmasked", "dos")],
    )
    assert warnings_json(resolved) == [
        {"code": "G11", "path": "", "message": "uno"},
        {"code": "pii_unmasked", "path": "", "message": "dos"},
    ]
