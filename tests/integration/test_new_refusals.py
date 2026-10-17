"""`kcut new` refusals and what it does with an existing folder (it never overwrites)."""

import hashlib
import json
from pathlib import Path

import pytest

from kcut import cli
from tests.conftest import run_kcut

REPO = Path(__file__).parents[2]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "proyecto ñandú"


def _new(root: Path, *extra: str) -> tuple[int, dict[str, object]]:
    result = run_kcut("new", str(root), "--json", *extra)
    return result.returncode, json.loads(result.stdout)


class TestRefusals:
    def test_inside_a_kcut_checkout(self, tmp_path: Path) -> None:
        package = tmp_path / "repo" / "src" / "kcut"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        target = tmp_path / "repo" / "videos" / "mio"
        code, doc = _new(target)
        assert code == 3
        assert "repo de kcut" in str(doc["error"])
        assert not target.exists()

    def test_inside_the_real_repo(self) -> None:
        target = REPO / "video-que-no-debe-existir"
        result = run_kcut("new", str(target), "--json")
        assert result.returncode == 3
        assert not target.exists()

    def test_over_an_existing_project(self, root: Path) -> None:
        assert _new(root)[0] == 0
        before = hashlib.sha256((root / "kcut.toml").read_bytes()).hexdigest()
        (root / "edit" / "estrategia.md").write_text("mi trabajo", encoding="utf-8")
        code, doc = _new(root)
        assert code == 3
        assert "ya es un proyecto" in str(doc["error"])
        assert hashlib.sha256((root / "kcut.toml").read_bytes()).hexdigest() == before
        assert (root / "edit" / "estrategia.md").read_text(encoding="utf-8") == "mi trabajo"

    def test_the_target_is_a_file(self, root: Path) -> None:
        root.write_text("soy un archivo", encoding="utf-8")
        assert _new(root)[0] == 3

    def test_json_error_document_is_the_only_stdout(self, root: Path) -> None:
        _new(root)
        result = run_kcut("new", str(root), "--json")
        doc = json.loads(result.stdout)
        assert doc["error"]["kind"] == "ProjectError"
        assert doc["error"]["exit_code"] == 3


class TestExistingFolder:
    def test_existing_files_are_kept_and_reported(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (root / "sueltos").mkdir(parents=True)
        (root / "video1.mov").write_bytes(b"a")
        (root / "sueltos" / "nota.txt").write_bytes(b"b")
        assert cli.main(["new", str(root)]) == 0
        out = capsys.readouterr().out
        assert "[AVISO] hay 2 archivos fuera de crudo/; muévelos a crudo/" in out
        assert (root / "video1.mov").read_bytes() == b"a"
        assert (root / "sueltos" / "nota.txt").read_bytes() == b"b"
        assert (root / "kcut.toml").is_file()

    def test_files_already_in_crudo_are_not_stray(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (root / "crudo").mkdir(parents=True)
        (root / "crudo" / "a.mov").write_bytes(b"a")
        assert cli.main(["new", str(root)]) == 0
        assert "fuera de crudo" not in capsys.readouterr().out
        assert (root / "crudo" / "a.mov").read_bytes() == b"a"

    def test_in_json_mode_the_warning_goes_to_stderr(self, root: Path) -> None:
        root.mkdir()
        (root / "suelto.mov").write_bytes(b"a")
        result = run_kcut("new", str(root), "--json")
        assert result.returncode == 0
        assert "fuera de crudo" in result.stderr
        assert json.loads(result.stdout)["ok"] is True

    def test_human_output_uses_ascii_tags_and_no_long_dashes(self, root: Path) -> None:
        result = run_kcut("new", str(root))
        assert result.returncode == 0
        assert "[OK] creado kcut.toml" in result.stdout
        assert "[INFO]" in result.stdout
        assert "—" not in result.stdout


class TestNeverOverwritesMore:
    @pytest.mark.parametrize("folder", ["recursos", "edit", "salida", "qa", ".kcut"])
    def test_any_layout_folder_that_is_a_file_is_refused_before_anything_is_made(
        self, root: Path, folder: str
    ) -> None:
        root.mkdir()
        (root / folder).write_text("x", encoding="utf-8")
        assert _new(root)[0] == 3
        assert sorted(p.name for p in root.iterdir()) == [folder]

    @pytest.mark.parametrize(
        "rel", ["recursos/recursos.json", "edit/versiones.md", "edit/estrategia.md"]
    )
    def test_a_starter_file_that_is_a_folder_is_refused_before_anything_is_made(
        self, root: Path, rel: str
    ) -> None:
        (root / rel).mkdir(parents=True)
        before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
        assert _new(root)[0] == 3
        assert sorted(str(p.relative_to(root)) for p in root.rglob("*")) == before
        assert not (root / "kcut.toml").exists()

    def test_kcut_toml_is_written_last(
        self, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from kcut.commands import new as new_module

        real = new_module._create_new

        def failing(path: Path, text: str) -> bool:
            if path.name == "estrategia.md":
                raise OSError("disco lleno")
            return real(path, text)

        monkeypatch.setattr(new_module, "_create_new", failing)
        assert cli.main(["new", str(root), "--json"]) == 3
        assert "disco lleno" in capsys.readouterr().out
        assert not (root / "kcut.toml").exists()

    def test_created_lists_only_what_was_made(self, root: Path) -> None:
        (root / "crudo").mkdir(parents=True)
        (root / "crudo" / "a.mov").write_bytes(b"a")
        (root / "edit").mkdir()
        code, doc = _new(root)
        assert code == 0
        created = doc["created"]
        assert isinstance(created, list)
        assert "crudo/" not in created and "edit/" not in created
        assert "edit/estrategia.md" in created and "edit/versiones.md" in created
        assert (root / "crudo" / "a.mov").read_bytes() == b"a"

    def test_a_folder_with_everything_but_kcut_toml_only_gets_kcut_toml(self, root: Path) -> None:
        assert _new(root)[0] == 0
        (root / "kcut.toml").unlink()
        strategy = (root / "edit" / "estrategia.md").read_bytes()
        code, doc = _new(root)
        assert code == 0
        assert doc["created"] == ["kcut.toml"]
        assert (root / "edit" / "estrategia.md").read_bytes() == strategy
