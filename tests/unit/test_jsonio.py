"""Atomic UTF-8 JSON and text files (spec 0.9)."""

import json
from pathlib import Path

import pytest

from kcut import jsonio, proc
from kcut.config.load import parse_config
from kcut.errors import ProjectError
from kcut.ingest import workfiles
from kcut.ingest.inventory import Inventory, Notice, load_inventory, save_inventory
from kcut.paths import Layout
from kcut.proc import RunResult
from kcut.project import Project
from kcut.text.corrections import load_corrections
from kcut.transcribe import cache
from tests.unit.transcribe_fakes import FakeClip, build_project, tone


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


def test_surrogate_text_is_written_with_a_replacement_instead_of_crashing(tmp_path: Path) -> None:
    """`save_inventory` / `write_json_atomic` never raise UnicodeEncodeError (001.7)."""
    jsonio.write_json_atomic(tmp_path / "a.json", {"file": "crudo/clip\ud800.mov"})
    assert jsonio.read_json(tmp_path / "a.json") == {"file": "crudo/clip?.mov"}
    assert not (tmp_path / "a.json.tmp").exists()


class TestSizeCap:
    """001.12 point 13: `read_json` does not parse a file over the cap (64 MiB by default)."""

    def test_size_cap_a_file_over_the_cap_is_not_parsed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "big.json"
        path.write_text('{"a": "' + "x" * 100 + '"}', encoding="utf-8")

        def never(*_a: object, **_k: object) -> None:
            raise AssertionError("a file over the cap must not reach the JSON parser")

        monkeypatch.setattr("json.loads", never)
        with pytest.raises(ProjectError, match="pesa más de"):
            jsonio.read_json(path, max_bytes=50)

    def test_size_cap_a_file_exactly_at_the_cap_is_read(self, tmp_path: Path) -> None:
        path = tmp_path / "ok.json"
        path.write_text('{"a": 1}', encoding="utf-8")
        assert jsonio.read_json(path, max_bytes=8) == {"a": 1}
        with pytest.raises(ProjectError):
            jsonio.read_json(path, max_bytes=7)

    def test_size_cap_the_default_is_64_mib(self, tmp_path: Path) -> None:
        assert jsonio.MAX_JSON_BYTES == 64 * 1024 * 1024
        path = tmp_path / "huge.json"
        with path.open("wb") as handle:
            handle.truncate(jsonio.MAX_JSON_BYTES + 1)
        with pytest.raises(ProjectError, match="64 MB"):
            jsonio.read_json(path)

    def test_size_cap_it_is_the_same_error_as_a_corrupt_file(self, tmp_path: Path) -> None:
        path = tmp_path / "x.json"
        path.write_text("{" + " " * 100, encoding="utf-8")
        with pytest.raises(ProjectError) as corrupt:
            jsonio.read_json(path)
        with pytest.raises(ProjectError) as capped:
            jsonio.read_json(path, max_bytes=10)
        assert type(corrupt.value) is type(capped.value) is ProjectError
        assert capped.value.exit_code == corrupt.value.exit_code == 3

    def test_size_cap_the_message_names_the_file(self, tmp_path: Path) -> None:
        path = tmp_path / "grande ñ.json"
        path.write_text("[" + "0," * 50 + "0]", encoding="utf-8")
        with pytest.raises(ProjectError, match=r"grande ñ\.json"):
            jsonio.read_json(path, max_bytes=20)

    def test_size_cap_a_bad_utf8_file_under_the_cap_is_still_a_project_error(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "bad.json"
        path.write_bytes(b'{"a": "\xff"}')
        with pytest.raises(ProjectError):
            jsonio.read_json(path)

    def test_size_cap_the_inventory_loader_treats_it_as_corrupt(self, tmp_path: Path) -> None:
        from kcut.ingest.inventory import load_inventory

        path = tmp_path / ".kcut" / "inventory.json"
        path.parent.mkdir()
        with path.open("wb") as handle:
            handle.truncate(jsonio.MAX_JSON_BYTES + 1)
        with pytest.raises(ProjectError):
            load_inventory(path, tmp_path)


class TestPerFileCaps:
    """001.14 point 11: each file has its own cap, so one hostile file cannot cost 64 MiB."""

    MIB = 1024 * 1024

    def test_per_file_caps_the_table(self) -> None:
        assert (jsonio.MAX_INDEX_BYTES, jsonio.MAX_CORRECTIONS_BYTES) == (
            1 * self.MIB,
            8 * self.MIB,
        )
        assert (jsonio.MAX_INVENTORY_BYTES, jsonio.MAX_JSON_BYTES) == (16 * self.MIB, 64 * self.MIB)

    def _sparse(self, path: Path, size: int) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            handle.truncate(size)
        return path

    def test_per_file_caps_index(self, tmp_path: Path) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))])
        index = project.layout.transcripts / "index.json"
        for size, capped in ((self.MIB, False), (self.MIB + 1, True)):
            self._sparse(index, size)
            notices: list[Notice] = []
            assert cache.read_index(project, notices) == {}
            assert bool(notices) is True  # zeros are not JSON: invalid either way...
            assert ("más de" in jsonio_error(index, jsonio.MAX_INDEX_BYTES)) is capped

    def test_per_file_caps_corrections(self, tmp_path: Path) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))])
        self._sparse(project.layout.edit / "correcciones.json", 8 * self.MIB + 1)
        with pytest.raises(ProjectError, match="pesa más de 8 MB"):
            load_corrections(project)

    def test_per_file_caps_inventory(self, tmp_path: Path) -> None:
        path = self._sparse(tmp_path / ".kcut" / "inventory.json", 16 * self.MIB + 1)
        with pytest.raises(ProjectError, match="pesa más de 16 MB"):
            load_inventory(path, tmp_path)

    def test_per_file_caps_transcript(self, tmp_path: Path) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))])
        key = "c" * 64
        self._sparse(cache.transcript_path(project, key), 64 * self.MIB + 1)
        notices: list[Notice] = []
        assert cache.load_matching(project, "a1", key, "d" * 64, {}, notices, 1000) is None
        assert [n.code for n in notices] == ["transcript_invalid"]

    def test_per_file_caps_a_file_at_the_cap_is_not_refused_for_its_size(
        self, tmp_path: Path
    ) -> None:
        path = self._sparse(tmp_path / "x.json", jsonio.MAX_INDEX_BYTES)
        with pytest.raises(ProjectError) as info:
            jsonio.read_json(path, jsonio.MAX_INDEX_BYTES)
        assert "pesa más de" not in info.value.message_es  # it is not JSON, but not "too big"


def jsonio_error(path: Path, cap: int) -> str:
    try:
        jsonio.read_json(path, cap)
    except ProjectError as exc:
        return exc.message_es
    return ""
