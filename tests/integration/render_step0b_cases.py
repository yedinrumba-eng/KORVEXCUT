"""`kcut render` and what it says, S1.6b step 0 (spec 001.30; rows 14 and 16).

Collected from `test_render_synth.py`, which is at the 300-line limit. `small` is the fixture of
`render_small_cases.py` (a copy of the project with the 2 s EDL, already rendered once).
"""

import json
import shutil
from collections import namedtuple
from pathlib import Path

import pytest

from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.fixtures.synth_edl import write_edl_v1
from tests.integration.render_small_cases import render_json
from tests.integration.view_frames_helpers import Run, Synth, project_args

__all__ = ["TestCacheGuardLabelRender", "TestDiskFullLongPath"]
LONG_ROOT = 205  # characters of the project path: over the 200 that the row asks for, and under
# the 260 of Windows once `.kcut/logs/render-<date>-<pid>.log` is added to it
SLUG = "ana-perez-809-555-1234"  # of `Ana Perez 809-555-1234.mp4`, as `ingest` makes it
LEAKS = ("ana", "perez", "809", "555", "1234")


class TestCacheGuardLabelRender:
    """Row 14: a junction where the wav48 goes, that leads out of `.kcut/`, is exit 3 and the
    message names `wav48 de a1`, not the file (its name has the slug of the original clip)."""

    @staticmethod
    def _renamed(small: Path) -> Path:
        """Give a1 the slug of a clip with a phone number in its name; return where its wav48
        goes. The slug is only a name: the rest of the inventory stays as `ingest` left it."""
        path = small / ".kcut" / "inventory.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        (clip,) = [c for c in document["clips"] if c["id"] == "a1"]
        clip["slug"] = SLUG
        path.write_text(json.dumps(document, indent=1), encoding="utf-8", newline="\n")
        return small / ".kcut" / "wav48" / f"a1_{SLUG}.wav"

    def test_cache_guard_label_a_junction_out_of_the_cache_is_exit_3_with_the_clip_not_the_slug(
        self, small: Path
    ) -> None:
        wav = self._renamed(small)
        outside = small.parent / "ajeno"
        outside.mkdir()
        make_dir_link(wav, outside)
        try:
            code, doc, err = render_json(small)
        finally:
            remove_dir_link(wav)  # the link, not what it points at
        assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
        message = doc["error"]["message"]
        assert message.startswith("wav48 de a1 queda fuera de .kcut/"), message
        assert not any(piece in (message + err).lower() for piece in LEAKS)
        assert list(outside.iterdir()) == []  # nothing was written through the link


class TestDiskFullLongPath:
    """Row 16 (001.30 point 4): the figure of a full disk comes before the path, so the cut of the
    message to 300 characters (`MAX_MESSAGE`) cannot take it away in a deep folder."""

    @staticmethod
    def _deep_copy(synth: Synth, tmp_path: Path) -> Path:
        """The synthetic project in a path of `LONG_ROOT` characters (a folder of padding is added
        to whatever the temporary folder is, so it holds with any `--basetemp`)."""
        sep = len(str(tmp_path / "x")) - len(str(tmp_path))
        name = "proyecto ñandú"
        pad = max(1, LONG_ROOT - len(str(tmp_path)) - 2 * sep - len(name))
        root = tmp_path / ("p" * pad) / name
        shutil.copytree(synth[0], root)
        return root

    def test_disk_full_long_path_the_message_that_kcut_prints_keeps_the_figure(
        self, synth_project: Synth, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._deep_copy(synth_project, tmp_path)
        assert len(str(root)) >= 200
        write_edl_v1(root)
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr(shutil, "disk_usage", lambda _path: usage(10**12, 10**12, 1000))
        code, doc, err = kcut_json("render", "--no-graphics", *project_args(root))
        needed = 345 * 1600 * 4 + 2**30
        message = doc["error"]["message"]
        assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
        assert len(message) <= 300
        assert f"faltan {needed - 1000} bytes" in message
        assert f"piden {needed}, hay 1000" in message
