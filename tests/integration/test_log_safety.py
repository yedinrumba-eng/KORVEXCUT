"""The run log lives in `.kcut/logs/`: a planted hard link must never write into `crudo/`."""

import argparse
import os
import sys
from pathlib import Path

import pytest

from kcut import cli, proc
from kcut.commands import doctor
from kcut.logfile import append_log, create_log, set_log_root, unsafe_reason
from tests.conftest import run_kcut
from tests.fixtures.links import make_hard_link
from tests.integration.ingest_helpers import snapshot


@pytest.fixture(autouse=True)
def _no_log_root() -> object:
    set_log_root(None)
    yield None
    set_log_root(None)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    (root / "crudo" / "nota.txt").write_text("texto del usuario", encoding="utf-8")
    return root


def _python() -> str:
    return str(getattr(sys, "_base_executable", None) or sys.executable)


class TestAppendLog:
    def test_append_rejects_a_path_with_two_links(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        original = tmp_path / "importante.txt"
        original.write_text("contenido original", encoding="utf-8")
        planted = tmp_path / "run.log"
        make_hard_link(planted, original)
        assert os.lstat(planted).st_nlink == 2
        assert unsafe_reason(planted) == "tiene 2 enlaces duros"

        append_log(planted, "esto no debe llegar al archivo\n")

        assert original.read_text(encoding="utf-8") == "contenido original"
        err = capsys.readouterr().err
        assert "enlaces duros" in err
        assert "esto no debe llegar al archivo" in err  # the text is not lost: it goes to stderr

    def test_the_warning_is_printed_once_per_log(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        original = tmp_path / "a.txt"
        original.write_text("a", encoding="utf-8")
        planted = tmp_path / "otra vez.log"
        make_hard_link(planted, original)
        for _ in range(3):
            append_log(planted, "x\n")
        assert capsys.readouterr().err.count("[AVISO]") == 1

    def test_append_refuses_a_symlink(self, tmp_path: Path) -> None:
        target = tmp_path / "real.txt"
        target.write_text("real", encoding="utf-8")
        link = tmp_path / "enlace.log"
        try:
            os.symlink(target, link)
        except OSError as exc:
            pytest.skip(f"sin privilegio para crear symlinks: {exc}")
        append_log(link, "no\n")
        assert target.read_text(encoding="utf-8") == "real"

    def test_append_refuses_a_directory(self, tmp_path: Path) -> None:
        folder = tmp_path / "carpeta.log"
        folder.mkdir()
        assert unsafe_reason(folder) is not None
        append_log(folder, "no\n")
        assert list(folder.iterdir()) == []

    def test_a_log_outside_the_cache_is_refused_once_the_root_is_set(self, tmp_path: Path) -> None:
        cache = tmp_path / ".kcut"
        (cache / "logs").mkdir(parents=True)
        set_log_root(cache)
        inside, outside = cache / "logs" / "ok.log", tmp_path / "fuera.log"
        append_log(inside, "dentro\n")
        append_log(outside, "fuera\n")
        assert inside.read_text(encoding="utf-8") == "dentro\n"
        assert not outside.exists()

    def test_a_normal_log_still_appends_in_order_with_unix_newlines(self, tmp_path: Path) -> None:
        log = tmp_path / "ok.log"
        assert create_log(log)
        append_log(log, "uno\n")
        append_log(log, "dos\n")
        assert log.read_bytes() == b"uno\ndos\n"

    def test_children_write_to_the_same_checked_log(self, tmp_path: Path) -> None:
        log = tmp_path / "hijos.log"
        proc.run([_python(), "-c", "import sys; sys.stderr.write('hola\\n')"], log=log)
        text = log.read_text(encoding="utf-8")
        assert text.startswith("$ ") and "hola" in text and "[exit 0" in text

    def test_children_cannot_write_through_a_hard_link_either(self, tmp_path: Path) -> None:
        original = tmp_path / "intacto.txt"
        original.write_text("intacto", encoding="utf-8")
        planted = tmp_path / "hijo.log"
        make_hard_link(planted, original)
        proc.run([_python(), "-c", "pass"], log=planted)
        assert original.read_text(encoding="utf-8") == "intacto"


class TestCreation:
    def test_creation_is_exclusive(self, tmp_path: Path) -> None:
        log = tmp_path / "unico.log"
        assert create_log(log) is True
        log.write_text("ya hay algo\n", encoding="utf-8")
        assert create_log(log) is False
        assert log.read_text(encoding="utf-8") == "ya hay algo\n"

    def test_the_name_carries_the_pid_and_the_log_exists_empty(
        self, monkeypatch: pytest.MonkeyPatch, project: Path
    ) -> None:
        seen: list[Path | None] = []

        def run(args: argparse.Namespace) -> int:
            seen.append(args.log)
            return 0

        monkeypatch.setattr(doctor, "run", run)
        assert cli.main(["doctor", "--project", str(project)]) == 0
        (log,) = seen
        assert log is not None and log.name.endswith(f"-{os.getpid()}.log")
        assert log.parent == project / ".kcut" / "logs"
        assert log.is_file() and os.lstat(log).st_nlink == 1

    def test_a_planted_hard_link_with_the_chosen_name_cannot_hurt_the_footage(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        raw = project / "crudo" / "nota.txt"
        planted = project / ".kcut" / "logs" / "doctor-fijo-1.log"
        planted.parent.mkdir(parents=True)
        make_hard_link(planted, raw)
        before = snapshot(project / "crudo")
        monkeypatch.setattr(cli, "log_path", lambda *_a, **_k: planted)

        def boom(_args: argparse.Namespace) -> int:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(doctor, "run", boom)
        assert cli.main(["doctor", "--project", str(project)]) == 10

        assert snapshot(project / "crudo") == before
        assert raw.read_text(encoding="utf-8") == "texto del usuario"
        assert "no pude crear el log" in capsys.readouterr().err

    def test_a_log_swapped_for_a_hard_link_after_creation_is_not_written(
        self, monkeypatch: pytest.MonkeyPatch, project: Path
    ) -> None:
        raw = project / "crudo" / "nota.txt"
        before = snapshot(project / "crudo")

        def swap_then_fail(args: argparse.Namespace) -> int:
            os.unlink(args.log)
            make_hard_link(args.log, raw)  # the attacker wins the race after creation
            proc.run([_python(), "-c", "import sys; sys.stderr.write('x\\n')"], log=args.log)
            raise RuntimeError("kaboom")

        monkeypatch.setattr(doctor, "run", swap_then_fail)
        assert cli.main(["doctor", "--project", str(project)]) == 10
        assert snapshot(project / "crudo") == before
        assert raw.read_text(encoding="utf-8") == "texto del usuario"

    def test_a_full_ingest_with_a_hard_linked_log_directory_entry_leaves_crudo_alone(
        self, project: Path
    ) -> None:
        raw = project / "crudo" / "nota.txt"
        logs = project / ".kcut" / "logs"
        logs.mkdir(parents=True)
        for name in ("ingest-20260101-000000-1.log", "ingest-20260101-000000-2.log"):
            make_hard_link(logs / name, raw)
        before = snapshot(project / "crudo")
        result = run_kcut("ingest", "--project", str(project), "--json")
        assert result.returncode == 0, result.stderr
        assert snapshot(project / "crudo") == before
