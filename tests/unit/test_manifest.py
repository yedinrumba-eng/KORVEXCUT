"""recursos/recursos.json: schema rules, validation messages and the approval gate (DS9)."""

from pathlib import Path
from typing import Any

import pytest

from kcut.config.load import parse_config
from kcut.errors import GateError, ProjectError
from kcut.jsonio import write_json_atomic
from kcut.paths import Layout
from kcut.project import Project
from kcut.recursos.manifest import load_manifest, require_approved, validate_manifest


def _item(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "file": "recursos/logos/claude-mascota.webp",
        "kind": "imagen",
        "origin": "descargado",
        "source_url": "https://ejemplo.com/kit-de-marca",
        "license": "kit oficial de marca",
        "license_url": None,
        "obtained": "2026-10-15",
        "approved_by": "Yedin",
        "approved_on": "2026-10-15",
        "notes": "mascota 3D, fondo quitado",
    }
    base.update(changes)
    return base


@pytest.fixture
def project(tmp_path: Path) -> Project:
    root = tmp_path / "proyecto ñandú"
    (root / "recursos" / "logos").mkdir(parents=True)
    (root / "recursos" / "logos" / "claude-mascota.webp").write_bytes(b"webp")
    layout = Layout(root)
    write_json_atomic(layout.manifest, {"schema": "kcut.recursos/1", "items": [_item()]})
    return Project(root=root, config=parse_config("", default_name="x"), layout=layout)


def _save(project: Project, *items: dict[str, Any]) -> None:
    write_json_atomic(project.layout.manifest, {"schema": "kcut.recursos/1", "items": list(items)})


class TestLoad:
    def test_the_example_of_the_spec(self, project: Project) -> None:
        (item,) = load_manifest(project)
        assert item.file == "recursos/logos/claude-mascota.webp"
        assert (item.kind, item.origin) == ("imagen", "descargado")
        assert item.source_url == "https://ejemplo.com/kit-de-marca"
        assert item.license == "kit oficial de marca"
        assert item.license_url is None
        assert (item.obtained, item.approved_by, item.approved_on) == (
            "2026-10-15",
            "Yedin",
            "2026-10-15",
        )
        assert item.notes == "mascota 3D, fondo quitado"

    def test_missing_manifest_means_no_resources(self, project: Project) -> None:
        project.layout.manifest.unlink()
        assert load_manifest(project) == []

    def test_empty_items(self, project: Project) -> None:
        _save(project)
        assert load_manifest(project) == []

    @pytest.mark.parametrize(
        ("changes", "fragment"),
        [
            ({"file": "logos/x.webp"}, "recursos/"),
            ({"file": "../recursos/x.webp"}, "sale del proyecto"),
            ({"file": "C:/recursos/x.webp"}, "unidad"),
            ({"kind": "pelicula"}, "kind"),
            ({"origin": "robado"}, "origin"),
            ({"origin": "descargado", "source_url": ""}, "source_url"),
            ({"origin": "descargado", "source_url": None}, "source_url"),
            ({"license": ""}, "license"),
            ({"obtained": "15/10/2026"}, "obtained"),
            ({"obtained": "2026-10-15\n"}, "obtained"),
            ({"obtained": "2026-02-30"}, "obtained"),
            ({"approved_on": "ayer"}, "approved_on"),
            ({"approved_by": 5}, "approved_by"),
            ({"extra": 1}, "extra"),
        ],
    )
    def test_invalid_item_is_a_project_error_naming_the_field(
        self, project: Project, changes: dict[str, Any], fragment: str
    ) -> None:
        _save(project, _item(**changes))
        with pytest.raises(ProjectError, match=fragment) as info:
            load_manifest(project)
        assert info.value.exit_code == 3

    @pytest.mark.parametrize("kind", ["imagen", "musica", "sfx", "video", "fuente", "otro"])
    def test_every_kind_is_valid(self, project: Project, kind: str) -> None:
        _save(project, _item(kind=kind))
        assert load_manifest(project)[0].kind == kind

    @pytest.mark.parametrize("origin", ["propio", "generado", "cliente"])
    def test_source_url_is_optional_unless_downloaded(self, project: Project, origin: str) -> None:
        _save(project, _item(origin=origin, source_url=None))
        assert load_manifest(project)[0].source_url is None

    def test_wrong_schema_marker(self, project: Project) -> None:
        write_json_atomic(project.layout.manifest, {"schema": "otro/9", "items": []})
        with pytest.raises(ProjectError, match="schema"):
            load_manifest(project)

    def test_malformed_json_reports_line_and_column(self, project: Project) -> None:
        project.layout.manifest.write_text(
            '{"schema": \n  "kcut.recursos/1", items}', encoding="utf-8"
        )
        with pytest.raises(ProjectError, match=r"línea \d+, columna \d+"):
            load_manifest(project)


