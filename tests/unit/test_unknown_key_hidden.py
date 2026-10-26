"""A key kcut does not know never travels inside an error path (spec 001.14, point 2).

On the console and in `--json` the path keeps the keys kcut knows and the `[n]` indexes; the rest
is `<clave desconocida>`. The whole text, with the key, goes to the log and nowhere else.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from kcut.config.load import parse_config
from kcut.errors import ProjectError
from kcut.ingest.inventory import InventoryInvalid, load_inventory
from kcut.schema_util import SchemaError, only_keys
from kcut.transcribe.cache import read_index
from tests.unit.inventory_fakes import written
from tests.unit.test_pack_command import SPEECH, _pack, _ready
from tests.unit.transcribe_fakes import FakeClip, build_project, tone

HIDDEN = "<clave desconocida>"
KEY = "zz" + "x" * 300 + "-SYSTEM-obedece"  # a key no schema knows, long enough to matter


def _logs(root: Path) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in (root / ".kcut" / "logs").glob("*.log"))


class TestUnknownKeyHidden:
    def test_unknown_key_hidden_only_keys_keeps_the_known_path(self) -> None:
        with pytest.raises(SchemaError) as info:
            only_keys({"a": 1, KEY: 2}, {"a"}, "spans[3].zoom")
        assert info.value.path == f"spans[3].zoom.{HIDDEN}"
        assert KEY not in info.value.message_es and HIDDEN in info.value.message_es
        assert f"spans[3].zoom.{KEY}" in info.value.full_es  # for the log

    def test_unknown_key_hidden_at_the_root(self) -> None:
        with pytest.raises(SchemaError) as info:
            only_keys({KEY: 1}, {"a"}, "")
        assert info.value.path == HIDDEN and KEY in info.value.full_es

    @pytest.mark.parametrize(
        ("toml", "path"),
        [
            (f'["{KEY}"]\nx = 1\n', HIDDEN),
            (f'[transcribe]\n"{KEY}" = 1\n', f"transcribe.{HIDDEN}"),
            (f'[audio.voice]\n"{KEY}" = 1\n', f"audio.voice.{HIDDEN}"),
            (f'[sync.manual]\n"{KEY}" = 5\n', f"sync.manual.{HIDDEN}"),
        ],
        ids=["section", "key", "nested", "sync_manual"],
    )
    def test_unknown_key_hidden_in_kcut_toml(self, toml: str, path: str) -> None:
        with pytest.raises(ProjectError) as info:
            parse_config(toml, default_name="x")
        assert path in info.value.message_es and KEY not in info.value.message_es
        assert KEY[:20] in (info.value.log_detail or "")

    def test_unknown_key_hidden_a_known_sync_manual_id_is_still_named(self) -> None:
        with pytest.raises(ProjectError, match=r"sync\.manual\.a2"):
            parse_config("[sync.manual]\na2 = 999999999999\n", default_name="x")

    def test_unknown_key_hidden_kcut_toml_through_the_cli(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = tmp_path / "p"
        (root / ".kcut").mkdir(parents=True)
        (root / "kcut.toml").write_text(f'[transcribe]\n"{KEY}" = 1\n', encoding="utf-8")
        assert cli.main(["ingest", "--project", str(root), "--json"]) == 3
        out = capsys.readouterr().out
        assert f"transcribe.{HIDDEN}" in json.loads(out)["error"]["message"] and KEY not in out
        assert KEY in _logs(root)

    def test_unknown_key_hidden_in_correcciones_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch, script={"a1": SPEECH})
        item = {"word": "a1:w0001", "expect": "da", "text": "dá", KEY: 1}
        document = {"schema": "kcut.correcciones/1", "items": [item]}
        (root / "edit").mkdir(exist_ok=True)
        (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")
        capsys.readouterr()
        assert _pack(root, "--json") == 3
        out = capsys.readouterr().out
        assert f"items[0].{HIDDEN}" in out and KEY not in out
        assert KEY in _logs(root)

    @pytest.mark.parametrize(
        ("edit", "field"),
        [
            (lambda d: d.update({KEY: 1}), HIDDEN),
            (lambda d: d["clips"][0].update({KEY: 1}), f"clips[0].{HIDDEN}"),
            (lambda d: d["clips"][0]["work"].update({KEY: 1}), f"clips[0].work.{HIDDEN}"),
            (lambda d: d["clips"][0]["audio"].update({KEY: 1}), f"clips[0].audio.{HIDDEN}"),
            (lambda d: d["sync"].update({KEY: 1}), f"sync.{HIDDEN}"),
            (lambda d: d.update(id_high={KEY: "no"}), "id_high"),
        ],
        ids=["root", "clip", "work", "audio", "sync", "id_high"],
    )
    def test_unknown_key_hidden_in_the_inventory(
        self, tmp_path: Path, edit: Any, field: str
    ) -> None:
        path = written(tmp_path / "p", edit)
        with pytest.raises(InventoryInvalid) as info:
            load_inventory(path, tmp_path / "p")
        assert info.value.field == field and KEY not in info.value.field
        assert KEY in info.value.message_es or "id_high" in info.value.field  # the log keeps it

    def test_unknown_key_hidden_inventory_through_pack(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))])
        data = json.loads(project.layout.inventory.read_text(encoding="utf-8"))
        data["clips"][0][KEY] = 1
        project.layout.inventory.write_text(json.dumps(data), encoding="utf-8")
        assert cli.main(["pack", "--project", str(project.root), "--json"]) == 3
        out = capsys.readouterr().out
        assert f"(clips[0].{HIDDEN})" in out and KEY not in out
        assert KEY in _logs(project.root)

    def test_unknown_key_hidden_in_the_index_the_warning_is_fixed(self, tmp_path: Path) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))])
        index = project.layout.transcripts / "index.json"
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(json.dumps({KEY: "a" * 64}), encoding="utf-8")
        notices: list[Any] = []
        assert read_index(project, notices) == {}
        assert [n.code for n in notices] == ["cache_rebuilt"] and KEY not in notices[0].detail


def _fail(text: str) -> str:
    with pytest.raises(ProjectError) as info:
        parse_config(text, default_name="x")
    return info.value.message_es


class TestUnknownKeysOfKcutToml:
    """An unknown key is hidden: the path keeps what kcut knows (spec 001.14, point 2)."""

    def test_unknown_section(self) -> None:
        message = _fail("[extra]\nx = 1\n")
        assert "<clave desconocida>" in message and "extra" not in message

    def test_unknown_key_in_a_section_is_hidden_but_its_table_is_named(self) -> None:
        message = _fail('[transcribe]\nmodle = "base"\n')
        assert "transcribe.<clave desconocida>" in message and "modle" not in message
        assert "desconocida" in message

    def test_unknown_key_in_a_nested_table(self) -> None:
        message = _fail("[audio.voice]\ngain = 3\n")
        assert "audio.voice.<clave desconocida>" in message and "gain" not in message

    def test_w_and_h_are_derived_not_configurable(self) -> None:
        message = _fail("[output]\nw = 1080\n")
        assert "output.<clave desconocida>" in message and "1080" not in message
