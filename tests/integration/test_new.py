"""`kcut new`: layout, refusals (inside the repo, existing project), options and safety."""

import json
import shutil
from pathlib import Path

import pytest

from kcut import cli
from kcut.config.load import load_config
from kcut.project import open_project
from tests.conftest import run_kcut
from tests.fixtures.links import make_dir_link
from tests.integration.ingest_helpers import snapshot

REPO = Path(__file__).parents[2]
FOLDERS = ["crudo", "recursos", "edit", "salida", "qa", ".kcut"]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "proyecto ñandú"


def _new(root: Path, *extra: str) -> tuple[int, dict[str, object]]:
    result = run_kcut("new", str(root), "--json", *extra)
    return result.returncode, json.loads(result.stdout)


class TestLayout:
    def test_creates_everything_of_spec_0_3(self, root: Path) -> None:
        code, doc = _new(root)
        assert code == 0
        for folder in FOLDERS:
            assert (root / folder).is_dir(), folder
        for name in (
            "kcut.toml",
            "recursos/recursos.json",
            "edit/estrategia.md",
            "edit/versiones.md",
        ):
            assert (root / name).is_file(), name
        assert doc["ok"] is True
        assert doc["project"] == str(root.resolve())
        created = doc["created"]
        assert isinstance(created, list)
        assert created[0] == "kcut.toml"
        assert "crudo/" in created
        assert "recursos/recursos.json" in created
        assert "edit/estrategia.md" in created

    def test_the_project_it_creates_opens_and_loads(self, root: Path) -> None:
        assert _new(root)[0] == 0
        project = open_project(str(root))
        assert project.root == root.resolve()
        assert project.config.project.name == "proyecto ñandú"
        assert (project.config.output.preset, project.config.output.fps) == ("9:16", 30)

    def test_manifest_starts_empty(self, root: Path) -> None:
        _new(root)
        data = json.loads((root / "recursos" / "recursos.json").read_text(encoding="utf-8"))
        assert data == {"schema": "kcut.recursos/1", "items": []}

    def test_versions_file(self, root: Path) -> None:
        _new(root, "--name", "Piloto 01")
        text = (root / "edit" / "versiones.md").read_text(encoding="utf-8")
        assert text == "# Versiones - Piloto 01\n"

    def test_strategy_front_matter_is_exact_and_not_approved(self, root: Path) -> None:
        _new(root, "--name", "Piloto 01")
        text = (root / "edit" / "estrategia.md").read_bytes().decode("utf-8")
        assert text == (
            "---\nvideo: Piloto 01\nformato: 9:16 · 1080x1920 · 30 fps\n"
            "aprobado: no\naprobado_por:\n---\n# Estrategia de corte - Piloto 01\n"
        )

    def test_files_use_unix_newlines_and_utf8(self, root: Path) -> None:
        _new(root)
        for name in ("kcut.toml", "edit/estrategia.md", "edit/versiones.md"):
            data = (root / name).read_bytes()
            assert b"\r" not in data
            data.decode("utf-8")

    def test_default_name_is_the_folder_name(self, root: Path) -> None:
        _new(root)
        assert load_config(root / "kcut.toml").project.name == "proyecto ñandú"


