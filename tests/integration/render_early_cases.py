"""`kcut render` and what it looks at first, and two renders at once (spec S1.5b rows 51, 53, 55
and 58; 001.26 points 3, 5, 7 and 10): a folder at a destination is told before anything is made,
a build folder that is a link is refused before anything is written, a link planted at the
temporary file of a sidecar changes nothing, and two renders with the wav48 and the mezzanines
cold both finish.

Collected from `test_render_synth.py`, which is at the 300-line limit. `small` is the fixture of
`render_small_cases.py` (a copy of the project with the 2 s EDL, already rendered once).
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from kcut.commands import render as render_command
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.integration.render_small_cases import mezz_files
from tests.integration.view_frames_helpers import Run, project_args

__all__ = [
    "TestBuildDirJunction",
    "TestRenderDestEarly",
    "TestSidecarTmpExclusive",
    "TestWorkfilesConcurrentRenders",
]
BUILD = ".kcut/build/v1"
DESTINATIONS = [
    "video.mp4",
    "render.mp4",
    "voice_raw.f32",
    "video.partial.mp4",
    "render.partial.mp4",
]


class TestRenderDestEarly:
    """Row 53: the five destinations are looked at before the mezzanines and the picture."""

    @pytest.mark.parametrize("name", DESTINATIONS)
    def test_render_dest_early_a_folder_at_a_destination_is_exit_3_before_any_work(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        target = small / BUILD / name
        if target.is_file():
            target.unlink()
        target.mkdir()

        def late(*_a: object, **_k: object) -> None:
            pytest.fail("the render went on after a folder at a destination")

        for stage in ("ensure_mezz", "plan_mezz", "compose_video", "write_voice"):
            monkeypatch.setattr(render_command, stage, late)
        started = {p.name for p in (small / BUILD).iterdir()}
        code, doc, _ = kcut_json("render", "--no-graphics", *project_args(small))
        assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
        assert "carpeta" in doc["error"]["message"]
        assert {p.name for p in (small / BUILD).iterdir()} == started  # nothing was written

    def test_render_dest_early_video_partial_never_comes_to_exist(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (small / BUILD / "render.mp4").unlink()
        (small / BUILD / "render.mp4").mkdir()
        seen: list[str] = []
        real = render_command.prepare_partial

        def spy(path: Path) -> None:
            seen.append(path.name)
            real(path)

        monkeypatch.setattr(render_command, "prepare_partial", spy)
        code, _, _ = kcut_json("render", "--no-graphics", *project_args(small))
        assert code == 3 and seen == []  # not even `video.partial.mp4` was prepared
        assert not (small / BUILD / "video.partial.mp4").exists()


class TestBuildDirJunction:
    """Row 58: `.kcut/build/v7` is a link to somewhere inside `.kcut/` itself."""

    @staticmethod
    def _v7(small: Path) -> Path:
        document = json.loads((small / "edit" / "edl-v1.json").read_text(encoding="utf-8"))
        document["version"] = 7
        (small / "edit" / "edl-v7.json").write_text(json.dumps(document), encoding="utf-8")
        return small / ".kcut" / "build" / "v7"

    @staticmethod
    def _root_of_the_cache(small: Path) -> list[str]:
        return sorted(p.name for p in (small / ".kcut").iterdir())

    def _refused(self, small: Path, kcut_json: Run, link: Path) -> None:
        before = self._root_of_the_cache(small)
        try:
            code, doc, err = kcut_json("render", "--no-graphics", *project_args(small))
        finally:
            remove_dir_link(link)  # the link, not what it points at
        assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
        assert "enlace" in doc["error"]["message"]
        after = self._root_of_the_cache(small)
        assert after == before
        assert not {"video.mp4", "render.mp4", "voice_raw.f32"} & set(after)

    @pytest.mark.skipif(sys.platform != "win32", reason="a junction is a Windows thing")
    def test_build_dir_junction_a_junction_to_the_cache_is_exit_3_and_writes_nothing(
        self, small: Path, kcut_json: Run
    ) -> None:
        link = self._v7(small)
        made = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(small / ".kcut")],
            capture_output=True,
            check=False,
        )
        assert made.returncode == 0, made.stdout
        self._refused(small, kcut_json, link)

    def test_build_dir_junction_a_link_to_the_cache_of_any_kind_is_exit_3(
        self, small: Path, kcut_json: Run
    ) -> None:
        link = self._v7(small)
        make_dir_link(link, small / ".kcut")  # a symlink, or a junction if that needs a privilege
        self._refused(small, kcut_json, link)

    def test_build_dir_junction_a_link_to_another_build_folder_is_exit_3_too(
        self, small: Path, kcut_json: Run
    ) -> None:
        link = self._v7(small)
        make_dir_link(link, small / BUILD)  # inside `.kcut/`, so the cache guard passes it
        try:
            code, doc, _ = kcut_json("render", "--no-graphics", *project_args(small))
        finally:
            remove_dir_link(link)
        assert code == 3 and "enlace" in doc["error"]["message"]


class TestSidecarTmpExclusive:
    """Row 55: a link planted where the sidecar of a mezzanine is about to be written."""

    def test_sidecar_tmp_exclusive_a_link_planted_during_a_render_is_exit_3_and_changes_nothing(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (mezz,) = mezz_files(small)
        sidecar = Path(f"{mezz}.json")
        sidecar.unlink()  # the mezzanine is made again, and its sidecar after it
        footage = small / "crudo" / "cam a.mp4"
        before = hashlib.sha256(footage.read_bytes()).hexdigest()
        tmp = sidecar.with_name(f"{sidecar.name}.{os.getpid()}.tmp")  # in process: our pid
        real, planted = Path.unlink, []

        def racing(self: Path, *args: Any, **kwargs: Any) -> None:
            real(self, *args, **kwargs)
            if self == tmp and not planted:  # right after the `unlink`, before the `open`
                planted.append(True)
                os.link(footage, tmp)

        monkeypatch.setattr(Path, "unlink", racing)
        code, doc, err = kcut_json("render", "--no-graphics", *project_args(small))
        monkeypatch.undo()
        assert planted == [True], "the race never happened"
        assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
        assert hashlib.sha256(footage.read_bytes()).hexdigest() == before
        assert footage.stat().st_nlink == 1  # the planted link was removed with the temporary


class TestWorkfilesConcurrentRenders:
    """Row 51: two renders (two versions of the EDL, so two locks) with the wav48 and the
    mezzanines cold, started together. Both build the wav48 in the voice phase."""

    @staticmethod
    def _children(small: Path) -> list[subprocess.Popen[str]]:
        base = [sys.executable, "-I", "-X", "utf8", "-m", "kcut", "render", "--no-graphics"]
        base += ["--json", "--project", str(small)]
        return [
            subprocess.Popen(
                [*base, "--edl", f"edit/edl-v{v}.json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
            )
            for v in (1, 2)
        ]

    def test_workfiles_concurrent_both_finish_with_the_wav48_and_the_mezzanines_cold(
        self, small: Path
    ) -> None:
        document: dict[str, Any] = json.loads((small / "edit" / "edl-v1.json").read_text("utf-8"))
        document["version"] = 2
        (small / "edit" / "edl-v2.json").write_text(json.dumps(document), encoding="utf-8")
        for round_ in range(2):
            shutil.rmtree(small / ".kcut" / "mezz", ignore_errors=True)
            shutil.rmtree(small / ".kcut" / "wav48", ignore_errors=True)
            done = [(*c.communicate(timeout=300), c.returncode) for c in self._children(small)]
            assert [code for _, _, code in done] == [0, 0], (round_, done)
        wavs = sorted(p.name for p in (small / ".kcut" / "wav48").iterdir())
        assert len(wavs) == 2 and wavs[1] == f"{wavs[0]}.json" and wavs[0].endswith(".wav")
        left = [p.name for p in (small / ".kcut").rglob("*") if ".partial." in p.name]
        assert left == []
