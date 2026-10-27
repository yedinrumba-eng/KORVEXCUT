"""The lock of an output (spec S1.5b row 3, DS11): one process at a time, taken without waiting and
released by the system. And `atomic_replace`, which moves a finished file over the final one.
"""

import hashlib
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from kcut.errors import LockedError, ProjectError
from kcut.render.lock import OutputLock, atomic_replace

HOLDER = (
    "import sys\n"
    "from pathlib import Path\n"
    "from kcut.render.lock import OutputLock\n"
    "with OutputLock(Path(sys.argv[1]), sys.argv[2]):\n"
    "    print('held', flush=True)\n"
    "    sys.stdin.readline()\n"
)


def _taken_soon(locks: Path, name: str, within_s: float = 10.0) -> None:
    """Take the lock `name` once, trying again for up to `within_s` seconds if it is still held.

    Windows frees the locks of a process a moment AFTER `wait()` says it is gone (its handles are
    closed while it is torn down), so right after a process ends the lock may still be taken."""
    deadline = time.monotonic() + within_s
    while True:
        try:
            with OutputLock(locks, name):
                return
        except LockedError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)


@pytest.fixture
def locks(tmp_path: Path) -> Path:
    return tmp_path / "proyecto ñandú" / ".kcut" / "locks"


class TestOutputLock:
    def test_lock_a_second_lock_of_the_same_name_is_refused_with_exit_6(self, locks: Path) -> None:
        with OutputLock(locks, "build-v1"):
            with pytest.raises(LockedError) as info, OutputLock(locks, "build-v1"):
                pytest.fail("the second lock was given")
            assert info.value.exit_code == 6 and "build-v1" in info.value.message_es

    def test_lock_it_is_released_on_leaving_the_with(self, locks: Path) -> None:
        with OutputLock(locks, "build-v1"):
            pass
        with OutputLock(locks, "build-v1"):
            pass  # taken again: it was released

    def test_lock_it_is_released_when_the_body_fails(self, locks: Path) -> None:
        with pytest.raises(RuntimeError), OutputLock(locks, "build-v1"):
            raise RuntimeError("boom")
        with OutputLock(locks, "build-v1"):
            pass

    def test_lock_another_name_is_another_lock(self, locks: Path) -> None:
        with OutputLock(locks, "build-v1"), OutputLock(locks, "build-v2"):
            pass

    def test_lock_a_refused_lock_does_not_free_the_one_that_holds_it(self, locks: Path) -> None:
        with OutputLock(locks, "build-v1"):
            with pytest.raises(LockedError), OutputLock(locks, "build-v1"):
                pass
            with pytest.raises(LockedError), OutputLock(locks, "build-v1"):
                pass  # still held after the refusal

    def test_lock_the_folder_is_made_and_the_file_says_who_holds_it(self, locks: Path) -> None:
        assert not locks.exists()
        with OutputLock(locks, "build-v3") as lock:
            lines = lock.path.read_text(encoding="utf-8").splitlines()
            assert lines[0].startswith("pid ") and lines[0].split()[1].isdigit()
            assert len(lines) == 2 and lock.path.name == "build-v3.lock"

    @pytest.mark.parametrize("name", ["", "a/b", "a\\b", "c:x", ".hidden", "../x"])
    def test_lock_a_name_that_is_not_a_plain_name_is_a_bug_of_the_caller(
        self, locks: Path, name: str
    ) -> None:
        with pytest.raises(ValueError, match="nombre de lock"):
            OutputLock(locks, name)


