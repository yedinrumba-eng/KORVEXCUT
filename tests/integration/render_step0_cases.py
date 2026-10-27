"""`kcut render` and what it trusts, S1.6a step 0 (spec 001.27; rows 12, 14, 15 and 19): the
partial files that a render killed by force left, a file where the build folder goes, a build
folder that is changed for a link while the render works, and a mezzanine or a wav48 that is a hard
link to a file of someone else.

Collected from `test_render_synth.py`, which is at the 300-line limit. `small` is the fixture of
`render_small_cases.py` (a copy of the project with the 2 s EDL, already rendered once).
"""

import hashlib
import json
import os
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from kcut.commands import render as render_command
from kcut.config.load import parse_config
from kcut.errors import ProjectError
from kcut.ingest.cache_guard import build_folder
from kcut.paths import Layout
from kcut.project import Project
from tests.conftest import run_kcut
from tests.fixtures.links import make_dir_link, make_hard_link, remove_dir_link
from tests.fixtures.synth_edl import write_edl_v1
from tests.integration.render_small_cases import mezz_files, render_json
from tests.integration.view_frames_helpers import Run, project_args

__all__ = [
    "TestBuildDirFile",
    "TestBuildDirSwap",
    "TestBuildFolderExtendedPrefix",
    "TestHardlinkStaleRender",
    "TestOrphanPartialsRender",
]
BUILD = ".kcut/build/v1"
WRITTEN_IN_THE_BUILD = {
    "video.mp4",
    "video.partial.mp4",
    "voice_raw.f32",
    "render.mp4",
    "render.partial.mp4",
}


def _planted(path: Path, hours: float) -> Path:
    """A half written file at `path`, `hours` old."""
    path.write_bytes(b"half a file")
    when = time.time() - hours * 3600
    os.utime(path, (when, when))
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestOrphanPartialsRender:
    """Row 12: `render` and `ingest` delete the partial files that are over a day old."""

    def test_orphan_partials_render_sweeps_the_old_ones_and_keeps_the_young_ones(
        self, small: Path
    ) -> None:
        folder = small / ".kcut" / "mezz"
        old = _planted(folder / "a1_45-135_1440x2560_tm2.4242.partial.mp4", 25)
        old_tmp = _planted(folder / "a1_45-135_1440x2560_tm2.mp4.json.4242.tmp", 25)
        young = _planted(folder / "a1_45-135_1440x2560_tm2.4243.partial.mp4", 1)
        code, doc, err = render_json(small)
        assert code == 0, err
        assert not old.exists() and not old_tmp.exists()
        assert young.exists()  # a render that may be alive
        assert "huérfano" not in json.dumps(doc)  # the count is for the log, not for the JSON
        logs = (small / ".kcut" / "logs").glob("render-*.log")
        assert any("[orphan_partials] 2 " in p.read_text(encoding="utf-8") for p in logs)

    def test_orphan_partials_render_leaves_no_trace_when_there_is_nothing_to_sweep(
        self, small: Path
    ) -> None:
        code, _, err = render_json(small)
        assert code == 0, err
        logs = (small / ".kcut" / "logs").glob("render-*.log")
        assert not any("[orphan_partials]" in p.read_text(encoding="utf-8") for p in logs)

    def test_orphan_partials_ingest_sweeps_too(self, view_fresh: Path) -> None:
        old = _planted(view_fresh / ".kcut" / "wav16" / "a1_x.4242.partial.wav", 25)
        done = run_kcut("ingest", "--no-proxy", "--json", "--project", str(view_fresh))
        assert done.returncode == 0, done.stderr
        assert not old.exists()
        assert "huérfano" not in done.stdout and "huérfano" not in done.stderr
        logs = (view_fresh / ".kcut" / "logs").glob("ingest-*.log")
        assert any("[orphan_partials] 1 " in p.read_text(encoding="utf-8") for p in logs)


