"""`params.shown`, the public name of the helper that says how a value goes into a message (spec
001.38, point 6; S1.9a row 16). It was `params._shown` and `audio/music_schema.py` imported it as a
private name; the body is the same: a text is only its length, anything else goes through
`describe_value`.
"""

import ast
from pathlib import Path

from kcut import params
from kcut.audio import music_schema
from kcut.schema_util import describe_value

SRC = Path(__file__).resolve().parents[2] / "src" / "kcut"


def test_params_shown_a_text_is_only_its_length() -> None:
    assert params.shown("Maria 809-555-1234") == "<texto, 18 car.>"
    assert params.shown("") == "<texto, 0 car.>"


def test_params_shown_anything_else_goes_through_describe_value() -> None:
    for value in (5, 2.5, True, None, [1, 2], {"a": 1}, 10**30):
        assert params.shown(value) == describe_value(value)


def test_params_shown_music_schema_uses_the_public_name() -> None:
    assert music_schema.shown is params.shown


def test_params_shown_the_private_name_of_params_is_gone() -> None:
    assert not hasattr(params, "_shown")
    assert not hasattr(music_schema, "_shown")


def test_params_shown_no_module_imports_it_as_private() -> None:
    """`from kcut.params import _shown` anywhere in `src/`: the import is read with `ast`."""
    found = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "kcut.params":
                found += [(path.name, alias.name) for alias in node.names if alias.name == "_shown"]
    assert found == []