class TestOptions:
    def test_name_preset_fps_and_language(self, root: Path) -> None:
        code, _ = _new(
            root, "--name", "Mi video", "--preset", "16:9", "--fps", "24", "--lang", "en"
        )
        assert code == 0
        cfg = load_config(root / "kcut.toml")
        assert cfg.project.name == "Mi video"
        assert (cfg.output.preset, cfg.output.w, cfg.output.h, cfg.output.fps) == (
            "16:9",
            1920,
            1080,
            24,
        )
        assert (cfg.output.safe_top_px, cfg.output.safe_bottom_px) == (60, 120)
        assert cfg.project.language == "en"
        assert cfg.transcribe.fillers == ("uh", "um", "uhm", "er", "hmm")
        front = (root / "edit" / "estrategia.md").read_text(encoding="utf-8")
        assert "formato: 16:9 · 1920x1080 · 24 fps" in front

    def test_fps_outside_the_allowed_set_is_a_project_error(self, root: Path) -> None:
        code, doc = _new(root, "--fps", "31")
        assert code == 3
        assert doc["ok"] is False
        assert not root.exists()

    def test_unknown_preset_is_a_usage_error(self, root: Path) -> None:
        assert run_kcut("new", str(root), "--preset", "4:3").returncode == 2
        assert not root.exists()

    def test_non_numeric_fps_is_a_usage_error(self, root: Path) -> None:
        assert run_kcut("new", str(root), "--fps", "rapido").returncode == 2

    def test_bad_language_code(self, root: Path) -> None:
        code, _ = _new(root, "--lang", "ESP")
        assert code == 3
        assert not root.exists()

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "x" * 81,
            "linea1\nlinea2",
            "tab\there",
            "a b",
            "a b",
            "a\u0085b",
            "a‮b",
            "a​b",
        ],
    )
    def test_bad_names_are_usage_errors_and_create_nothing(self, root: Path, name: str) -> None:
        result = run_kcut("new", str(root), "--json", "--name", name)
        assert result.returncode == 2
        assert json.loads(result.stdout)["error"]["kind"] == "UsageError"
        assert not root.exists()

    def test_a_name_cannot_forge_the_approval_gate(self, root: Path) -> None:
        for forged in ("video\naprobado: si", "video aprobado: si", "video\u0085aprobado: si"):
            assert run_kcut("new", str(root), "--name", forged).returncode == 2
        assert not root.exists()

    def test_a_name_of_exactly_80_characters_is_fine(self, root: Path) -> None:
        assert _new(root, "--name", "n" * 80)[0] == 0
        assert load_config(root / "kcut.toml").project.name == "n" * 80

    def test_the_default_name_is_cleaned_and_cut_to_80(self, tmp_path: Path) -> None:
        folder = tmp_path / ("mi‮​ video " + "x" * 100)
        assert _new(folder)[0] == 0
        assert load_config(folder / "kcut.toml").project.name == ("mi video " + "x" * 100)[:80]
        front = (folder / "edit" / "estrategia.md").read_text(encoding="utf-8")
        assert "‮" not in front

    def test_a_default_name_with_nothing_left_is_proyecto(self, tmp_path: Path) -> None:
        folder = tmp_path / "​​"
        assert _new(folder)[0] == 0
        assert load_config(folder / "kcut.toml").project.name == "proyecto"

    def test_a_name_with_a_colon_and_quotes_is_fine(self, root: Path) -> None:
        assert _new(root, "--name", 'Rojo: "el" video')[0] == 0
        assert load_config(root / "kcut.toml").project.name == 'Rojo: "el" video'


class TestNeverOverwrites:
    def test_new_keeps_existing_files_untouched(self, root: Path) -> None:
        (root / "edit").mkdir(parents=True)
        (root / "recursos").mkdir()
        strategy = "---\nvideo: Mio\naprobado: si\naprobado_por: Yedin\n---\n# Ya aprobada\n"
        keep = {
            root / "edit" / "estrategia.md": strategy,
            root / "edit" / "versiones.md": "# Versiones - Mio\n\n## v1\nnotas de Claude\n",
            root / "recursos" / "recursos.json": '{"schema": "kcut.recursos/1", "items": []}\n',
        }
        for path, text in keep.items():
            path.write_bytes(text.encode("utf-8"))
        before = {path: path.read_bytes() for path in keep}
        stamps = {path: path.stat().st_mtime_ns for path in keep}

        code, doc = _new(root)

        assert code == 0
        for path in keep:
            assert path.read_bytes() == before[path]
            assert path.stat().st_mtime_ns == stamps[path]
        created = doc["created"]
        assert isinstance(created, list)
        for name in ("edit/estrategia.md", "edit/versiones.md", "recursos/recursos.json"):
            assert name not in created
        for name in ("edit/", "recursos/"):
            assert name not in created
        assert {"kcut.toml", "crudo/", "salida/", "qa/", ".kcut/"} <= set(created)
        assert (root / "kcut.toml").is_file()

    def test_new_crudo_is_file_creates_nothing(self, root: Path) -> None:
        root.mkdir()
        (root / "crudo").write_text("soy un archivo", encoding="utf-8")
        code, doc = _new(root)
        assert code == 3
        assert doc["ok"] is False
        assert sorted(p.name for p in root.iterdir()) == ["crudo"]
        assert (root / "crudo").read_text(encoding="utf-8") == "soy un archivo"


