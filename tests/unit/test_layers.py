"""The layers of the package (spec S1.6b round 1, 001.31 point 12; row 30): a module that is not a
command does not import a command, and nobody imports a private name of another module's command.

`commands/` is the top: `cli.py` and `__main__.py` import it, and nothing else does. The code that
two commands share (`build_folder`, `refuse_edl`, `proxy_of`, `fx_context`, `MAX_SHOWN`) lives in a
neutral module that both import. The test reads the imports with `ast`, so it sees an import inside
a function too.
"""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "kcut"
TOP = {"cli.py", "__main__.py"}  # the only files outside `commands/` that import it
Found = list[tuple[str, int, str]]


def _imports(source: str, name: str) -> list[tuple[int, str, list[str]]]:
    """`(line, module, names)` of each import in `source`: `import a.b` is `(n, "a.b", [])` and
    `from a.b import c, d` is `(n, "a.b", ["c", "d"])`; `from . import x` has the module `.`."""
    found: list[tuple[int, str, list[str]]] = []
    for node in ast.walk(ast.parse(source, filename=name)):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name, []) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            found.append((node.lineno, module, [alias.name for alias in node.names]))
    return found


def _reaches_commands(module: str, names: list[str]) -> bool:
    """Does the import reach `kcut.commands` (`kcut.commands.x`, `from kcut import commands`)?"""
    if module == "kcut.commands" or module.startswith("kcut.commands."):
        return True
    return module == "kcut" and "commands" in names


def _upward(source: str, name: str) -> list[tuple[int, str]]:
    """The imports of a module that is not a command that reach a command: `(line, module)`."""
    return [
        (line, module)
        for line, module, names in _imports(source, name)
        if _reaches_commands(module, names)
    ]


def _private(source: str, name: str) -> list[tuple[int, str]]:
    """`from kcut.commands.<x> import _<name>`: `(line, "module._name")`."""
    return [
        (line, f"{module}.{imported}")
        for line, module, names in _imports(source, name)
        if module.startswith("kcut.commands.")
        for imported in names
        if imported.startswith("_")
    ]


def _files() -> list[Path]:
    found = sorted(SRC.rglob("*.py"))
    assert len(found) > 100  # the folder was found: this is not a test of an empty list
    return found


def _outside_commands() -> list[Path]:
    return [
        p
        for p in _files()
        if "commands" not in p.relative_to(SRC).parts[:-1]
        and p.relative_to(SRC).as_posix() not in TOP
    ]


def test_layers_nothing_outside_commands_imports_a_command() -> None:
    found: Found = []
    for path in _outside_commands():
        found += [
            (path.relative_to(SRC).as_posix(), line, module)
            for line, module in _upward(path.read_text(encoding="utf-8"), path.name)
        ]
    assert found == [], "estos módulos importan kcut.commands: " + str(found)


def test_layers_cli_and_main_are_the_ones_that_do_import_the_commands() -> None:
    """The exception is a real one, so the rule above is looking at something."""
    cli = (SRC / "cli.py").read_text(encoding="utf-8")
    assert '"kcut.commands.render"' in cli  # it loads them by name, with `importlib`


def test_layers_no_file_imports_a_private_name_of_a_command_module() -> None:
    found: Found = []
    for path in _files():
        found += [
            (path.relative_to(SRC).as_posix(), line, name)
            for line, name in _private(path.read_text(encoding="utf-8"), path.name)
        ]
    assert found == [], "estos archivos importan un nombre privado de un comando: " + str(found)


@pytest.mark.parametrize(
    ("line", "upward", "private"),
    [
        ("from kcut.commands.view import proxy_of", 1, 0),
        ("from kcut.commands.render import _build_folder, _refuse", 1, 2),
        ("import kcut.commands.render", 1, 0),
        ("from kcut import commands", 1, 0),
        ("from kcut.commands import view", 1, 0),
        ("def f():\n    from kcut.commands.pack import _energy", 1, 1),
        ("from kcut.render.proxy_file import proxy_of", 0, 0),
        ("from kcut.ingest.cache_guard import build_folder", 0, 0),
        ("from kcut import issues", 0, 0),
        ("# from kcut.commands.view import proxy_of", 0, 0),
    ],
)
def test_layers_the_scan_finds_what_it_is_made_to_find(
    line: str, upward: int, private: int
) -> None:
    """A contrast test: the rules above run on a planted line and see it (or do not)."""
    assert len(_upward(line, "x.py")) == upward
    assert len(_private(line, "x.py")) == private


def test_layers_the_shared_code_lives_in_neutral_modules() -> None:
    from kcut import issues
    from kcut.commands import edl, listing, mix, refuse, render, view
    from kcut.ingest import cache_guard
    from kcut.render import compose, frame_fx, preview, proxy_file

    assert callable(cache_guard.build_folder) and callable(cache_guard.assert_own_folder)
    assert callable(refuse.refuse_edl) and refuse.refuse_edl.__module__ == "kcut.commands.refuse"
    assert proxy_file.proxy_of.__module__ == "kcut.render.proxy_file"
    assert proxy_file.Proxy == tuple[Path, tuple[int, int]]
    assert view.proxy_of is proxy_file.proxy_of and preview.proxy_of is proxy_file.proxy_of
    assert frame_fx.fx_context.__module__ == "kcut.render.frame_fx"
    assert "fx_context" in vars(compose) and compose.fx_context is frame_fx.fx_context
    assert issues.MAX_SHOWN == 50
    # 001.37, point 13: `graphics check` and `mix` list through `commands/listing.py` and no longer
    # have a `MAX_SHOWN` of their own; the one `listing` cuts with is still the one of `issues`
    # (was `graphics.MAX_SHOWN is issues.MAX_SHOWN`)
    assert edl.MAX_SHOWN is issues.MAX_SHOWN and listing.MAX_SHOWN is issues.MAX_SHOWN  # 001.37
    assert not hasattr(mix, "MAX_SHOWN")  # 001.37: it does not keep a second name either
    assert not hasattr(render, "_build_folder") and not hasattr(render, "_refuse")
    assert not hasattr(preview, "fx_context")  # it moved: preview does not keep a second name


def test_layers_max_shown_of_the_checks_is_defined_once() -> None:
    """`kcut/issues.py` has it; `text/corrections.py` has another, which is a length of text."""
    where = sorted(
        path.relative_to(SRC).as_posix()
        for path in _files()
        if re.search(r"^MAX_SHOWN\s*=", path.read_text(encoding="utf-8"), re.MULTILINE)
    )
    assert where == ["issues.py", "text/corrections.py"]
