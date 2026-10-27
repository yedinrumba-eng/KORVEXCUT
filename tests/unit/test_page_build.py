"""The HTML page of the graphics (spec S1.6a row 3, S1.7 row 7): the data cannot close the script
tag, the fonts go inside, nothing is read from the network and the scripts are in order."""

import base64
import json
import re
from typing import Any

import pytest

from kcut.errors import InternalError
from kcut.gfx.components import COMPONENTS
from kcut.gfx.components_base import LABEL, TITLE, ComponentDef
from kcut.gfx.page import FONTS, WEB, build_page, json_for_script, web_text

DATA: dict[str, Any] = {
    "fps": 30,
    "w": 1080,
    "h": 1920,
    "frames": 345,
    "brand": {"accent": "#E5FF1F", "accent2": "#2FA8FF", "dark": "#0B0B0E", "light": "#FFFFFF"},
    "images": {},
    "cues": [
        {"id": "a", "component": "label", "start_f": 0, "end_f": 30, "params": {"text": "hola"}}
    ],
}
SCRIPT_DATA = re.compile(r'<script type="application/json" id="kc-data">(.*?)</script>', re.DOTALL)


def _data_of(page: str) -> Any:
    found = SCRIPT_DATA.search(page)
    assert found is not None
    return json.loads(found.group(1))


def _with_text(text: str) -> dict[str, Any]:
    data = json.loads(json.dumps(DATA))
    data["cues"][0]["params"]["text"] = text
    return data


@pytest.mark.parametrize(
    "text",
    [
        "</script><script>alert(1)</script>",
        "a </SCRIPT> b",
        "<!-- <script>",
        "</",
        "<\\/script>",
        "ñ   </",
    ],
)
def test_page_build_a_script_tag_in_a_text_stays_escaped_and_the_data_reads_back(text: str) -> None:
    page = build_page(_with_text(text), ["label"])
    block = SCRIPT_DATA.search(page)
    assert block is not None and "</" not in block.group(1) and "<!--" not in block.group(1)
    assert _data_of(page)["cues"][0]["params"]["text"] == text


def test_page_build_the_closing_script_text_is_written_with_a_backslash() -> None:
    page = build_page(_with_text("</script>"), ["label"])
    assert "<\\/script>" in page
    assert json_for_script({"t": "</x>"}) == '{"t":"<\\/x>"}'


def test_page_build_every_script_tag_is_closed_once_and_only_ours() -> None:
    page = build_page(_with_text("</script>boom"), ["label", "title", "captions"])
    opened = len(re.findall(r"<script[ >]", page))
    assert opened == page.count("</script>") == 1 + 1 + 3  # data, runtime, three components


def test_page_build_the_three_fonts_go_inside_as_woff2_data_uris() -> None:
    page = build_page(DATA, ["label"])
    for weight in (600, 800, 900):
        assert f"font-weight:{weight}" in page
        raw = (FONTS / f"inter-latin-{weight}-normal.woff2").read_bytes()
        assert base64.b64encode(raw).decode("ascii") in page
        assert raw[:4] == b"wOF2"
    assert page.count("@font-face") == 3 and page.count("data:font/woff2;base64,") == 3


def test_page_build_nothing_is_read_from_the_network() -> None:
    page = build_page(DATA, ["label", "title", "kinetic", "endcard", "captions"])
    assert "://" not in page and "<link" not in page and "<img" not in page


def test_page_build_the_body_is_w_by_h_and_transparent() -> None:
    page = build_page(DATA, ["label"])
    assert "html,body{width:1080px;height:1920px}" in page
    assert re.search(r"html, body \{[^}]*background: transparent", page)
    assert "<!doctype html>" in page and '<meta charset="utf-8">' in page


def test_page_build_the_runtime_comes_first_and_then_each_component_once_in_order() -> None:
    page = build_page(DATA, ["title", "label", "title"])
    runtime, title, label = (
        page.index(web_text(n))
        for n in ("runtime.js", "components/title.js", "components/label.js")
    )
    assert runtime < title < label
    assert page.count(web_text("components/title.js")) == 1


def test_page_build_the_js_files_of_a_component_go_in_its_own_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    two = ComponentDef(
        "two", ("label.js", "title.js"), False, (), "Dos", "", "", "bajo", "", "test"
    )
    swapped = ComponentDef(
        "swapped", ("title.js", "label.js"), False, (), "Tres", "", "", "bajo", "", "test"
    )
    monkeypatch.setitem(COMPONENTS, "two", two)
    monkeypatch.setitem(COMPONENTS, "swapped", swapped)
    label, title = web_text("components/label.js"), web_text("components/title.js")
    page = build_page(DATA, ["two"])
    assert page.index(label) < page.index(title)
    page = build_page(DATA, ["swapped"])
    assert page.index(title) < page.index(label)


def test_page_build_the_internal_captions_component_can_be_in_the_page() -> None:
    assert web_text("components/captions.js") in build_page(DATA, ["captions"])


def test_page_build_an_unknown_component_is_an_internal_error() -> None:
    with pytest.raises(InternalError):
        build_page(DATA, ["nope"])


def test_page_build_data_without_a_size_is_an_internal_error() -> None:
    with pytest.raises(InternalError):
        build_page({"fps": 30}, [])


def test_page_build_nan_in_the_data_is_refused() -> None:
    with pytest.raises(ValueError):
        build_page({**DATA, "frames": float("nan")}, [])


def test_page_build_every_file_it_reads_exists_and_the_registry_points_at_real_scripts() -> None:
    for component in (*COMPONENTS.values(), TITLE, LABEL):
        for name in component.js_files:
            assert (WEB / "components" / name).is_file()
    assert (WEB / "runtime.js").is_file() and (WEB / "base.css").is_file()
