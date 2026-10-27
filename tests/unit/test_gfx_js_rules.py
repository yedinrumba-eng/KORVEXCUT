"""The rules every script and style of `gfx/web/` follows (spec S1.6a row 3): the picture is a
function of the time, so nothing in them may read a clock, ask for chance, wait, fetch or build HTML
from text. Checked with regular expressions over every file of the folder and over the `js_files`
of every component, in the order the page includes them."""

import re
from pathlib import Path

import pytest

from kcut.gfx.components import COMPONENTS, page_component
from kcut.gfx.page import WEB

FORBIDDEN_JS = {
    "Date": r"\bDate\b",
    "performance.now": r"\bperformance\s*\.\s*now\b",
    "Math.random": r"\bMath\s*\.\s*random\b",
    "requestAnimationFrame": r"\brequestAnimationFrame\b",
    "setTimeout": r"\bsetTimeout\b",
    "setInterval": r"\bsetInterval\b",
    "fetch(": r"\bfetch\s*\(",
    "XMLHttpRequest": r"\bXMLHttpRequest\b",
    "innerHTML": r"\binnerHTML\b",
    "outerHTML": r"\bouterHTML\b",
    "insertAdjacentHTML": r"\binsertAdjacentHTML\b",
    "eval(": r"\beval\s*\(",
}
FORBIDDEN_CSS = {"transition": r"\btransition\b", "animation": r"\banimation\b"}
# Text goes in with `textContent`: `innerText` and `document.write` are forbidden too (001.29)
TEXT_RULE = r"\binnerText\b|\bdocument\s*\.\s*write"


def _registered_files() -> list[Path]:
    """The scripts of the components as the page includes them: the `js_files` of each one."""
    found: list[Path] = []
    for component_id in [*COMPONENTS, "captions"]:
        component = page_component(component_id)
        assert component is not None
        found += [WEB / "components" / name for name in component.js_files]
    return found


def _files() -> list[Path]:
    return sorted(p for p in WEB.rglob("*") if p.suffix in (".js", ".css"))


def test_gfx_js_rules_the_web_folder_has_what_the_spec_lists() -> None:
    names = {p.relative_to(WEB).as_posix() for p in _files()}
    assert {"runtime.js", "base.css"} <= names
    assert {
        f"components/{n}.js" for n in ("captions", "title", "label", "kinetic", "endcard")
    } <= names


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.relative_to(WEB).as_posix())
def test_gfx_js_rules_no_file_uses_a_forbidden_api(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    rules = FORBIDDEN_JS if path.suffix == ".js" else {}
    found = [name for name, pattern in rules.items() if re.search(pattern, text)]
    # `transition` and `animation` are forbidden in CSS, and the CSS of a component lives in its JS
    found += [name for name, pattern in FORBIDDEN_CSS.items() if re.search(pattern, text)]
    assert found == [], f"{path.name} usa {found}"


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.relative_to(WEB).as_posix())
def test_gfx_js_rules_a_file_cannot_close_the_script_tag_that_holds_it(path: Path) -> None:
    text = path.read_text(encoding="utf-8").lower()
    assert "</script" not in text and "<!--" not in text


def test_gfx_js_rules_every_js_file_of_every_component_is_checked_and_exists() -> None:
    files = _registered_files()
    assert files, "no hay componentes registrados"
    assert all(path.is_file() for path in files)
    on_disk = {p for p in _files() if p.parent.name == "components"}
    assert set(files) == on_disk  # every script of the folder belongs to a component, and back


def test_gfx_js_rules_the_js_files_of_a_component_are_a_tuple_of_names_in_components() -> None:
    for component_id in [*COMPONENTS, "captions"]:
        component = page_component(component_id)
        assert component is not None and isinstance(component.js_files, tuple)
        assert all(re.fullmatch(r"[a-z_]+\.js", name) for name in component.js_files)


def _breaks_the_text_rule(path: Path) -> bool:
    return re.search(TEXT_RULE, path.read_text(encoding="utf-8")) is not None


def test_gfx_js_rules_text_goes_in_with_text_content_only() -> None:
    for path in _files():
        # 001.29: the rule had 0x08 where `\b` goes and never found anything; now it does
        assert not _breaks_the_text_rule(path), path.name


# 001.29: this rule had the control character 0x08 where `\b` goes (a heredoc did it), so it never
# found anything and the test above passed without testing. The contrast tests show it finds.
def test_gfx_js_rules_the_text_rule_has_word_boundaries_and_no_control_characters() -> None:
    assert TEXT_RULE.count("\\b") == 3
    assert not any(ord(ch) < 32 for ch in TEXT_RULE)


@pytest.mark.parametrize(
    "code",
    ["el.innerText = x;", "document.write(x);", "document . write (x);", "document.writeln(x)"],
)
def test_gfx_js_rules_the_text_rule_finds_what_it_forbids_in_a_planted_file(
    tmp_path: Path, code: str
) -> None:
    planted = tmp_path / "planted.js"
    planted.write_text(f"function f(el, x) {{ {code} }}\n", encoding="utf-8")
    assert _breaks_the_text_rule(planted)


@pytest.mark.parametrize(
    "code", ["el.textContent = x;", "const innerTextual = 1;", "mydocument.write(x);"]
)
def test_gfx_js_rules_the_text_rule_leaves_alone_what_it_does_not_forbid(
    tmp_path: Path, code: str
) -> None:
    planted = tmp_path / "planted.js"
    planted.write_text(f"function f(el, x) {{ {code} }}\n", encoding="utf-8")
    assert not _breaks_the_text_rule(planted)


def test_gfx_js_rules_the_checker_itself_catches_each_forbidden_api() -> None:
    samples = {
        "Date": "const t = new Date();",
        "performance.now": "performance.now()",
        "Math.random": "Math.random() * 3",
        "requestAnimationFrame": "requestAnimationFrame(tick)",
        "setTimeout": "setTimeout(f, 10)",
        "setInterval": "setInterval(f, 10)",
        "fetch(": "fetch ('x')",
        "XMLHttpRequest": "new XMLHttpRequest()",
        "innerHTML": "el.innerHTML = x",
        "outerHTML": "el.outerHTML = x",
        "insertAdjacentHTML": "el.insertAdjacentHTML('beforeend', x)",
        "eval(": "eval('1')",
    }
    assert samples.keys() == FORBIDDEN_JS.keys()
    for name, code in samples.items():
        assert re.search(FORBIDDEN_JS[name], code), name
    assert re.search(FORBIDDEN_CSS["transition"], ".a{transition:all 1s}")
    assert re.search(FORBIDDEN_CSS["animation"], ".a{animation:spin 1s}")
    assert not re.search(FORBIDDEN_JS["Date"], "const update = 1; // the updated state")
