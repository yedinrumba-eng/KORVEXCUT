"""`load_corrections`: the project's `edit/correcciones.json`, absent, good or malformed."""

from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.project import Project
from kcut.text.corrections import load_corrections


class TestLoad:
    def test_a_project_without_the_file_has_no_corrections(self, tmp_path: Path) -> None:
        project = _project(tmp_path)
        assert load_corrections(project) == {}

    def test_the_file_is_read_as_utf8(self, tmp_path: Path) -> None:
        project = _project(tmp_path)
        (tmp_path / "edit" / "correcciones.json").write_text(
            '{"schema": "kcut.correcciones/1", "items": '
            '[{"word": "a1:w0002", "expect": "ñandu", "text": "ñandú", "why": "acento"}]}',
            encoding="utf-8",
        )
        assert load_corrections(project)["a1:w0002"].text == "ñandú"

    def test_a_malformed_file_is_a_project_error_that_names_the_file(self, tmp_path: Path) -> None:
        project = _project(tmp_path)
        (tmp_path / "edit" / "correcciones.json").write_text('{"schema": ', encoding="utf-8")
        with pytest.raises(ProjectError, match=r"correcciones\.json"):
            load_corrections(project)

    def test_a_schema_error_names_the_file_and_the_path(self, tmp_path: Path) -> None:
        project = _project(tmp_path)
        (tmp_path / "edit" / "correcciones.json").write_text('{"schema": "x"}', encoding="utf-8")
        with pytest.raises(ProjectError, match=r"correcciones\.json: schema"):
            load_corrections(project)


def _project(root: Path) -> Project:
    from kcut.config.load import parse_config
    from kcut.paths import Layout

    (root / "edit").mkdir(parents=True, exist_ok=True)
    return Project(root=root, config=parse_config("", default_name="x"), layout=Layout(root))
