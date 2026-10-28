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
    # 001.34, point 1: the other ways to leave a task for after the `seek` (the photo has no limit
    # of its own, so the rules are what keeps a deferred task from blocking the page)
    "requestIdleCallback": r"\brequestIdleCallback\b",
    "MessageChannel": r"\bMessageChannel\b",
    "postMessage": r"\bpostMessage\b",
    "Worker": r"\bWorker\b",
    "fetch(": r"\bfetch\s*\(",
    "XMLHttpRequest": r"\bXMLHttpRequest\b",
    "innerHTML": r"\binnerHTML\b",
    "outerHTML": r"\bouterHTML\b",
    "insertAdjacentHTML": r"\binsertAdjacentHTML\b",
    "eval(": r"\beval\s*\(",
    # 001.35, point 2: the tasks that were still left to run after the `seek`. `Observer` has no
    # `\b` in front on purpose: it catches ResizeObserver, IntersectionObserver, MutationObserver
    # and PerformanceObserver, whose callbacks run during the photo with no limit
    "Observer": r"Observer\b",
    "queueMicrotask": r"\bqueueMicrotask\b",
    "requestVideoFrameCallback": r"\brequestVideoFrameCallback\b",
    ".animate(": r"\.\s*animate\s*\(",
    "SharedWorker": r"\bSharedWorker\b",
    "ServiceWorker": r"\b[Ss]erviceWorker\b",
    "BroadcastChannel": r"\bBroadcastChannel\b",
    "scheduler.": r"\bscheduler\s*\.",
    # 001.36, point 6: the APIs of animation that bring a clock of their own. Bracket access with
    # built names (`window["set" + "Timeout"]`) is accepted: this is a lint over the JS of kcut,
    # not a defence against someone else's JS (the CSP without `'unsafe-eval'` stops `eval`)
    "KeyframeEffect": r"\bKeyframeEffect\b",
    "document.timeline": r"\bdocument\s*\.\s*timeline\b",
    "new Animation": r"\bnew\s+Animation\b",
    "getAnimations": r"\bgetAnimations\b",
}
# 001.35, point 2: and in the components (`gfx/web/components/*.js`, not `runtime.js`, which loads
# images and fonts at start-up) nothing is left for later: no promise and no event callback
FORBIDDEN_COMPONENT_JS = {
    "Promise": r"\bPromise\b",
    "async": r"\basync\b",
    "await": r"\bawait\b",
    ".then(": r"\.\s*then\s*\(",
    "addEventListener": r"\baddEventListener\b",
    ".on<event> =": r"\.\s*on[a-z]+\s*=(?!=)",
}
# 001.36, point 6: no distinction of capitals, so `el.style.Animation` is caught too. 001.37, point
# 7: and no word boundary either (`\b`), so `animationName`, `transitionProperty` and
# `webkitAnimation` are caught: they are the JS names of the same CSS properties
FORBIDDEN_CSS = {"transition": r"(?i)transition", "animation": r"(?i)animation"}  # 001.37
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
    if path.suffix == ".js" and path.parent.name == "components":  # 001.35
        rules = rules | FORBIDDEN_COMPONENT_JS
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
        "requestIdleCallback": "requestIdleCallback(() => spin())",  # 001.34
        "MessageChannel": "const ch = new MessageChannel();",  # 001.34
        "postMessage": "window.postMessage('x', '*')",  # 001.34
        "Worker": "const w = new Worker('w.js');",  # 001.34
        "fetch(": "fetch ('x')",
        "XMLHttpRequest": "new XMLHttpRequest()",
        "innerHTML": "el.innerHTML = x",
        "outerHTML": "el.outerHTML = x",
        "insertAdjacentHTML": "el.insertAdjacentHTML('beforeend', x)",
        "eval(": "eval('1')",
        "Observer": "new ResizeObserver(() => spin()).observe(el);",  # 001.35
        "queueMicrotask": "queueMicrotask(() => spin());",  # 001.35
        "requestVideoFrameCallback": "video.requestVideoFrameCallback(tick);",  # 001.35
        ".animate(": "el.animate([{opacity: 0}, {opacity: 1}], 100);",  # 001.35
        "SharedWorker": "const w = new SharedWorker('w.js');",  # 001.35
        "ServiceWorker": "navigator.serviceWorker.register(); const s = ServiceWorker;",  # 001.35
        "BroadcastChannel": "const c = new BroadcastChannel('x');",  # 001.35
        "scheduler.": "scheduler.postTask(() => spin());",  # 001.35
        "KeyframeEffect": "const k = new KeyframeEffect(el, [], 100);",  # 001.36
        "document.timeline": "const t = document . timeline.currentTime;",  # 001.36
        "new Animation": "const a = new Animation(effect);",  # 001.36
        "getAnimations": "el.getAnimations().forEach(f);",  # 001.36
    }
    assert samples.keys() == FORBIDDEN_JS.keys()
    for name, code in samples.items():
        assert re.search(FORBIDDEN_JS[name], code), name
    assert re.search(FORBIDDEN_CSS["transition"], ".a{transition:all 1s}")
    assert re.search(FORBIDDEN_CSS["animation"], ".a{animation:spin 1s}")
    # 001.36, point 6: the two patterns do not tell capitals from small letters
    assert re.search(FORBIDDEN_CSS["animation"], "el.style.Animation = 'spin 1s';")
    assert re.search(FORBIDDEN_CSS["transition"], "el.style.Transition = 'all 1s';")
    # 001.37, point 7: the two patterns have no word boundary, so the JS names of the properties
    # and the prefixed ones are caught too
    assert re.search(FORBIDDEN_CSS["animation"], "el.style.animationName = 'spin';")
    assert re.search(FORBIDDEN_CSS["transition"], "el.style.transitionProperty = 'all';")
    assert re.search(FORBIDDEN_CSS["animation"], "el.style.webkitAnimation = 'spin 1s';")
    assert not re.search(FORBIDDEN_JS["Date"], "const update = 1; // the updated state")
    # 001.34: the new names are whole words, and a name that only contains one is not caught
    assert not re.search(FORBIDDEN_JS["Worker"], "const coworker = 1; const workerCount = 2;")
    assert not re.search(FORBIDDEN_JS["postMessage"], "const postMessages = 1;")
    assert not re.search(FORBIDDEN_JS["MessageChannel"], "const MessageChannels = 1;")
    assert not re.search(FORBIDDEN_JS["requestIdleCallback"], "const requestIdleCallbacks = 1;")


