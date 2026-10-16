"""proc.tool_path: never the cwd, always absolute, never .bat/.cmd (spec 0.8, 0.10.11)."""

import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from kcut import proc
from kcut.errors import MissingDependency

NO_CWD_ENV = "NoDefaultCurrentDirectoryInExePath"
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="regla propia de Windows")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """tool_path sets a process-wide variable on Windows: put the original state back."""
    saved = os.environ.pop(NO_CWD_ENV, None)
    monkeypatch.delenv("KCUT_FFMPEG", raising=False)
    monkeypatch.delenv("KCUT_FFPROBE", raising=False)
    yield
    if saved is None:
        os.environ.pop(NO_CWD_ENV, None)
    else:
        os.environ[NO_CWD_ENV] = saved


def _fake_exe(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b"MZ not a real program")
    return path


class TestSearchPath:
    @windows_only
    def test_planted_exe_in_cwd_is_not_chosen(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        planted = _fake_exe(tmp_path / "crudo", "ffmpeg.exe")
        empty_bin = tmp_path / "bin"
        empty_bin.mkdir()
        monkeypatch.chdir(planted.parent)
        monkeypatch.setenv("PATH", str(empty_bin))
        # Premise: without the protection Windows really would pick the planted file.
        assert shutil.which("ffmpeg") is not None
        with pytest.raises(MissingDependency) as info:
            proc.tool_path("ffmpeg")
        assert info.value.exit_code == 7

    @windows_only
    def test_protection_variable_is_set_before_which(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        seen: list[str | None] = []
        real = _fake_exe(tmp_path / "bin", "ffmpeg.exe")

        def spy(name: str) -> str:
            seen.append(os.environ.get(NO_CWD_ENV))
            return str(real)

        monkeypatch.setattr(shutil, "which", spy)
        proc.tool_path("ffmpeg")
        assert seen == ["1"]

    @windows_only
    def test_real_path_entry_wins_over_the_planted_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        planted = _fake_exe(tmp_path / "crudo", "ffmpeg.exe")
        real = _fake_exe(tmp_path / "bin", "ffmpeg.exe")
        monkeypatch.chdir(planted.parent)
        monkeypatch.setenv("PATH", str(real.parent))
        assert proc.tool_path("ffmpeg") == real.resolve()

    def test_result_is_absolute(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        real = _fake_exe(tmp_path / "bin", "ffprobe.exe")
        monkeypatch.setenv("PATH", str(real.parent))
        monkeypatch.chdir(tmp_path)
        path = proc.tool_path("ffprobe")
        assert path.is_absolute()
        assert path == real.resolve()

    def test_relative_result_from_which_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda _name: os.path.join("bin", "ffmpeg.exe"))
        with pytest.raises(MissingDependency, match="relativa"):
            proc.tool_path("ffmpeg")

    def test_nothing_on_path_is_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("PATH", str(tmp_path))
        with pytest.raises(MissingDependency):
            proc.tool_path("ffmpeg")

    @windows_only
    @pytest.mark.parametrize("name", ["ffmpeg.bat", "ffmpeg.cmd", "ffmpeg.BAT"])
    def test_which_returning_a_script_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
    ) -> None:
        script = _fake_exe(tmp_path, name)
        monkeypatch.setattr(shutil, "which", lambda _name: str(script))
        with pytest.raises(MissingDependency) as info:
            proc.tool_path("ffmpeg")
        assert info.value.exit_code == 7
        assert ".exe" in info.value.message_es

    @windows_only
    def test_com_suffix_is_accepted(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        program = _fake_exe(tmp_path, "ffmpeg.com")
        monkeypatch.setattr(shutil, "which", lambda _name: str(program))
        assert proc.tool_path("ffmpeg") == program.resolve()


class TestEnvironmentOverride:
    @windows_only
    @pytest.mark.parametrize("name", ["ffmpeg.cmd", "ffmpeg.bat", "ffmpeg.CMD"])
    def test_script_override_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
    ) -> None:
        script = _fake_exe(tmp_path, name)
        monkeypatch.setenv("KCUT_FFMPEG", str(script))
        with pytest.raises(MissingDependency) as info:
            proc.tool_path("ffmpeg")
        assert info.value.exit_code == 7
        assert "KCUT_FFMPEG" in info.value.message_es

    @windows_only
    def test_script_override_for_ffprobe_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("KCUT_FFPROBE", str(_fake_exe(tmp_path, "ffprobe.cmd")))
        with pytest.raises(MissingDependency, match="KCUT_FFPROBE"):
            proc.tool_path("ffprobe")

    def test_relative_override_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _fake_exe(tmp_path, "ffmpeg.exe")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KCUT_FFMPEG", "ffmpeg.exe")
        with pytest.raises(MissingDependency, match="absoluta"):
            proc.tool_path("ffmpeg")

    def test_missing_file_override_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("KCUT_FFMPEG", str(tmp_path / "no-existe.exe"))
        with pytest.raises(MissingDependency, match="no existe"):
            proc.tool_path("ffmpeg")

    def test_directory_override_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("KCUT_FFMPEG", str(tmp_path))
        with pytest.raises(MissingDependency):
            proc.tool_path("ffmpeg")

    @pytest.mark.parametrize("name", ["ffmpeg.exe", "FFMPEG.EXE"])
    def test_exe_override_is_accepted_and_returned_absolute(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
    ) -> None:
        program = _fake_exe(tmp_path, name)
        monkeypatch.setenv("KCUT_FFMPEG", str(program))
        assert proc.tool_path("ffmpeg") == program.resolve()

    def test_override_beats_the_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        on_path = _fake_exe(tmp_path / "bin", "ffprobe.exe")
        chosen = _fake_exe(tmp_path / "otro", "ffprobe.exe")
        monkeypatch.setenv("PATH", str(on_path.parent))
        monkeypatch.setenv("KCUT_FFPROBE", str(chosen))
        assert proc.tool_path("ffprobe") == chosen.resolve()

    def test_no_cache_between_calls(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        first = _fake_exe(tmp_path / "a", "ffmpeg.exe")
        second = _fake_exe(tmp_path / "b", "ffmpeg.exe")
        monkeypatch.setenv("KCUT_FFMPEG", str(first))
        assert proc.tool_path("ffmpeg") == first.resolve()
        monkeypatch.setenv("KCUT_FFMPEG", str(second))
        assert proc.tool_path("ffmpeg") == second.resolve()


@windows_only
def test_symlink_exe_to_cmd_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Resolve first, then check the suffix: `ffmpeg.exe` -> `real.cmd` is a script in disguise."""
    real = _fake_exe(tmp_path, "real.cmd")
    link = tmp_path / "ffmpeg.exe"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"sin privilegio para crear symlinks en Windows: {exc}")
    monkeypatch.setenv("KCUT_FFMPEG", str(link))
    with pytest.raises(MissingDependency) as info:
        proc.tool_path("ffmpeg")
    assert info.value.exit_code == 7
    assert ".cmd" in info.value.message_es


@windows_only
def test_suffix_is_checked_on_the_resolved_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Same rule as the symlink test, but simulated so it needs no symlink privilege."""
    real = _fake_exe(tmp_path, "real.cmd")
    disguised = _fake_exe(tmp_path, "ffmpeg.exe")
    original = Path.resolve

    def fake_resolve(self: Path, strict: bool = False) -> Path:
        return original(real if self == disguised else self, strict=strict)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    monkeypatch.setenv("KCUT_FFMPEG", str(disguised))
    with pytest.raises(MissingDependency, match=r"\.cmd") as info:
        proc.tool_path("ffmpeg")
    assert info.value.exit_code == 7


def test_which_result_that_does_not_exist_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: str(tmp_path / "fantasma.exe"))
    with pytest.raises(MissingDependency, match="no existe"):
        proc.tool_path("ffmpeg")
