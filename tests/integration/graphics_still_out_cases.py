"""`graphics still --out` inside `.kcut/` (spec S1.6b round 1, 001.31 point 9; row 27): it is a
UsageError (exit 2) before Chromium starts, because `assert_writable` replaces a file that is
under `.kcut/` without `--force`, and `--out .kcut/transcripts` would write next to the
transcripts. Without `--out` the stills go to `.kcut/build/vN/gfx/stills/`. A `--out` outside
`.kcut/` still replaces a `still_NNNNNN.png` that is there (D9: the name is fixed).

Collected from `test_graphics_still.py`, which is at the 300-line limit: its `fresh` fixture (the
synthetic project with the example EDL, a transcript and the fixture graphics) is the one used.
"""

from pathlib import Path

import playwright.sync_api as sync_api
import pytest

from tests.integration.fake_shooter import install_fake_shooter
from tests.integration.graphics_helpers import tree_hash
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["TestStillOutKcut"]
MESSAGE = (
    "--out no puede ir dentro de .kcut/; sin --out los stills van a .kcut/build/vN/gfx/stills/"
)


class TestStillOutKcut:
    @pytest.mark.parametrize(
        "out",
        [
            ".kcut/transcripts",
            ".kcut",
            ".kcut/",
            ".KCUT/transcripts",
            "./.kcut/build",
            "qa/../.kcut",
        ],
    )
    def test_graphics_still_out_kcut_is_exit_2_before_chromium_and_nothing_is_written(
        self, fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, out: str
    ) -> None:
        transcripts = fresh / ".kcut" / "transcripts"
        before = tree_hash(transcripts)
        assert before and any(transcripts.iterdir())
        monkeypatch.setattr(sync_api, "sync_playwright", lambda: pytest.fail("se lanzó Chromium"))
        code, doc, _ = kcut_json("graphics", "still", "60", "--out", out, *project_args(fresh))
        assert code == 2 and doc["error"]["kind"] == "UsageError", (out, doc)
        assert doc["error"]["message"] == MESSAGE
        assert tree_hash(transcripts) == before
        assert not list(fresh.rglob("still_*.png"))

    def test_graphics_still_out_kcut_a_folder_outside_replaces_the_still_that_is_there(
        self, fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_shooter(monkeypatch)
        args = ("graphics", "still", "60", "--out", "qa/vistas", *project_args(fresh))
        assert kcut_json(*args)[0] == 0
        still = fresh / "qa" / "vistas" / "still_000060.png"
        still.write_bytes(b"an old one")
        code, doc, err = kcut_json(*args)  # no `--force`: the name is fixed (D9)
        assert code == 0, (doc, err)
        assert still.read_bytes() != b"an old one" and still.stat().st_size > 1000

    def test_graphics_still_out_kcut_without_out_the_stills_go_under_kcut_as_before(
        self, fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_shooter(monkeypatch)
        code, doc, err = kcut_json("graphics", "still", "60", *project_args(fresh))
        assert code == 0, (doc, err)
        assert doc["stills"] == [{"f": 60, "png": ".kcut/build/v1/gfx/stills/still_000060.png"}]