class TestBuildDirFile:
    """Row 14: a file where the build folder goes is a ProjectError, not an exit 10."""

    def test_build_dir_file_a_file_at_build_v1_is_exit_3_and_no_mezzanine_is_made(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        write_edl_v1(view_fresh)
        build = view_fresh / ".kcut" / "build"
        build.mkdir(parents=True, exist_ok=True)
        (build / "v1").write_text("this is a file", encoding="utf-8")
        code, doc, err = kcut_json("render", "--no-graphics", *project_args(view_fresh))
        assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
        assert str(build / "v1") in doc["error"]["message"]
        assert (
            "es un archivo; kcut espera una carpeta ahí: bórralo o renómbralo"
            in (doc["error"]["message"])
        )
        assert not (view_fresh / ".kcut" / "mezz").exists()  # it stopped before the mezzanines
        assert (build / "v1").read_text(encoding="utf-8") == "this is a file"  # and kept the file


class TestBuildDirSwap:
    """Row 15: `build/v7` is changed for a link to `.kcut/` while the render works. The folder is
    looked at again before the picture, the voice and the mux."""

    @staticmethod
    def _v7(small: Path) -> Path:
        document = json.loads((small / "edit" / "edl-v1.json").read_text(encoding="utf-8"))
        document["version"] = 7
        (small / "edit" / "edl-v7.json").write_text(json.dumps(document), encoding="utf-8")
        return small / ".kcut" / "build" / "v7"

    @staticmethod
    def _swap(folder: Path, small: Path) -> None:
        """Move the real folder away and leave a link to the cache where it was."""
        folder.rename(folder.with_name("v7-real"))
        make_dir_link(folder, small / ".kcut")

    @pytest.mark.parametrize("after", ["_mezzanines", "_picture", "write_voice"])
    def test_build_dir_swap_a_folder_changed_for_a_link_mid_render_is_exit_3_and_writes_nothing(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, after: str
    ) -> None:
        v7 = self._v7(small)
        real = getattr(render_command, after)

        def swapping(*args: object, **kwargs: object) -> object:
            result = real(*args, **kwargs)  # the stage runs; then the folder is changed
            self._swap(v7, small)
            return result

        monkeypatch.setattr(render_command, after, swapping)
        before = sorted(p.name for p in (small / ".kcut").iterdir())
        try:
            code, doc, err = kcut_json("render", "--no-graphics", *project_args(small))
        finally:
            remove_dir_link(v7)  # the link, not what it points at
        assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
        assert "enlace" in doc["error"]["message"]
        root = sorted(p.name for p in (small / ".kcut").iterdir())
        assert not WRITTEN_IN_THE_BUILD & set(root) and root == before


class TestHardlinkStaleRender:
    """Row 19: a mezzanine or a wav48 that is a hard link to a file outside the project is made
    again, and the file outside is left as it was."""

    def _linked(self, small: Path, work_file: Path) -> tuple[Path, str]:
        """Make `work_file` a second name of a copy of it that lives outside the project (its
        sidecar stays, and it still matches the bytes)."""
        outside = small.parent / f"ajeno-{work_file.suffix[1:]}{work_file.suffix}"
        shutil.copy2(work_file, outside)
        work_file.unlink()
        make_hard_link(work_file, outside)
        assert work_file.stat().st_nlink == 2
        return outside, _sha(outside)

    def test_hardlink_stale_a_mezzanine_that_is_a_hard_link_is_made_again(
        self, small: Path
    ) -> None:
        (mezz,) = mezz_files(small)
        outside, before = self._linked(small, mezz)
        code, doc, err = render_json(small)
        assert code == 0, err
        assert (doc["mezz_built"], doc["mezz_reused"]) == (1, 0)
        assert _sha(outside) == before and outside.stat().st_nlink == 1
        assert mezz.stat().st_nlink == 1

    def test_hardlink_stale_a_wav48_that_is_a_hard_link_is_made_again(self, small: Path) -> None:
        wav = next((small / ".kcut" / "wav48").glob("a1_*.wav"))
        outside, before = self._linked(small, wav)
        code, _, err = render_json(small)
        assert code == 0, err
        assert _sha(outside) == before and outside.stat().st_nlink == 1
        assert wav.stat().st_nlink == 1
        assert _sha(wav) == before  # the same audio, made again


@pytest.mark.skipif(sys.platform != "win32", reason="the prefix is how Windows resolves a path")
class TestBuildFolderExtendedPrefix:
    """Row 22 (001.28 point 1): `build_folder` compares the folder with where it should resolve.
    With the extended-length prefix on one side only (what `Path.resolve` does on a path that
    another process is creating at that moment) it refused its own folder as "not itself"."""

    @staticmethod
    def _project(tmp_path: Path) -> Project:
        root = (tmp_path / "proyecto ñandú").resolve()
        (root / ".kcut" / "build" / "v1").mkdir(parents=True)
        return Project(root, parse_config("", default_name="x"), Layout(root))

    @staticmethod
    def _prefixed(monkeypatch: pytest.MonkeyPatch, which: Callable[[Path], bool]) -> None:
        real = Path.resolve

        def resolve(self: Path, strict: bool = False) -> Path:
            out = real(self, strict=strict)
            return Path("\\\\?\\" + str(out)) if which(out) else out

        monkeypatch.setattr(Path, "resolve", resolve)

    @pytest.mark.parametrize("name", ["v1", "build", None], ids=["folder", "parent", "all"])
    def test_extended_prefix_build_folder_passes_with_it_on_the_folder_or_its_parent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str | None
    ) -> None:
        project = self._project(tmp_path)
        self._prefixed(monkeypatch, lambda out: name is None or out.name == name)
        # 001.31: `_build_folder` of `commands/render.py` is `build_folder` of `cache_guard`
        assert build_folder(project, 1) == project.layout.build_dir(1)

    def test_extended_prefix_build_folder_still_refuses_a_link_to_the_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = self._project(tmp_path)
        folder = project.layout.build_dir(1)
        folder.rmdir()
        make_dir_link(folder, project.layout.cache)
        try:
            self._prefixed(monkeypatch, lambda _out: True)
            with pytest.raises(ProjectError, match="enlace"):
                build_folder(project, 1)  # 001.31: it was `render_command._build_folder`
        finally:
            remove_dir_link(folder)