@pytest.mark.parametrize(
    "code",
    [  # 001.35: the four observers that `Observer` has to catch
        "new ResizeObserver(f)",
        "new IntersectionObserver(f)",
        "new MutationObserver(f)",
        "new PerformanceObserver(f)",
    ],
)
def test_gfx_js_rules_observer_catches_the_four_observers(code: str) -> None:
    assert re.search(FORBIDDEN_JS["Observer"], code)


def test_gfx_js_rules_the_new_names_are_whole_words() -> None:
    # 001.35: a name that only contains one of them is not caught
    assert not re.search(FORBIDDEN_JS["queueMicrotask"], "const queueMicrotasks = 1;")
    assert not re.search(FORBIDDEN_JS[".animate("], "const animated = 1; el.animation = 2;")
    assert not re.search(FORBIDDEN_JS["scheduler."], "const schedulers = 1;")
    assert not re.search(FORBIDDEN_JS["Observer"], "const observer = 1; const Observers = 2;")
    assert not re.search(FORBIDDEN_JS["BroadcastChannel"], "const BroadcastChannels = 1;")
    assert not re.search(FORBIDDEN_JS["SharedWorker"], "const SharedWorkers = 1;")
    # 001.36, point 6: the four APIs of animation are whole names too
    assert not re.search(FORBIDDEN_JS["KeyframeEffect"], "const KeyframeEffects = 1;")
    assert not re.search(FORBIDDEN_JS["document.timeline"], "const mydocument = document.title;")
    assert not re.search(FORBIDDEN_JS["new Animation"], "const a = new AnimationFrameLike();")
    assert not re.search(FORBIDDEN_JS["getAnimations"], "const getAnimationsCount = 1;")


def test_gfx_js_rules_the_component_rules_catch_what_a_component_may_not_leave_for_later() -> None:
    samples = {  # 001.35: one example of each
        "Promise": "const p = Promise.resolve(1);",
        "async": "const f = async () => 1;",
        "await": "const v = await f();",
        ".then(": "load().then(draw);",
        "addEventListener": "el.addEventListener('load', draw);",
        ".on<event> =": "img.onload = draw;",
    }
    assert samples.keys() == FORBIDDEN_COMPONENT_JS.keys()
    for name, code in samples.items():
        assert re.search(FORBIDDEN_COMPONENT_JS[name], code), name
    assert re.search(FORBIDDEN_COMPONENT_JS[".on<event> ="], "el.onerror=fail;")
    assert not re.search(FORBIDDEN_COMPONENT_JS[".on<event> ="], "if (a.once == 1) { b.one === 2 }")
    assert not re.search(FORBIDDEN_COMPONENT_JS["async"], "const asyncCount = 1;")


def test_gfx_js_rules_runtime_is_outside_the_component_rules() -> None:
    """`runtime.js` loads images and fonts at start-up, so it keeps its promises and its `load`
    listener: the component rules apply to the files of `components/` only (001.35)."""
    runtime = (WEB / "runtime.js").read_text(encoding="utf-8")
    assert any(re.search(pattern, runtime) for pattern in FORBIDDEN_COMPONENT_JS.values())
    components = [p for p in _files() if p.suffix == ".js" and p.parent.name == "components"]
    assert components and all(p.name != "runtime.js" for p in components)
