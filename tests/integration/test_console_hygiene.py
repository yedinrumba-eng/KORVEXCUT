"""`kcut ingest` never prints untrusted text raw: keys and ids of `inventory.json`, file names of
`crudo/` (spec 001.8, point 1). Human mode and `--json`, stdout and stderr."""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kcut import cli

Edit = Callable[[dict[str, Any]], object]

_FLAGS = pytest.mark.parametrize("flags", [[], ["--json"]], ids=["human", "json"])
_INVENTORY_CASES = [
    pytest.param(
        lambda d: d.update({"\x1b]0;X\x07\x1b[2J": 1}),
        "\\x1b]0;X\\x07\\x1b[2J: clave desconocida",
        id="key",
    ),
    pytest.param(
        lambda d: d["clips"][0].update(id="d1\x1b[2J"),
        "clips[d1\\x1b[2J].id",
        id="clip_id",
    ),
]


def _forbidden_in(text: str) -> list[str]:
    """The characters of `text` that must never reach a terminal (spec 001.8, criterion 55)."""
    return [c for c in text if c in "\x1b\x07\x7f\u202e" or "\x80" <= c <= "\x9f"]


def _strings(value: object) -> list[str]:
    """Every string (keys and values) of a decoded JSON document."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (*_strings(k), *_strings(v))]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    root = tmp_path / "proyecto ñandú"
    assert cli.main(["new", str(root)]) == 0
    (root / "crudo" / "nota.txt").write_text("hola", encoding="utf-8")
    return root


@pytest.fixture
def ingested(project_dir: Path) -> Path:
    assert cli.main(["ingest", "--project", str(project_dir), "--no-proxy"]) == 0
    return project_dir


@_FLAGS
@pytest.mark.parametrize(("edit", "escaped"), _INVENTORY_CASES)
def test_console_hygiene_inventory_text_is_escaped(
    ingested: Path,
    capsys: pytest.CaptureFixture[str],
    flags: list[str],
    edit: Edit,
    escaped: str,
) -> None:
    saved = ingested / ".kcut" / "inventory.json"
    data = json.loads(saved.read_text(encoding="utf-8"))
    edit(data)
    saved.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()

    assert cli.main(["ingest", "--project", str(ingested), "--no-proxy", *flags]) == 0

    captured = capsys.readouterr()
    assert not _forbidden_in(captured.out + captured.err)
    assert "inventory_invalid" in captured.err and escaped in captured.err
    if flags:
        assert escaped in " ".join(_strings(json.loads(captured.out)))


@_FLAGS
def test_console_hygiene_file_names_are_escaped(
    project_dir: Path, capsys: pytest.CaptureFixture[str], flags: list[str]
) -> None:
    crudo = project_dir / "crudo"
    (crudo / "n\u009b\x7f\u202eota.txt").write_text("hola", encoding="utf-8")
    try:
        (crudo / "a\u009b\x7f\u202eb\ud800.txt").write_text("hola", encoding="utf-8")
    except (OSError, UnicodeEncodeError) as exc:
        pytest.skip(f"este sistema no admite un nombre con surrogate suelto: {exc}")
    capsys.readouterr()

    assert cli.main(["ingest", "--project", str(project_dir), "--no-proxy", *flags]) == 0

    captured = capsys.readouterr()
    assert not _forbidden_in(captured.out + captured.err)
    assert "crudo/a\\x9b\\x7f\\u202eb?.txt: el nombre de este archivo" in captured.err
    if flags:
        texts = _strings(json.loads(captured.out))
        assert "crudo/a\\x9b\\x7f\\u202eb?.txt" in texts
    else:
        assert re.search(r"\[OK\] d\d: doc - crudo/n\\x9b\\x7f\\u202eota\.txt\n", captured.out)
