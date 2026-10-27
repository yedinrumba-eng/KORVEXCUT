"""Work files, S1.6a round 2 (spec 001.28, point 2; row 23): a message about a work file names it by
its class and its clip (`wav48 de a1`), never by its path or by `str()` of an `OSError`, because
the name carries the slug of the original clip and that slug may hold a phone number.

Collected from `test_workfiles.py`, whose `project` fixture (a project with `.kcut/wav16/` and
`crudo/`) these use. The wavio half of the row is in `wavio_nopath_cases.py`.
"""

import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.errors import ProjectError, ToolError
from kcut.ingest import sidecar as sidecar_module
from kcut.ingest import workfiles
from kcut.ingest.workfiles import work_label
from kcut.jsonio import write_json_exclusive
from kcut.project import Project

__all__ = ["TestWavNoPath"]
NAME = "a1_ana-perez-809-555-1234.wav"
LEAKS = ("809", "555", "1234", "ana", "perez", ":\\")
JOB = ("sha256:abc", {"sr": 48000}, 1.0)
CLOSE = "cierra el wav48 de a1 en el reproductor y repite"


def _clean(message: str) -> bool:
    return not any(piece in message.lower() for piece in LEAKS)


class TestWavNoPath:
    @staticmethod
    def _dst(project: Project) -> Path:
        dst = project.layout.wav48 / NAME
        dst.parent.mkdir(parents=True, exist_ok=True)
        return dst

    @staticmethod
    def _refused(where: Path) -> Any:
        def refuse(*_a: object, **_k: object) -> None:
            raise PermissionError(13, "Access is denied", str(where))

        return refuse

    @pytest.mark.parametrize(
        ("rel", "label"),
        [
            (f".kcut/wav48/{NAME}", "wav48 de a1"),
            (".kcut/wav16/b2_clip-uno.wav", "wav16 de b2"),
            (".kcut/proxy/a10_clip.mp4", "proxy de a10"),
        ],
    )
    def test_wav_no_path_work_label_is_the_class_and_the_clip(self, rel: str, label: str) -> None:
        assert work_label(Path("p") / rel) == label

    def test_wav_no_path_land_with_a_refused_replace_says_the_class_and_the_clip(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        dst.write_bytes(b"theirs, no sidecar")
        monkeypatch.setattr(os, "replace", self._refused(dst))
        monkeypatch.setattr(sidecar_module, "LAND_WAIT_S", 0.0)  # 001.29: no real wait
        with pytest.raises(ProjectError) as info:
            workfiles._land(dst.with_name("a1_x.4242.partial.wav"), dst, JOB[0], JOB[1])
        assert info.value.message_es == CLOSE and _clean(info.value.message_es)

    def test_wav_no_path_copy_with_a_refused_copy_says_the_class_and_the_clip(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        src = project.layout.wav16 / "stage-1.wav"
        src.write_bytes(b"audio")
        monkeypatch.setattr(shutil, "copy2", self._refused(dst))
        with pytest.raises(ProjectError) as info:
            workfiles._copy(src, dst)
        assert info.value.message_es == CLOSE and _clean(info.value.message_es)

    def test_wav_no_path_replace_with_a_refused_move_says_the_class_and_the_clip(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        monkeypatch.setattr(os, "replace", self._refused(dst))
        with pytest.raises(ProjectError) as info:
            workfiles._replace(project.layout.wav16 / "stage-1.wav", dst)
        assert info.value.message_es == CLOSE and _clean(info.value.message_es)

    def test_wav_no_path_a_folder_where_the_work_file_goes_says_the_class_and_the_clip(
        self, project: Project
    ) -> None:
        dst = self._dst(project)
        dst.mkdir()
        for call in (workfiles._replace, workfiles._copy):
            with pytest.raises(ProjectError) as info:
                call(project.layout.wav16 / "stage-1.wav", dst)
            expected = "en el wav48 de a1 hay una carpeta donde kcut espera un archivo; "
            assert info.value.message_es == expected + "bórrala o muévela"
            assert _clean(info.value.message_es)

    def test_wav_no_path_a_build_that_makes_nothing_says_the_class_and_the_clip(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(proc, "run", lambda *_a, **_k: None)  # ffmpeg "ran" and wrote nothing
        with pytest.raises(ToolError) as info:
            workfiles._build(
                project, lambda out: ["ffmpeg", str(out)], self._dst(project), JOB, None
            )
        assert info.value.message_es == "ffmpeg no produjo el wav48 de a1"

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (
                OSError(5, "Input/output error", f"C:\\p\\.kcut\\wav48\\{NAME}.json"),
                "no pude escribir el sidecar del wav48 de a1: Input/output error",
            ),
            (OSError(f"disk of {NAME}"), "no pude escribir el sidecar del wav48 de a1: OSError"),
            (
                PermissionError(13, "Access is denied", NAME),
                "cierra el sidecar del wav48 de a1 en el reproductor y repite",
            ),
        ],
    )
    def test_wav_no_path_the_sidecar_of_a_work_file_that_fails_to_be_written(
        self,
        project: Project,
        monkeypatch: pytest.MonkeyPatch,
        error: OSError,
        expected: str,
    ) -> None:
        dst = self._dst(project)
        dst.write_bytes(b"audio")
        real = os.replace

        def replace(src: Any, to: Any) -> None:
            if str(to).endswith(".json"):
                raise error
            real(src, to)

        monkeypatch.setattr(proc, "run", lambda args, **_k: Path(args[-1]).write_bytes(b"made"))
        monkeypatch.setattr(os, "replace", replace)
        # 001.31: a refused move of the sidecar waits (`land_sidecar`); no real 10 s in this test
        monkeypatch.setattr(sidecar_module, "LAND_WAIT_S", 0.0)
        with pytest.raises(ProjectError) as info:
            workfiles._build(project, lambda out: ["ffmpeg", str(out)], dst, JOB, None)
        assert info.value.message_es == expected and _clean(info.value.message_es)

    def test_wav_no_path_without_a_label_write_json_exclusive_keeps_its_old_messages(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "x.json"

        def replace(*_a: object, **_k: object) -> None:
            raise OSError(5, "Input/output error", str(target))

        monkeypatch.setattr(os, "replace", replace)
        with pytest.raises(ProjectError) as info:
            write_json_exclusive(target, {"a": 1})
        assert info.value.message_es.startswith(f"no pude escribir {target}: ")
        assert "Input/output error" in info.value.message_es
