"""A poisoned `.kcut/` must never make kcut touch `crudo/` or anything outside `.kcut/`.

The attacks: an inventory with a hostile id, a `wav16` that points at a raw file (so an old
"reuse the previous wav" step would *move* the user's footage), and `.kcut` replaced by a
junction to another folder.
"""

import json
import shutil
from pathlib import Path

import pytest

from kcut import cli
from kcut.errors import ProjectError
from kcut.ingest import workfiles
from kcut.ingest.naming import qhash
from kcut.project import open_project
from tests.conftest import run_kcut
from tests.fixtures.links import make_dir_link
from tests.fixtures.synth_media import MediaTruth
from tests.integration.ingest_helpers import ingest, inventory, snapshot

Synth = tuple[Path, MediaTruth]


@pytest.fixture
def camera(tmp_path: Path, synth_project: Synth) -> Path:
    """A project holding one real camera clip, already ingested without proxies."""
    root = tmp_path / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    shutil.copy2(synth_project[0] / "crudo" / "cam a.mp4", root / "crudo" / "cam a.mp4")
    assert ingest(root)[0] == 0
    return root


def _poison(root: Path, change: object) -> None:
    path = root / ".kcut" / "inventory.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert callable(change)
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def _tree_outside_cache(root: Path) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if ".kcut" not in p.relative_to(root).parts
    )


def _codes(doc: dict[str, object]) -> list[str]:
    warnings = doc["warnings"]
    assert isinstance(warnings, list)
    return [w["code"] for w in warnings]


@pytest.mark.ffmpeg
class TestPoisonedInventory:
    @pytest.mark.slow
    def test_a_hostile_id_discards_the_inventory_and_touches_nothing_else(
        self, camera: Path, tmp_path: Path
    ) -> None:
        canary = tmp_path / "x"
        canary.mkdir()
        (canary / "canary.txt").write_text("viva", encoding="utf-8")
        before, outside = snapshot(camera / "crudo"), snapshot(tmp_path / "x")
        tree = _tree_outside_cache(camera)

        _poison(camera, lambda d: d["clips"][0].update(id="../../x"))
        code, doc = ingest(camera)

        assert code == 0
        assert "inventory_invalid" in _codes(doc)
        assert snapshot(camera / "crudo") == before
        assert snapshot(tmp_path / "x") == outside
        assert _tree_outside_cache(camera) == tree
        assert [c.id for c in inventory(camera).clips] == ["a1"]  # rebuilt from scratch

    @pytest.mark.slow
    def test_a_wav16_pointing_at_the_raw_file_never_moves_it(self, camera: Path) -> None:
        raw = camera / "crudo" / "cam a.mp4"
        digest = qhash(raw)
        # the attacker plants a matching sidecar next to the footage, so "is it fresh?" says yes
        (camera / "crudo" / "cam a.mp4.json").write_text(
            json.dumps({"qhash": digest, "params": workfiles.wav_params(16000)}), encoding="utf-8"
        )
        before = snapshot(camera / "crudo")

        _poison(camera, lambda d: d["clips"][0]["work"].update(wav16="crudo/cam a.mp4"))
        code, doc = ingest(camera)

        assert code == 0
        assert "inventory_invalid" in _codes(doc)
        assert raw.is_file()
        assert snapshot(camera / "crudo") == before

    @pytest.mark.slow
    @pytest.mark.parametrize(
        "change",
        [
            lambda d: d["clips"][0].update(file="../../x.mov"),
            lambda d: d["clips"][0].update(file="edit/estrategia.md"),
            lambda d: d["clips"][0].update(slug="../x"),
            lambda d: d["clips"][0]["work"].update(wav16="../../x.wav"),
            lambda d: d["clips"][0]["work"].update(proxy="crudo/cam a.mp4"),
            lambda d: d.update(id_high={"zz": 4}),
        ],
    )
    def test_every_kind_of_poison_is_dropped(self, camera: Path, change: object) -> None:
        before = snapshot(camera / "crudo")
        _poison(camera, change)
        code, doc = ingest(camera)
        assert code == 0
        assert "inventory_invalid" in _codes(doc)
        assert snapshot(camera / "crudo") == before

    @pytest.mark.slow
    def test_a_clean_run_leaves_crudo_identical_in_content_and_mtime(self, camera: Path) -> None:
        before = snapshot(camera / "crudo")
        assert ingest(camera)[0] == 0
        assert ingest(camera, "--resync")[0] == 0
        assert snapshot(camera / "crudo") == before
        assert sorted(p.name for p in (camera / "crudo").iterdir()) == ["cam a.mp4"]


