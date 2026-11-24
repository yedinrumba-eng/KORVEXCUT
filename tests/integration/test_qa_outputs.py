"""What `kcut qa` writes, and when (spec S1.9a rows 24, 25, 26 and 28; 001.41, points 4 to 6 and 8).

The run takes minutes (the ear), so each target is looked at again right before it is written; a
sheet that is not made takes the old one of an earlier run with it; a `graphics.json` that cannot
be read is a sheet that is skipped and not a run that falls after everything was measured; and the
report on disk has its texts through `safe_text`, as what is printed has.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kcut.qa import run as qa_run
from kcut.qa.contact_gfx import GRAPHICS_ES
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.integration.graphics_helpers import plant_words
from tests.integration.qa_contact_helpers import install_solid_layer, mask_pii_off
from tests.integration.qa_helpers import VIDEO, built, check_of, copy_of
from tests.integration.qa_pii_cases import SPEECH
from tests.integration.view_frames_helpers import Run, project_args, remove
from tests.unit.qa_fakes import install_ear

__all__ = ["built"]
pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
# Built with chr() so that no invisible character sits in this source: a bidi override, a zero
# width space, two characters of the "tag" zone and ESC.
BAD = [chr(0x202E), chr(0x200B), chr(0xE0041), chr(0xE007F), chr(0x1B)]
HOSTILE = "bogus" + "".join(BAD) + "[31m"
SHEET = ("qa", "v1", "contact.jpg")


def _swap_for_a_junction(root: Path, outside: Path) -> Callable[[], None]:
    """What a hook does: `qa/v1` becomes a link to `outside` (a folder of somebody else's)."""

    def swap() -> None:
        folder = root / "qa" / "v1"
        shutil.rmtree(folder, ignore_errors=True)
        folder.parent.mkdir(exist_ok=True)
        make_dir_link(folder, outside)

    return swap


def _outside(tmp_path: Path) -> Path:
    outside = tmp_path / "ajeno"
    outside.mkdir()
    return outside


def test_qa_write_guard_a_junction_put_in_qa_v1_during_the_ear_is_exit_3_and_nothing_goes_through(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    plant_words(root)
    outside = _outside(tmp_path)
    swap = _swap_for_a_junction(root, outside)
    fake = install_ear(monkeypatch, SPEECH)
    real = fake.transcribe

    def transcribe(self: Any, *args: Any, **kwargs: Any) -> Any:
        swap()  # the minutes of the ear: `qa/v1` is somebody else's now
        return real(self, *args, **kwargs)

    monkeypatch.setattr(fake, "transcribe", transcribe)
    install_solid_layer(monkeypatch)
    try:
        code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    finally:
        remove_dir_link(root / "qa" / "v1")
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    assert list(outside.iterdir()) == []  # not the sheet and not the report


def test_qa_write_guard_a_junction_put_in_qa_v1_after_the_sheet_stops_the_report(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    outside = _outside(tmp_path)
    swap = _swap_for_a_junction(root, outside)
    real = qa_run._warnings  # called after the sheet is written and before the report is

    def warnings(notices: Any) -> Any:
        swap()
        return real(notices)

    monkeypatch.setattr(qa_run, "_warnings", warnings)
    try:
        code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    finally:
        remove_dir_link(root / "qa" / "v1")
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    assert list(outside.iterdir()) == []


def _mask_pii_on(root: Path) -> None:
    path = root / "kcut.toml"
    text = path.read_text(encoding="utf-8")
    assert "mask_pii = false" in text
    path.write_text(text.replace("mask_pii = false", "mask_pii = true"), encoding="utf-8")


def test_qa_contact_stale_removed_the_sheet_of_an_earlier_run_goes_when_this_one_has_none(
    built: Path, tmp_path: Path, kcut_json: Run
) -> None:
    root = copy_of(built, tmp_path)
    mask_pii_off(root)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code in (0, 1) and doc["contact_sheet"] == "qa/v1/contact.jpg", (doc, err)
    assert root.joinpath(*SHEET).is_file()  # a sheet from the video, raw if it had text
    _mask_pii_on(root)
    remove(root, "a1", "proxy")  # no proxy, so no cell can be made
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code in (0, 1) and doc["contact_sheet"] is None, (doc, err)
    assert [w["code"] for w in doc["warnings"]] == ["contact_skipped"]
    assert not root.joinpath(*SHEET).exists()  # the old one is gone, not left next to `null`
    assert json.loads((root / "qa" / "v1" / "report.json").read_text(encoding="utf-8")) == doc


def test_qa_contact_graphics_unreadable_is_no_sheet_and_the_other_checks_come_out(
    built: Path, tmp_path: Path, kcut_json: Run
) -> None:
    root = copy_of(built, tmp_path)
    (root / "edit" / "graphics.json").write_text("{ 972 808 3211", encoding="utf-8")
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0 and doc["verdict"] == "incomplete", (doc, err)  # as without the file
    assert doc["contact_sheet"] is None and not root.joinpath(*SHEET).exists()
    assert [(w["code"], w["message_es"]) for w in doc["warnings"]] == [
        ("contact_skipped", GRAPHICS_ES)
    ]
    assert check_of(doc, "frames")["status"] == "pass"  # everything else was measured
    assert "972" not in json.dumps(doc) and "972" not in err
    assert "contact_skipped" in err


def test_qa_report_safe_text_the_report_on_disk_has_no_invisible_or_control_characters(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ear hears a word with a bidi mark, a zero-width space, characters of the "tag" zone and
    an ESC: it comes out in `diffs[].heard`. Printed it was escaped; on disk it was not."""
    root = copy_of(built, tmp_path)
    plant_words(root)
    heard = [(HOSTILE if text == "Higgsfield" else text, s, e) for text, s, e in SPEECH]
    install_ear(monkeypatch, heard)
    install_solid_layer(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code in (0, 1) and "error" not in doc, (doc, err)
    text = (root / "qa" / "v1" / "report.json").read_text(encoding="utf-8")
    forbidden = [*BAD, *(chr(c) for c in range(0xE0020, 0xE0080))]
    assert [c for c in forbidden if c in text] == []
    diffs = check_of(json.loads(text), "transcript")["diffs"]
    (shown,) = [d["heard"] for d in diffs if "bogus" in d["heard"]]
    assert "\\u202e" in shown and "\\x1b" in shown and "\\U000e0041" in shown  # seen, as text