class TestExistingFolderRules:
    """`kcut new` on a folder that already exists (001.6)."""

    @pytest.fixture
    def elsewhere(self, tmp_path: Path) -> Path:
        folder = tmp_path / "otro disco"
        folder.mkdir()
        for i in range(5):
            (folder / f"ajeno{i}.mov").write_bytes(b"x")
        return folder

    @pytest.mark.parametrize("linked", [".kcut", "edit", "salida"])
    def test_existing_folder_rejects_internal_links_before_writing(
        self, root: Path, linked: str
    ) -> None:
        (root / "crudo").mkdir(parents=True)
        (root / "crudo" / "a.mov").write_bytes(b"footage")
        if linked == "edit":
            (root / "edit").mkdir()  # replaced by the link below
            shutil.rmtree(root / "edit")
        make_dir_link(root / linked, root / "crudo")  # a link that stays inside the project
        before = snapshot(root / "crudo")

        code, doc = _new(root)

        assert code == 3
        assert "enlace" in str(doc["error"])
        assert snapshot(root / "crudo") == before
        assert not (root / "kcut.toml").exists()

    def test_existing_folder_rejects_a_link_that_leaves_the_folder(
        self, root: Path, elsewhere: Path
    ) -> None:
        root.mkdir()
        make_dir_link(root / "qa", elsewhere)
        code, _ = _new(root)
        assert code == 3
        assert not (root / "kcut.toml").exists()
        assert sorted(p.name for p in elsewhere.iterdir()) == [f"ajeno{i}.mov" for i in range(5)]

    def test_existing_folder_prunes_links_when_it_counts_loose_files(
        self, root: Path, elsewhere: Path
    ) -> None:
        root.mkdir()
        (root / "suelto1.mov").write_bytes(b"1")
        (root / "suelto2.mov").write_bytes(b"2")
        make_dir_link(root / "atajo", elsewhere)  # not a layout folder: 5 files behind it
        result = run_kcut("new", str(root), "--json")
        assert result.returncode == 0, result.stderr
        assert "hay 2 archivos fuera de crudo/" in result.stderr

    def test_existing_folder_warning_ignores_the_layout_files(self, root: Path) -> None:
        for rel in (
            "edit/estrategia.md",
            "edit/versiones.md",
            "edit/graphics.json",
            "recursos/recursos.json",
            "recursos/logos/logo.png",
            "salida/v1.mp4",
            "qa/v1/report.json",
            ".kcut/inventory.json",
            "crudo/a.mov",
        ):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(b"x")
        result = run_kcut("new", str(root), "--json")
        assert result.returncode == 0, result.stderr
        assert "fuera de crudo" not in result.stderr

    def test_existing_folder_warning_counts_only_what_is_really_loose(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (root / "edit").mkdir(parents=True)
        (root / "edit" / "estrategia.md").write_text("x", encoding="utf-8")
        (root / "notas").mkdir()
        (root / "notas" / "a.txt").write_text("a", encoding="utf-8")
        (root / "video.mov").write_bytes(b"v")
        assert cli.main(["new", str(root)]) == 0
        out = capsys.readouterr().out
        assert "[AVISO] hay 2 archivos fuera de crudo/; muévelos a crudo/" in out
        assert "estrategia.md" not in out.split("[AVISO]")[1]
