"""The guard of `.kcut/` with the extended-length prefix of Windows, and two builds of the same
work file (spec S1.5b rows 51 and 52; 001.26 points 3 and 4).

Collected from `test_workfiles.py`, which is at the 300-line limit: the `project` fixture (a
project with `.kcut/wav16/` and `crudo/`) is the one of that file.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.errors import ProjectError
from kcut.ingest import sidecar as sidecar_module
from kcut.ingest import workfiles
from kcut.ingest.cache_guard import plain_path
from kcut.project import Project
from kcut.render import mezz_files
from tests.unit.mezz_build_cases import _Fake
from tests.unit.mezz_files_cases import FPS, _a1, _job, mezz_project

__all__ = ["TestInCachePrefix", "TestPlainPath", "TestWorkfilesConcurrent", "mezz_project"]


def _prefixed(monkeypatch: pytest.MonkeyPatch, which: Any) -> None:
    """`Path.resolve` leaves the `\\\\?\\` prefix on the paths for which `which(path)` is true, as
    it does on Windows for a file that another process is replacing."""
    real = Path.resolve

    def resolve(self: Path, strict: bool = False) -> Path:
        out = real(self, strict=strict)
        return Path("\\\\?\\" + str(out)) if which(out) else out

    monkeypatch.setattr(Path, "resolve", resolve)


@pytest.mark.skipif(sys.platform != "win32", reason="the prefix is how Windows resolves a path")
class TestInCachePrefix:
    """Row 52 (001.26 point 4): the paths are compared without the `\\\\?\\` prefix."""

    def test_in_cache_prefix_a_path_inside_the_cache_that_resolves_with_it_is_accepted(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inside = project.layout.wav16 / "a1_x.wav"
        plain = inside.resolve()
        _prefixed(monkeypatch, lambda out: out.name == "a1_x.wav")
        assert str(inside.resolve()).startswith("\\\\?\\")  # the patch does what Windows does
        assert workfiles._assert_in_cache(project, inside) == plain

    def test_in_cache_prefix_everything_resolving_with_it_is_accepted_too(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _prefixed(monkeypatch, lambda _out: True)
        workfiles._assert_in_cache(project, project.layout.wav16 / "a1_x.wav")

    @pytest.mark.parametrize("rel", ["crudo/cam a.mp4", "edit/estrategia.md", "x"])
    def test_in_cache_prefix_a_path_outside_the_cache_is_still_refused(
        self, project: Project, monkeypatch: pytest.MonkeyPatch, rel: str
    ) -> None:
        _prefixed(monkeypatch, lambda out: out.name == Path(rel).name)
        with pytest.raises(ProjectError, match=r"fuera de \.kcut"):
            workfiles._assert_in_cache(project, project.root / rel)

    def test_in_cache_prefix_a_path_that_climbs_out_with_it_is_still_refused(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _prefixed(monkeypatch, lambda out: out.name == "cam a.mp4")
        sneaky = project.layout.wav16 / ".." / ".." / "crudo" / "cam a.mp4"
        with pytest.raises(ProjectError, match=r"fuera de \.kcut"):
            workfiles._assert_in_cache(project, sneaky)


class TestPlainPath:
    """Row 52: the prefix is taken off as text, so this runs on any system."""

    @pytest.mark.parametrize(
        ("raw", "plain"),
        [
            ("\\\\?\\C:\\p\\.kcut\\x.wav", "C:\\p\\.kcut\\x.wav"),
            ("\\\\?\\UNC\\srv\\share\\p\\x.wav", "\\\\srv\\share\\p\\x.wav"),
            ("\\\\?\\unc\\srv\\share", "\\\\srv\\share"),
            ("C:\\p\\x.wav", "C:\\p\\x.wav"),
            ("\\\\srv\\share\\x.wav", "\\\\srv\\share\\x.wav"),
            ("/tmp/p/x.wav", "/tmp/p/x.wav"),
        ],
    )
    def test_in_cache_prefix_plain_path_takes_off_only_the_extended_length_prefix(
        self, raw: str, plain: str
    ) -> None:
        assert str(plain_path(Path(raw))) == str(Path(plain))

    def test_in_cache_prefix_mezz_files_has_no_retry_and_calls_the_guard_directly(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert not hasattr(mezz_files, "_in_cache") and not hasattr(mezz_files, "_CHECK_TRIES")
        seen: list[str] = []
        real = workfiles._assert_in_cache

        def spy(project: Project, path: Path) -> Path:
            seen.append(path.name)
            return real(project, path)

        monkeypatch.setattr(workfiles, "_assert_in_cache", spy)
        _Fake(monkeypatch, made=90)
        mezz_files.build_mezz(mezz_project, _job(), _a1(), FPS, None)
        name = _job().path.rsplit("/", 1)[1]
        assert seen == [name, f"{name[:-4]}.{os.getpid()}.partial.mp4", f"{name}.json"]

    def test_in_cache_prefix_a_guard_that_says_no_is_believed_the_first_time(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[Path] = []

        def no(_project: Project, path: Path) -> Path:
            calls.append(path)
            raise ProjectError("queda fuera de .kcut/")

        monkeypatch.setattr(workfiles, "_assert_in_cache", no)
        fake = _Fake(monkeypatch, made=90)
        with pytest.raises(ProjectError):
            mezz_files.build_mezz(mezz_project, _job(), _a1(), FPS, None)
        assert len(calls) == 1 and fake.runs == []  # no waiting, no second look


WAV_SIDECAR = {"qhash": "sha256:abc", "params": {"sr": 48000}}


class TestWorkfilesConcurrent:
    """Row 51 (001.26 point 3): two builds of the same work file in two processes."""

    def _dst(self, project: Project) -> Path:
        return project.layout.wav48 / "a1_clip.wav"

    def _build(self, project: Project, dst: Path) -> None:
        workfiles._build(
            project, lambda out: ["ffmpeg", str(out)], dst, ("sha256:abc", {"sr": 48000}, 1.0), None
        )

    def _fake_ffmpeg(self, monkeypatch: pytest.MonkeyPatch, after: Any = None) -> list[str]:
        """`proc.run` writes the file it was asked for; `after()` runs when it has written it."""
        asked: list[str] = []

        def run(args: list[str], **_k: object) -> None:
            asked.append(args[-1])
            Path(args[-1]).write_bytes(b"mine")
            if after is not None:
                after()

        monkeypatch.setattr(proc, "run", run)
        return asked

    def test_workfiles_concurrent_the_partial_has_the_pid_and_everything_is_written(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = self._fake_ffmpeg(monkeypatch)
        dst = self._dst(project)
        self._build(project, dst)
        assert Path(asked[0]).name == f"a1_clip.{os.getpid()}.partial.wav"
        assert dst.read_bytes() == b"mine"
        sidecar = json.loads(workfiles.sidecar_path(dst).read_text(encoding="utf-8"))
        assert sidecar == WAV_SIDECAR
        assert sorted(p.name for p in dst.parent.iterdir()) == ["a1_clip.wav", "a1_clip.wav.json"]

    def test_workfiles_concurrent_the_finally_deletes_only_its_own_partial(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._fake_ffmpeg(monkeypatch)
        dst = self._dst(project)
        dst.parent.mkdir(parents=True)
        theirs = dst.parent / "a1_clip.99999.partial.wav"
        theirs.write_bytes(b"another process is writing this")
        self._build(project, dst)
        assert theirs.read_bytes() == b"another process is writing this"

    def test_workfiles_concurrent_a_failed_build_leaves_no_partial_of_its_own(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def run(args: list[str], **_k: object) -> None:
            Path(args[-1]).write_bytes(b"half")
            raise RuntimeError("ffmpeg died")

        monkeypatch.setattr(proc, "run", run)
        dst = self._dst(project)
        with pytest.raises(RuntimeError):
            self._build(project, dst)
        assert list(dst.parent.iterdir()) == []

    def _other_finishes(self, dst: Path) -> Any:
        def done() -> None:
            dst.write_bytes(b"theirs")
            workfiles.sidecar_path(dst).write_text(json.dumps(WAV_SIDECAR), encoding="utf-8")

        return done

    def test_workfiles_concurrent_a_file_that_is_fresh_when_the_partial_is_done_is_used(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        self._fake_ffmpeg(monkeypatch, after=self._other_finishes(dst))
        replaced: list[object] = []
        monkeypatch.setattr(os, "replace", lambda *a: replaced.append(a))
        self._build(project, dst)
        assert dst.read_bytes() == b"theirs" and replaced == []
        assert sorted(p.name for p in dst.parent.iterdir()) == ["a1_clip.wav", "a1_clip.wav.json"]

    def test_workfiles_concurrent_a_replace_that_is_refused_over_a_fresh_file_uses_it(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other process has not written its sidecar at the first look, and has by the time
        the replace is refused (it is reading the file)."""
        dst = self._dst(project)
        self._fake_ffmpeg(monkeypatch, after=lambda: dst.write_bytes(b"theirs"))

        def refused(_src: object, _dst: object) -> None:
            workfiles.sidecar_path(dst).write_text(json.dumps(WAV_SIDECAR), encoding="utf-8")
            raise PermissionError(13, "Access is denied", str(dst))

        monkeypatch.setattr(os, "replace", refused)
        self._build(project, dst)
        assert dst.read_bytes() == b"theirs"
        assert sorted(p.name for p in dst.parent.iterdir()) == ["a1_clip.wav", "a1_clip.wav.json"]

    def test_workfiles_concurrent_a_replace_that_is_refused_over_a_file_that_is_not_fresh_is_exit_3(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        self._fake_ffmpeg(monkeypatch, after=lambda: dst.write_bytes(b"theirs, no sidecar"))

        def refused(_src: object, _dst: object) -> None:
            raise PermissionError(13, "Access is denied", str(dst))

        monkeypatch.setattr(os, "replace", refused)
        monkeypatch.setattr(sidecar_module, "LAND_WAIT_S", 0.0)  # 001.29: no real wait
        with pytest.raises(ProjectError) as info:
            self._build(project, dst)
        # 001.28: the file is named by class and clip, not by path (was `cierra el archivo`)
        assert info.value.exit_code == 3
        assert info.value.message_es == "cierra el wav48 de a1 en el reproductor y repite"
        assert [p.name for p in dst.parent.iterdir()] == ["a1_clip.wav"]  # its partial is gone