class TestLockFileIsSafe:
    """001.25 point 2 (rows 33 and 42): the lock is written in place, so a hard link to a file of
    `crudo/`, a link or a folder at its place is a ProjectError and nothing is written."""

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_lock_hardlink_a_second_name_of_another_file_is_refused_and_not_touched(
        self, locks: Path, tmp_path: Path
    ) -> None:
        crudo = tmp_path / "crudo" / "cam a.mp4"
        crudo.parent.mkdir()
        crudo.write_bytes(b"the footage " * 1000)
        before = self._sha(crudo)
        locks.mkdir(parents=True)
        os.link(crudo, locks / "build-v1.lock")
        with pytest.raises(ProjectError) as info, OutputLock(locks, "build-v1"):
            pytest.fail("the lock was given on a hard link")
        assert info.value.exit_code == 3 and "enlaces duros" in info.value.message_es
        assert self._sha(crudo) == before and crudo.stat().st_size == 12000

    def test_lock_hardlink_the_check_is_on_the_open_handle_not_only_on_the_name(
        self, locks: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The link appears between looking at the name and opening it: `fstat` still sees it."""
        crudo = tmp_path / "crudo.mp4"
        crudo.write_bytes(b"x" * 100)
        locks.mkdir(parents=True)
        real_open = os.open

        def open_after_the_link(path: object, flags: int, mode: int = 0o777) -> int:
            os.link(crudo, str(path))
            return real_open(path, flags, mode)  # type: ignore[arg-type]

        monkeypatch.setattr(os, "open", open_after_the_link)
        with pytest.raises(ProjectError, match="enlaces duros"), OutputLock(locks, "build-v1"):
            pass
        monkeypatch.undo()
        assert crudo.read_bytes() == b"x" * 100

    def test_lock_hardlink_an_ordinary_lock_file_is_taken_again_and_again(
        self, locks: Path
    ) -> None:
        for _ in range(3):
            with OutputLock(locks, "build-v1") as lock:
                assert lock.path.stat().st_nlink == 1

    def test_lock_render_dest_dir_a_folder_at_the_lock_is_a_project_error(
        self, locks: Path
    ) -> None:
        (locks / "build-v1.lock").mkdir(parents=True)
        with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo"):
            OutputLock(locks, "build-v1").__enter__()

    def test_lock_render_dest_dir_a_read_only_lock_is_a_project_error(self, locks: Path) -> None:
        locks.mkdir(parents=True)
        lock = locks / "build-v1.lock"
        lock.write_text("pid 1\n", encoding="utf-8")
        lock.chmod(stat.S_IREAD)
        try:
            with pytest.raises(ProjectError) as info, OutputLock(locks, "build-v1"):
                pytest.fail("a read-only lock was given")
            assert info.value.exit_code == 3 and "no pude abrir el lock" in info.value.message_es
        finally:
            lock.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_lock_render_dest_dir_the_folder_of_the_locks_being_a_file_is_a_project_error(
        self, tmp_path: Path
    ) -> None:
        blocker = tmp_path / "locks"
        blocker.write_text("no soy una carpeta", encoding="utf-8")
        with pytest.raises(ProjectError, match="no pude abrir el lock"):
            OutputLock(blocker, "build-v1").__enter__()


class TestAnotherProcess:
    """The lock is the system's, so it works between processes and goes away with the process."""

    def _start(self, locks: Path, name: str) -> subprocess.Popen[str]:
        child = subprocess.Popen(
            [sys.executable, "-I", "-X", "utf8", "-c", HOLDER, str(locks), name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "held", child.stderr
        return child

    def test_lock_a_process_that_holds_it_keeps_this_one_out_until_it_ends(
        self, locks: Path
    ) -> None:
        child = self._start(locks, "build-v1")
        try:
            with pytest.raises(LockedError), OutputLock(locks, "build-v1"):
                pass
            with OutputLock(locks, "build-v2"):  # another output is free
                pass
        finally:
            child.kill()
            child.wait(timeout=30)
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream is not None:
                    stream.close()
        _taken_soon(locks, "build-v1")  # a process that dies does not leave it taken

    def test_lock_a_process_that_ends_in_order_frees_it_too(self, locks: Path) -> None:
        child = self._start(locks, "build-v1")
        assert child.stdin is not None
        child.stdin.write("\n")
        child.stdin.flush()
        assert child.wait(timeout=30) == 0
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream is not None:
                stream.close()
        _taken_soon(locks, "build-v1")


class TestAtomicReplace:
    def test_replace_a_new_file_takes_the_place_of_the_old_one(self, tmp_path: Path) -> None:
        final, partial = tmp_path / "video.mp4", tmp_path / "video.partial.mp4"
        final.write_bytes(b"old")
        partial.write_bytes(b"new")
        atomic_replace(partial, final)
        assert final.read_bytes() == b"new" and not partial.exists()

    def test_replace_it_works_when_there_is_no_old_file(self, tmp_path: Path) -> None:
        final, partial = tmp_path / "video.mp4", tmp_path / "video.partial.mp4"
        partial.write_bytes(b"new")
        atomic_replace(partial, final)
        assert final.read_bytes() == b"new"

    def test_replace_a_folder_where_the_file_goes_says_so(self, tmp_path: Path) -> None:
        final, partial = tmp_path / "video.mp4", tmp_path / "video.partial.mp4"
        final.mkdir()
        partial.write_bytes(b"new")
        with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo"):
            atomic_replace(partial, final)
        assert partial.read_bytes() == b"new"  # the finished file is not lost

    @pytest.mark.skipif(
        sys.platform != "win32", reason="only Windows refuses to replace an open file"
    )
    def test_replace_a_file_a_player_has_open_says_to_close_it(self, tmp_path: Path) -> None:
        final, partial = tmp_path / "video.mp4", tmp_path / "video.partial.mp4"
        final.write_bytes(b"old")
        partial.write_bytes(b"new")
        with final.open("rb"), pytest.raises(ProjectError, match=r"cierra el archivo .* repite"):
            atomic_replace(partial, final)
        assert partial.read_bytes() == b"new"
