"""Every function of the tests that makes a folder with `tmp_path_factory.mktemp` deletes it with
`remove_tree` (spec S1.9b step 0, row 17; 001.47 point 10): a fixture of a wide scope, or a test.
The scan is of the syntax tree, so a new fixture that forgets it is a failure here.
"""

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]


def _calls(node: ast.AST, name: str) -> bool:
    """True if `node` has a call to `name(...)` or `<anything>.name(...)`."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            target = child.func
            if (isinstance(target, ast.Attribute) and target.attr == name) or (
                isinstance(target, ast.Name) and target.id == name
            ):
                return True
    return False


def test_tmp_cleanup_users_every_function_that_makes_a_folder_deletes_it() -> None:
    makers: list[str] = []
    forgetful: list[str] = []
    for path in sorted(TESTS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and _calls(node, "mktemp"):
                where = f"{path.relative_to(TESTS).as_posix()}::{node.name}"
                makers.append(where)
                if not _calls(node, "remove_tree"):
                    forgetful.append(where)
    assert len(makers) >= 15, makers  # control: the scan does find the fixtures
    assert forgetful == []