class TestLayoutOutsideTheProject:
    @pytest.fixture
    def elsewhere(self, tmp_path: Path) -> Path:
        folder = tmp_path / "otra carpeta"
        folder.mkdir()
        return folder

    @pytest.mark.parametrize("folder", [".kcut", "crudo", "edit", "salida", "qa", "recursos"])
    def test_a_layout_folder_that_leaves_the_root_rejects_the_project(
        self, tmp_path: Path, elsewhere: Path, folder: str
    ) -> None:
        root = tmp_path / "proyecto ñandú"
        assert run_kcut("new", str(root)).returncode == 0
        shutil.rmtree(root / folder)
        make_dir_link(root / folder, elsewhere)
        with pytest.raises(ProjectError, match=r"enlace|fuera del proyecto") as info:
            open_project(str(root))
        assert info.value.exit_code == 3
        assert list(elsewhere.iterdir()) == []

    @pytest.mark.slow
    def test_a_cache_subfolder_that_leaves_the_root_rejects_the_project(
        self, tmp_path: Path, elsewhere: Path
    ) -> None:
        root = tmp_path / "proyecto ñandú"
        assert run_kcut("new", str(root)).returncode == 0
        make_dir_link(root / ".kcut" / "wav16", elsewhere)
        with pytest.raises(ProjectError, match=r"enlace|fuera del proyecto"):
            open_project(str(root))

    @pytest.mark.slow
    def test_kcut_junction_to_another_folder_writes_nothing_there(
        self, tmp_path: Path, elsewhere: Path, synth_project: Synth
    ) -> None:
        root = tmp_path / "proyecto ñandú"
        assert run_kcut("new", str(root)).returncode == 0
        shutil.copy2(synth_project[0] / "crudo" / "cam a.mp4", root / "crudo" / "cam a.mp4")
        shutil.rmtree(root / ".kcut")
        make_dir_link(root / ".kcut", elsewhere)
        before = snapshot(root / "crudo")

        result = run_kcut("ingest", "--project", str(root), "--json")

        assert result.returncode == 3
        assert json.loads(result.stdout)["error"]["kind"] == "ProjectError"
        assert list(elsewhere.iterdir()) == []
        assert snapshot(root / "crudo") == before

    @pytest.mark.slow
    def test_an_internal_error_does_not_write_its_log_through_the_link(
        self, tmp_path: Path, elsewhere: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kcut.commands import doctor

        root = tmp_path / "proyecto ñandú"
        assert run_kcut("new", str(root)).returncode == 0
        shutil.rmtree(root / ".kcut")
        make_dir_link(root / ".kcut", elsewhere)

        def boom(_args: object) -> int:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(doctor, "run", boom)
        assert cli.main(["doctor", "--project", str(root)]) == 10
        assert list(elsewhere.iterdir()) == []


class TestInternalLinks:
    """A link that stays *inside* the project is just as dangerous: `.kcut -> crudo/` would
    make every cache write land in the user's footage."""

    @pytest.fixture
    def project(self, tmp_path: Path, synth_project: Synth) -> Path:
        root = tmp_path / "proyecto ñandú"
        assert run_kcut("new", str(root)).returncode == 0
        shutil.copy2(synth_project[0] / "crudo" / "cam a.mp4", root / "crudo" / "cam a.mp4")
        (root / "edit" / "estrategia.md").write_text("---\naprobado: si\n---\n", encoding="utf-8")
        return root

    def _guarded(self, root: Path) -> dict[str, dict[str, tuple[str, int]]]:
        return {name: snapshot(root / name) for name in ("crudo", "edit", "recursos")}

    @pytest.mark.slow
    @pytest.mark.parametrize("target", ["crudo", "edit"])
    def test_internal_link_from_kcut_to_a_project_folder_rejects_the_project(
        self, project: Path, target: str
    ) -> None:
        shutil.rmtree(project / ".kcut")
        make_dir_link(project / ".kcut", project / target)
        before = self._guarded(project)

        with pytest.raises(ProjectError, match="enlace") as info:
            open_project(str(project))
        assert info.value.exit_code == 3
        result = run_kcut("ingest", "--project", str(project), "--json")

        assert result.returncode == 3
        assert json.loads(result.stdout)["error"]["kind"] == "ProjectError"
        assert self._guarded(project) == before
        assert sorted(p.name for p in (project / "crudo").iterdir()) == ["cam a.mp4"]

    @pytest.mark.slow
    def test_internal_link_from_the_logs_folder_to_crudo_rejects_the_project(
        self, project: Path
    ) -> None:
        make_dir_link(project / ".kcut" / "logs", project / "crudo")
        before = self._guarded(project)

        with pytest.raises(ProjectError, match="enlace"):
            open_project(str(project))
        for command in (["ingest", "--json"], ["doctor", "--json"]):
            run_kcut(*command, "--project", str(project))

        assert self._guarded(project) == before
        assert sorted(p.name for p in (project / "crudo").iterdir()) == ["cam a.mp4"]

    @pytest.mark.slow
    def test_internal_link_from_a_cache_subfolder_to_edit_rejects_the_project(
        self, project: Path
    ) -> None:
        make_dir_link(project / ".kcut" / "wav16", project / "edit")
        before = self._guarded(project)
        with pytest.raises(ProjectError, match="enlace"):
            open_project(str(project))
        assert run_kcut("ingest", "--project", str(project), "--json").returncode == 3
        assert self._guarded(project) == before

    @pytest.mark.slow
    def test_internal_link_in_a_layout_folder_is_found_by_new_too(self, project: Path) -> None:
        (project / "kcut.toml").unlink()  # a folder that is not yet a project
        shutil.rmtree(project / ".kcut")
        make_dir_link(project / ".kcut", project / "crudo")
        before = self._guarded(project)
        result = run_kcut("new", str(project), "--json")
        assert result.returncode == 3
        assert "enlace" in json.loads(result.stdout)["error"]["message"]
        assert self._guarded(project) == before
        assert not (project / "kcut.toml").exists()

    @pytest.mark.slow
    def test_a_real_folder_is_still_accepted(self, project: Path) -> None:
        assert open_project(str(project)).root == project.resolve()


class TestLayoutFolderIsAFile:
    """A file where the layout expects a folder is named, not a bare NotADirectoryError (001.7)."""

    def test_layout_folder_is_file_ingest_exits_3_and_keeps_the_inventory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = tmp_path / "proyecto ñandú"
        assert cli.main(["new", str(root)]) == 0
        (root / "crudo" / "nota.txt").write_text("texto", encoding="utf-8")
        args = ["ingest", "--project", str(root), "--json", "--no-proxy"]
        assert cli.main(args) == 0  # a note needs no ffprobe: the inventory exists
        saved = root / ".kcut" / "inventory.json"
        before = saved.read_bytes()
        shutil.rmtree(root / ".kcut" / "logs", ignore_errors=True)
        (root / ".kcut" / "logs").write_text("soy un archivo", encoding="utf-8")
        capsys.readouterr()

        assert cli.main(args) == 3

        message = json.loads(capsys.readouterr().out)["error"]["message"]
        assert "hay un archivo donde kcut espera una carpeta: .kcut/logs" in message
        assert saved.read_bytes() == before
