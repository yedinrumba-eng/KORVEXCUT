"""Atomic UTF-8 JSON and text files (spec 0.9)."""

import json
from pathlib import Path

import pytest

from kcut import jsonio, proc
from kcut.config.load import parse_config
from kcut.errors import ProjectError
from kcut.ingest import workfiles
from kcut.ingest.inventory import Inventory, save_inventory
from kcut.paths import Layout
from kcut.proc import RunResult
from kcut.project import Project


class TestJsonio:
    def test_format(self, tmp_path: Path) -> None:
        jsonio.write_json_atomic(tmp_path / "a.json", {"nombre": "ñandú", "n": [1, 2]})
        raw = (tmp_path / "a.json").read_bytes()
        assert raw.decode("utf-8") == '{\n "nombre": "ñandú",\n "n": [\n  1,\n  2\n ]\n}\n'

    def test_no_tmp_file_is_left(self, tmp_path: Path) -> None:
        jsonio.write_json_atomic(tmp_path / "a.json", {"a": 1})
        assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json"]

    def test_round_trip_and_parents(self, tmp_path: Path) -> None:
        jsonio.write_json_atomic(tmp_path / "x" / "a.json", {"a": [1, {"b": None}]})
        assert jsonio.read_json(tmp_path / "x" / "a.json") == {"a": [1, {"b": None}]}

    def test_nan_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            jsonio.write_json_atomic(tmp_path / "a.json", {"x": float("nan")})
        assert not (tmp_path / "a.json").exists()

    def test_malformed_json_reports_file_line_and_column(self, tmp_path: Path) -> None:
        path = tmp_path / "mal.json"
        path.write_text('{\n "a": 1,\n "b": }\n', encoding="utf-8")
        with pytest.raises(ProjectError) as info:
            jsonio.read_json(path)
        assert "mal.json" in info.value.message_es
        assert "línea 3, columna 7" in info.value.message_es
        assert info.value.exit_code == 3

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectError, match="no existe"):
            jsonio.read_json(tmp_path / "no.json")

    def test_invalid_utf8(self, tmp_path: Path) -> None:
        (tmp_path / "x.json").write_bytes(b'{"a": "\xff"}')
        with pytest.raises(ProjectError):
            jsonio.read_json(tmp_path / "x.json")

    def test_text_is_written_with_unix_newlines(self, tmp_path: Path) -> None:
        jsonio.write_text_atomic(tmp_path / "t.md", "a\nb\n")
        assert (tmp_path / "t.md").read_bytes() == b"a\nb\n"

    def test_a_locked_target_asks_to_close_the_player(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def locked(_src: object, _dst: object) -> None:
            raise PermissionError("en uso")

        monkeypatch.setattr(jsonio.os, "replace", locked)
        with pytest.raises(ProjectError, match=r"cierra el archivo .* en el reproductor y repite"):
            jsonio.write_text_atomic(tmp_path / "salida.txt", "x")
        assert not (tmp_path / "salida.txt.tmp").exists()

    def test_json_dump_matches_the_documented_call(self, tmp_path: Path) -> None:
        obj = {"a": "ñ", "b": [1, 2.5]}
        jsonio.write_json_atomic(tmp_path / "a.json", obj)
        expected = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
        assert (tmp_path / "a.json").read_text(encoding="utf-8") == expected


class TestHostileJson:
    def test_a_deeply_nested_document_is_a_project_error_not_a_crash(self, tmp_path: Path) -> None:
        (tmp_path / "hondo.json").write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
        with pytest.raises(ProjectError, match="anidado") as info:
            jsonio.read_json(tmp_path / "hondo.json")
        assert info.value.exit_code == 3

    def test_a_number_with_thousands_of_digits_is_a_project_error(self, tmp_path: Path) -> None:
        (tmp_path / "enorme.json").write_text('{"n": ' + "9" * 5000 + "}", encoding="utf-8")
        with pytest.raises(ProjectError) as info:
            jsonio.read_json(tmp_path / "enorme.json")
        assert info.value.exit_code == 3

    def test_both_cases_name_the_file(self, tmp_path: Path) -> None:
        (tmp_path / "x.json").write_text("[" * 100_000, encoding="utf-8")
        with pytest.raises(ProjectError, match=r"x\.json"):
            jsonio.read_json(tmp_path / "x.json")

    def test_a_stale_tmp_file_is_not_written_through(self, tmp_path: Path) -> None:
        victim = tmp_path / "victima.txt"
        victim.write_text("intacta", encoding="utf-8")
        tmp = tmp_path / "salida.json.tmp"
        try:
            tmp.symlink_to(victim)
        except OSError:
            tmp.write_text("viejo", encoding="utf-8")  # no symlink privilege: a plain stale file
        jsonio.write_json_atomic(tmp_path / "salida.json", {"a": 1})
        assert victim.read_text(encoding="utf-8") == "intacta"
        assert json.loads((tmp_path / "salida.json").read_text(encoding="utf-8")) == {"a": 1}
        assert not tmp.exists()


class TestDirectoryTarget:
    """A folder where a file is expected is not "close the player" (spec 0.10.5, 001.6)."""

    def test_directory_target_for_write_json(self, tmp_path: Path) -> None:
        (tmp_path / "salida.json").mkdir()
        (tmp_path / "salida.json" / "dentro.txt").write_text("x", encoding="utf-8")
        with pytest.raises(ProjectError) as info:
            jsonio.write_json_atomic(tmp_path / "salida.json", {"a": 1})
        assert "hay una carpeta donde kcut espera un archivo" in info.value.message_es
        assert "reproductor" not in info.value.message_es
        assert info.value.exit_code == 3
        assert (tmp_path / "salida.json" / "dentro.txt").read_text(encoding="utf-8") == "x"
        assert not (tmp_path / "salida.json.tmp").exists()

    def test_directory_target_for_write_text(self, tmp_path: Path) -> None:
        (tmp_path / "nota.md").mkdir()
        with pytest.raises(ProjectError, match="bórrala o muévela"):
            jsonio.write_text_atomic(tmp_path / "nota.md", "hola")

    def test_directory_target_where_the_inventory_goes(self, tmp_path: Path) -> None:
        (tmp_path / ".kcut" / "inventory.json").mkdir(parents=True)
        inv = Inventory("x", 30, ())
        with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo"):
            save_inventory(tmp_path / ".kcut" / "inventory.json", inv)

    def test_directory_target_where_a_sidecar_goes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = tmp_path / "proyecto ñandú"
        (root / ".kcut" / "wav16").mkdir(parents=True)
        (root / "crudo").mkdir()
        project = Project(root, parse_config("", default_name="x"), Layout(root))
        dst = project.layout.wav16 / "a1_x.wav"
        workfiles.sidecar_path(dst).mkdir()

        def fake_run(args: list[str], **_kwargs: object) -> RunResult:
            Path(args[-1]).write_bytes(b"wav")
            return RunResult(0, b"", "")

        job = ("sha256:" + "a" * 64, {}, 10.0)
        with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo"):
            monkeypatch.setattr(proc, "run", fake_run)
            workfiles._build(project, lambda out: ["x", str(out)], dst, job, None)

    def test_a_normal_overwrite_still_works(self, tmp_path: Path) -> None:
        jsonio.write_json_atomic(tmp_path / "a.json", {"a": 1})
        jsonio.write_json_atomic(tmp_path / "a.json", {"a": 2})
        assert jsonio.read_json(tmp_path / "a.json") == {"a": 2}
