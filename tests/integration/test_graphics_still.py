"""`kcut graphics still` (spec S1.6b rows 7 and 8, 001.15).

Without `--alpha` it is the frame of the cut made from the proxy (`render.preview.base_frame`) with
the graphics blended over it, as an RGB PNG of the size of the video; with `--alpha` it is the PNG
that Chromium made, with alpha 0 where nothing is drawn. The page that Chromium gets for a still has
the subtitles masked (a phone number in the transcript is not in it), because Claude reads what a
still shows. `--out` goes through `assert_writable`: nothing is written in `crudo/` or outside the
project, and the targets are checked before the first frame is made.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import playwright.sync_api as sync_api
import pytest
from numpy.typing import NDArray

from kcut.edl.check import check_edl_file
from kcut.gfx import capture as gfx_capture
from kcut.project import load_inventory, open_project
from kcut.render.frame_fx import fx_context  # 001.31: it moved from `render.preview`
from kcut.render.preview import base_frame
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import write_graphics_v1
from tests.integration.capture_helpers import decode_png
from tests.integration.graphics_helpers import plant_words, tree_hash
from tests.integration.graphics_still_out_cases import *  # noqa: F403  (001.31: 300-line rule)
from tests.integration.view_frames_helpers import Run, project_args, remove

pytestmark = [pytest.mark.ffmpeg, pytest.mark.chromium, pytest.mark.slow]
STILLS = ".kcut/build/v1/gfx/stills"
W, H = 1080, 1920
TITLE_STRIP = (round(0.5 * H), round(0.7 * H))  # `title` is centered at y = 0.6, +-0.1 * H


@pytest.fixture(scope="module")
def shared(view_shared: Path) -> Path:
    """The synthetic project with the example EDL, a transcript planted and the fixture graphics."""
    write_edl_v1(view_shared)
    plant_words(view_shared)
    write_graphics_v1(view_shared, False)
    return view_shared


@pytest.fixture
def fresh(view_fresh: Path) -> Path:
    write_edl_v1(view_fresh)
    plant_words(view_fresh)
    write_graphics_v1(view_fresh, False)
    return view_fresh


def _base(root: Path, f: int) -> NDArray[np.uint8]:
    """`base_frame` of frame `f`, as the command computes it."""
    project = open_project(str(root))
    inventory = load_inventory(project)
    checked = check_edl_file(project, inventory, None)
    assert checked.edl is not None
    ctx = fx_context(project, checked.edl)
    return base_frame(project, checked.edl, inventory, f, ctx, log=None)


def _outside(picture: NDArray[Any], rows: tuple[int, int]) -> NDArray[Any]:
    """The rows of `picture` that are not in `rows` (`[low, high)`)."""
    return np.concatenate([picture[: rows[0]], picture[rows[1] :]])


def _mean_diff(a: NDArray[Any], b: NDArray[Any]) -> float:
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


class TestStill:
    def test_graphics_still_the_json_lists_the_stills_and_each_png_is_rgb_of_the_video_size(
        self, shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json("graphics", "still", "60", "85", *project_args(shared))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert doc["alpha"] is False and doc["warnings"] == []
        assert doc["stills"] == [
            {"f": 60, "png": f"{STILLS}/still_000060.png"},
            {"f": 85, "png": f"{STILLS}/still_000085.png"},
        ]
        for still in doc["stills"]:
            picture = decode_png(shared / still["png"])
            assert picture.shape == (H, W, 3) and picture.dtype == np.uint8

    def test_graphics_still_outside_every_cue_the_pixels_are_the_base_frame(
        self, shared: Path, kcut_json: Run
    ) -> None:
        kcut_json("graphics", "still", "60", "85", *project_args(shared))
        at_60 = decode_png(shared / STILLS / "still_000060.png")
        # frame 60 has the title on: outside its strip the picture is the base frame
        base_60 = _base(shared, 60)
        assert _mean_diff(_outside(at_60, TITLE_STRIP), _outside(base_60, TITLE_STRIP)) < 1
        assert (
            _mean_diff(
                at_60[TITLE_STRIP[0] : TITLE_STRIP[1]], base_60[TITLE_STRIP[0] : TITLE_STRIP[1]]
            )
            > 2
        )  # and inside it the graphics are on top
        # frame 85 has no cue and no subtitle (the title ended at 80, the label starts at 90)
        at_85 = decode_png(shared / STILLS / "still_000085.png")
        assert _mean_diff(at_85, _base(shared, 85)) < 1

    def test_graphics_still_alpha_is_rgba_with_alpha_0_outside_the_cues(
        self, shared: Path, kcut_json: Run
    ) -> None:
        args = ("graphics", "still", "60", "85", "--alpha", *project_args(shared))
        code, doc, err = kcut_json(*args)
        assert code == 0 and doc["alpha"] is True, (doc, err)
        at_60 = decode_png(shared / STILLS / "still_000060.png")
        assert at_60.shape == (H, W, 4)
        assert int(_outside(at_60[:, :, 3], TITLE_STRIP).max()) == 0
        assert int(at_60[TITLE_STRIP[0] : TITLE_STRIP[1], :, 3].max()) > 0
        at_85 = decode_png(shared / STILLS / "still_000085.png")
        assert at_85.shape == (H, W, 4) and int(at_85[:, :, 3].max()) == 0

    def test_graphics_still_a_frame_that_is_asked_for_twice_is_made_once(
        self, shared: Path, kcut_json: Run
    ) -> None:
        code, doc, _ = kcut_json("graphics", "still", "60", "60", "85", "60", *project_args(shared))
        assert code == 0 and [s["f"] for s in doc["stills"]] == [60, 85]

    def test_graphics_still_the_page_has_the_subtitles_masked(
        self, shared: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pages: list[str] = []
        real = gfx_capture.capture_stills

        def spy(page_html: str, *args: Any, **kwargs: Any) -> dict[int, Path]:
            pages.append(page_html)
            return real(page_html, *args, **kwargs)

        monkeypatch.setattr(gfx_capture, "capture_stills", spy)
        code, doc, err = kcut_json("graphics", "still", "150", *project_args(shared))
        assert code == 0, (doc, err)
        (page,) = pages
        for word in ("972", "808", "3211"):  # the phone number that a1 says in the fixture
            assert f'"text":"{word}"' not in page
        assert '"text":"**11"' in page  # the last digits stay, as in `graphics check`
        # the cues are the ones Claude wrote, as they are
        assert '"text":"Higgsfield"' in page  # 001.31: it was one assertion with `or`
        assert "Higgsfield" in page

    def test_graphics_still_the_still_of_a_frame_with_a_subtitle_has_no_phone_digits_in_the_page(
        self, shared: Path, kcut_json: Run
    ) -> None:
        code = kcut_json("graphics", "still", "150", *project_args(shared))[0]
        assert code == 0
        page = (shared / ".kcut/build/v1/gfx/stills_work/page.html").read_text(encoding="utf-8")
        data = json.loads(page.split('id="kc-data">', 1)[1].split("</script>", 1)[0])
        words = [
            w["text"]
            for cue in data["cues"]
            if cue["component"] == "captions"
            for chunk in cue["params"]["chunks"]
            for w in chunk["words"]
        ]
        assert words and "**11" in words and not {"972", "808", "3211"} & set(words)

    def test_graphics_still_the_raw_files_of_chromium_are_not_kept(
        self, shared: Path, kcut_json: Run
    ) -> None:
        kcut_json("graphics", "still", "60", *project_args(shared))
        work = shared / ".kcut" / "build" / "v1" / "gfx" / "stills_work"
        assert [p.name for p in work.glob("*.png")] == []

    def test_graphics_still_a_frame_outside_the_video_is_exit_2_and_makes_nothing(
        self, shared: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shutil.rmtree(shared / STILLS, ignore_errors=True)
        monkeypatch.setattr(sync_api, "sync_playwright", lambda: pytest.fail("Chromium"))
        for bad in ("345", "9999"):
            code, doc, _ = kcut_json("graphics", "still", "60", bad, *project_args(shared))
            assert code == 2 and doc["error"]["kind"] == "UsageError"
            assert "va de 0 a 344" in doc["error"]["message"]
        assert not (shared / STILLS).exists()

    def test_graphics_still_a_negative_frame_is_exit_2(self, shared: Path, kcut_json: Run) -> None:
        assert kcut_json("graphics", "still", "-1", *project_args(shared))[0] == 2

    def test_graphics_still_nothing_to_draw_is_the_base_frame_and_no_chromium(
        self, view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """001.15 point 40: no `graphics.json` and the subtitles off: `resolved.empty`. The still
        is the base frame, and with `--alpha` an RGBA PNG with alpha 0 all over; Chromium is not
        started."""
        write_edl_v1(view_fresh)
        toml = view_fresh / "kcut.toml"
        text = toml.read_text(encoding="utf-8").replace(
            "[captions]\nenabled = true", "[captions]\nenabled = false"
        )
        toml.write_text(text, encoding="utf-8", newline="\n")
        monkeypatch.setattr(sync_api, "sync_playwright", lambda: pytest.fail("Chromium"))
        code, doc, err = kcut_json("graphics", "still", "60", *project_args(view_fresh))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert "G12" in [w["code"] for w in doc["warnings"]]
        still = decode_png(view_fresh / doc["stills"][0]["png"])
        assert still.shape == (H, W, 3) and _mean_diff(still, _base(view_fresh, 60)) < 1
        code, doc, err = kcut_json("graphics", "still", "60", "--alpha", *project_args(view_fresh))
        assert code == 0, (doc, err)
        clear = decode_png(view_fresh / doc["stills"][0]["png"])
        assert clear.shape == (H, W, 4) and int(clear.max()) == 0  # alpha 0 all over (and black)

    def test_graphics_still_a_proxy_that_is_missing_is_exit_3_that_says_ingest(
        self, fresh: Path, kcut_json: Run
    ) -> None:
        remove(fresh, "a1", "proxy")
        code, doc, _ = kcut_json("graphics", "still", "60", *project_args(fresh))
        assert code == 3 and doc["error"]["kind"] == "ProjectError"
        assert "falta el proxy de a1; corre kcut ingest" in doc["error"]["message"]

    def test_graphics_still_errors_in_the_graphics_are_exit_1_before_anything_is_made(
        self, fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        document = json.loads((fresh / "edit" / "graphics.json").read_text(encoding="utf-8"))
        document["cues"][1]["end"] = 999
        (fresh / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")
        monkeypatch.setattr(sync_api, "sync_playwright", lambda: pytest.fail("Chromium"))
        code, doc, _ = kcut_json("graphics", "still", "60", *project_args(fresh))
        assert code == 1 and doc["error"]["kind"] == "CheckFailed" and "G07" in doc["error"][
            "message"]  # fmt: skip

    def test_graphics_still_an_edl_with_errors_is_exit_1_with_the_e_codes(
        self, fresh: Path, kcut_json: Run
    ) -> None:
        path = fresh / "edit" / "edl-v1.json"
        edl = json.loads(path.read_text(encoding="utf-8"))
        edl["frames"] = 346
        path.write_text(json.dumps(edl), encoding="utf-8")
        code, doc, _ = kcut_json("graphics", "still", "60", *project_args(fresh))
        assert code == 1 and "E08" in doc["error"]["message"]


class TestStillOut:
    """Row 8: `--out` is checked by `assert_writable` before any frame is made."""

    def test_graphics_still_out_in_the_project_writes_the_files_there(
        self, shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json(
            "graphics", "still", "60", "85", "--out", "qa/vistas", *project_args(shared)
        )
        assert code == 0, (doc, err)
        assert [s["png"] for s in doc["stills"]] == [
            "qa/vistas/still_000060.png", "qa/vistas/still_000085.png"]  # fmt: skip
        assert all((shared / s["png"]).is_file() for s in doc["stills"])

    def test_graphics_still_out_crudo_is_exit_3_and_crudo_is_left_as_it_was(
        self, fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        before = tree_hash(fresh / "crudo")
        monkeypatch.setattr(sync_api, "sync_playwright", lambda: pytest.fail("Chromium"))
        for out in ("crudo", "crudo/sub", "CRUDO", "crudo/"):
            code, doc, _ = kcut_json("graphics", "still", "60", "--out", out, *project_args(fresh))
            assert code == 3 and doc["error"]["kind"] == "ProjectError", out
        assert tree_hash(fresh / "crudo") == before
        assert sorted(p.name for p in (fresh / "crudo").iterdir()) == sorted(
            p.name for p in (fresh / "crudo").glob("*")
        )

    @pytest.mark.parametrize("out", ["../fuera", "/abs", "C:/x", "a/../../b", "x:y", "CON"])
    def test_graphics_still_out_a_path_that_is_not_allowed_is_exit_3(
        self, fresh: Path, kcut_json: Run, out: str
    ) -> None:
        code, doc, _ = kcut_json("graphics", "still", "60", "--out", out, *project_args(fresh))
        assert code == 3 and doc["error"]["kind"] == "ProjectError"

    def test_graphics_still_out_a_link_that_leaves_the_project_is_exit_3_and_writes_nothing(
        self, fresh: Path, kcut_json: Run
    ) -> None:
        outside = fresh.parent / "ajeno"
        outside.mkdir()
        link = fresh / "enlace"
        make_dir_link(link, outside)
        try:
            args = ("graphics", "still", "60", "--out", "enlace", *project_args(fresh))
            code, doc, _ = kcut_json(*args)
        finally:
            remove_dir_link(link)
        assert code == 3 and doc["error"]["kind"] == "ProjectError"
        assert list(outside.iterdir()) == []

    def test_graphics_still_out_every_target_is_checked_before_the_first_is_made(
        self, fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A folder where the second still goes: exit 3, and the first one is not made either."""
        (fresh / "qa" / "v" / "still_000085.png").mkdir(parents=True)
        monkeypatch.setattr(sync_api, "sync_playwright", lambda: pytest.fail("Chromium"))
        code, doc, _ = kcut_json(
            "graphics", "still", "60", "85", "--out", "qa/v", *project_args(fresh)
        )
        assert code == 3 and doc["error"]["kind"] == "ProjectError"
        assert not (fresh / "qa" / "v" / "still_000060.png").exists()