class TestValidate:
    def test_clean_manifest_has_no_errors(self, project: Project) -> None:
        assert validate_manifest(project) == []

    def test_a_missing_file_is_reported(self, project: Project) -> None:
        (project.root / "recursos" / "logos" / "claude-mascota.webp").unlink()
        errors = validate_manifest(project)
        assert len(errors) == 1
        assert "claude-mascota.webp" in errors[0]
        assert "no existe" in errors[0]

    def test_every_problem_is_listed_not_just_the_first(self, project: Project) -> None:
        _save(
            project,
            _item(license=""),
            _item(file="recursos/logos/b.webp", kind="pelicula"),
            _item(file="recursos/otro.webp"),
        )
        errors = validate_manifest(project)
        assert any("license" in e for e in errors)
        assert any("kind" in e for e in errors)
        assert any("otro.webp" in e and "no existe" in e for e in errors)

    def test_duplicate_files_are_reported(self, project: Project) -> None:
        _save(project, _item(), _item())
        assert any("repetido" in e for e in validate_manifest(project))

    def test_unapproved_is_not_an_error_just_unusable(self, project: Project) -> None:
        _save(project, _item(approved_by=""))
        assert validate_manifest(project) == []

    def test_malformed_file_is_one_error_not_an_exception(self, project: Project) -> None:
        project.layout.manifest.write_text("{", encoding="utf-8")
        errors = validate_manifest(project)
        assert len(errors) == 1


class TestRequireApproved:
    def test_approved_resource_is_returned(self, project: Project) -> None:
        item = require_approved(project, "recursos/logos/claude-mascota.webp")
        assert item.approved_by == "Yedin"

    def test_equivalent_spellings_of_the_path_match(self, project: Project) -> None:
        assert (
            require_approved(project, "recursos/./logos//claude-mascota.webp").approved_by
            == "Yedin"
        )

    def test_not_in_the_manifest_is_a_gate_error(self, project: Project) -> None:
        with pytest.raises(GateError, match="manifiesto") as info:
            require_approved(project, "recursos/logos/otro.webp")
        assert info.value.exit_code == 5

    def test_empty_approved_by_is_a_gate_error(self, project: Project) -> None:
        _save(project, _item(approved_by=""))
        with pytest.raises(GateError, match="aprob") as info:
            require_approved(project, "recursos/logos/claude-mascota.webp")
        assert info.value.exit_code == 5

    def test_blank_approved_by_is_also_unapproved(self, project: Project) -> None:
        _save(project, _item(approved_by="   "))
        with pytest.raises(GateError):
            require_approved(project, "recursos/logos/claude-mascota.webp")

    def test_a_path_that_escapes_is_a_project_error(self, project: Project) -> None:
        with pytest.raises(ProjectError):
            require_approved(project, "../fuera.png")

    def test_missing_manifest_means_nothing_is_approved(self, project: Project) -> None:
        project.layout.manifest.unlink()
        with pytest.raises(GateError):
            require_approved(project, "recursos/logos/claude-mascota.webp")

    def test_approved_but_deleted_from_disk(self, project: Project) -> None:
        (project.root / "recursos" / "logos" / "claude-mascota.webp").unlink()
        with pytest.raises(ProjectError, match="no existe"):
            require_approved(project, "recursos/logos/claude-mascota.webp")
