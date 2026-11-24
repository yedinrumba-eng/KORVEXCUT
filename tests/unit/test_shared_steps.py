"""What `render`, `mix` and `build` do the same lives in one place (spec 001.51 point 6, row 31).

Each command used to carry its own copy of the steps (`_picture`, `_plan`, `_graphics`, `_looks`,
`_read_optional`, the mux...), and the copies drifted apart without any test tying them. The scan
reads the five modules with `ast` and finds no two functions with the same body (the `ast.dump` of
the statements, without the docstring).
"""

import ast
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "kcut"
FILES = (
    "commands/render.py",
    "commands/mix.py",
    "pipeline/build.py",
    "pipeline/picture.py",
    "pipeline/audio.py",
)


def _body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """The `ast.dump` of the body of a function, without its docstring."""
    statements = list(node.body)
    first = statements[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        statements = statements[1:]
    return "\n".join(ast.dump(statement) for statement in statements)


def _functions() -> dict[str, list[str]]:
    """`{body: ["file:name", ...]}` of every function and method of the five files."""
    found: dict[str, list[str]] = defaultdict(list)
    for rel in FILES:
        tree = ast.parse((SRC / rel).read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                found[_body(node)].append(f"{rel}:{node.name}")
    return found


def test_shared_steps_no_two_functions_of_the_five_modules_have_the_same_body() -> None:
    repeated = [names for body, names in _functions().items() if body and len(names) > 1]
    assert repeated == [], repeated


def test_shared_steps_the_scan_does_see_a_copy_when_there_is_one() -> None:
    """Control: two functions with the same statements and different docstrings are one body."""
    one = ast.parse('def a(x):\n    """one"""\n    return x + 1\n').body[0]
    two = ast.parse('def b(x):\n    """two"""\n    return x + 1\n').body[0]
    assert isinstance(one, ast.FunctionDef) and isinstance(two, ast.FunctionDef)
    assert _body(one) == _body(two)


def test_shared_steps_the_commands_import_the_steps_and_do_not_define_them() -> None:
    defined = {
        rel: {n.name for n in ast.walk(ast.parse((SRC / rel).read_text(encoding="utf-8")))
              if isinstance(n, ast.FunctionDef)}
        for rel in FILES
    }  # fmt: skip
    for rel in ("commands/render.py", "commands/mix.py"):
        assert not {"_picture", "_plan", "_graphics", "_looks", "_read_optional"} & defined[rel]
    assert {"make_picture", "make_video", "resolve_graphics", "looks", "mux_replace"} <= defined[
        "pipeline/picture.py"
    ]
    assert {"read_plan", "make_mix"} <= defined["pipeline/audio.py"]
