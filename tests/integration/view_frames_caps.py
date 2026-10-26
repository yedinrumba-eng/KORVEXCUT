"""Rows 28 and 32 of S1.4 (001.20 points 5 and 9): the sheet of `frames` and `--out`.

Collected from `test_view_frames_synth.py`.
"""

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from kcut.commands import frames as frames_cmd
from kcut.commands import view as view_cmd
from tests.fixtures.peak_memory import measure
from tests.integration.view_frames_helpers import Run, project_args, size

__all__ = ["TestOutBadName", "TestOutNoOverwrite", "TestSheetCapped"]
LIMIT_MPX = 25_000_000


def _fake_grab(*args: Any, **kwargs: Any) -> NDArray[np.uint8]:
    return np.full((960, 540, 3), 90, dtype=np.uint8)


class TestSheetCapped:
    def test_sheet_capped_width_never_passes_the_width_of_the_proxy(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json(
            "frames", "a1", "30", "--width", "1920", *project_args(view_shared)
        )
        assert code == 0, err
        assert size(view_shared / doc["frames"][0]["png"])[0] == 540  # the proxy is 540 wide
        assert doc["width"] == 540 and doc["cell_width"] is None  # one frame: no sheet

    def test_sheet_capped_the_json_tells_the_real_width_of_a_cell(
        self, view_shared: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(frames_cmd, "grab", _fake_grab)
        code, doc, err = kcut_json("frames", "a1", "30", "60", "90", *project_args(view_shared))
        assert code == 0, err
        assert doc["width"] == 540 and doc["cell_width"] == 540  # three frames fit as they are
        # 001.22: 64 times in one frame are one frame now, so the 64 are different frames
        times = [str(f) for f in range(64)]
        code, doc, err = kcut_json("frames", "a1", *times, *project_args(view_shared))
        assert code == 0, err
        assert doc["width"] == 540 and 100 < doc["cell_width"] < 540
        width, height = size(view_shared / doc["sheet"])
        assert width * height <= LIMIT_MPX

    def test_sheet_capped_64_times_with_width_1920_fit_25_mpx_and_600_mb(
        self, view_shared: Path
    ) -> None:
        # 001.22: equal times are one frame now: the 64 are 64 different frames, 0 to 63
        code = (
            "from pathlib import Path\n"
            "import numpy as np\n"
            "from PIL import Image\n"
            "from kcut import cli\n"
            "from kcut.commands import frames\n"
            "frames.grab = lambda *a, **k: np.full((960, 540, 3), 90, dtype=np.uint8)\n"
            "mark()\n"
            f"root = {str(view_shared)!r}\n"
            "argv = ['frames', 'a1', *map(str, range(64)), '--width', '1920', '--project', root]\n"
            "print('exit', cli.main(argv))\n"
            "sheet = Path(root) / '.kcut' / 'frames' / 'a1_sheet_0-63.png'\n"
            "print('sheet', Image.open(sheet).size)\n"
        )
        done = measure(code)
        assert done.returncode == 0 and "exit 0" in done.stdout, done.stderr
        width, height = eval(done.stdout.rsplit("sheet", 1)[1])
        assert width * height <= LIMIT_MPX
        assert done.ws_peak_mb < 600, done


class TestOutNoOverwrite:
    def test_out_no_overwrite_view_does_not_replace_a_file_of_the_project(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        logo = view_fresh / "recursos" / "logo.png"
        logo.parent.mkdir(exist_ok=True)
        logo.write_bytes(b"EL LOGO DEL CLIENTE")
        code, doc, _ = kcut_json(
            "view", "a1", "0", "2s", "--out", "recursos/logo.png", *project_args(view_fresh)
        )
        assert code == 2 and doc["error"]["kind"] == "UsageError"
        assert (
            "recursos/logo.png" in doc["error"]["message"] and "--force" in doc["error"]["message"]
        )
        assert logo.read_bytes() == b"EL LOGO DEL CLIENTE"

    def test_out_no_overwrite_with_force_it_does(self, view_fresh: Path, kcut_json: Run) -> None:
        target = view_fresh / "edit" / "vista.png"
        target.write_bytes(b"viejo")
        args = ("view", "a1", "0", "2s", "--out", "edit/vista.png", *project_args(view_fresh))
        assert kcut_json(*args)[0] == 2 and target.read_bytes() == b"viejo"
        code, _, err = kcut_json(*args, "--force")
        assert code == 0, err
        with Image.open(target) as image:
            assert image.size == (2400, 420)

    def test_out_no_overwrite_the_default_place_under_kcut_is_always_replaced(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        for _ in range(2):
            assert kcut_json("view", "a1", "0", "2s", *project_args(view_fresh))[0] == 0

    def test_out_no_overwrite_frames_checks_every_file_before_writing_any(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        folder = view_fresh / "qa" / "muestras"
        folder.mkdir(parents=True)
        (folder / "a1_sheet_30-60.png").write_bytes(b"VIEJA")  # only the sheet is in the way
        code, doc, _ = kcut_json(
            "frames", "a1", "30", "60", "--out", "qa/muestras", *project_args(view_fresh)
        )
        assert code == 2 and "a1_sheet_30-60.png" in doc["error"]["message"]
        assert sorted(p.name for p in folder.iterdir()) == ["a1_sheet_30-60.png"]
        code, _, err = kcut_json(
            "frames", "a1", "30", "60", "--out", "qa/muestras", "--force", *project_args(view_fresh)
        )
        assert code == 0, err
        assert (folder / "a1_f30.png").is_file() and (
            folder / "a1_sheet_30-60.png"
        ).stat().st_size > 5

    def test_no_replace_race_view_keeps_a_file_that_appeared_after_the_check(
        self, view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = view_fresh / "edit" / "vista.png"
        real = view_cmd.png_bytes

        def racing(image: Any) -> bytes:
            target.write_bytes(b"OTRO PROCESO")  # after `assert_writable`, before the write
            return real(image)

        monkeypatch.setattr(view_cmd, "png_bytes", racing)
        args = ("view", "a1", "0", "2s", "--out", "edit/vista.png", *project_args(view_fresh))
        code, doc, _ = kcut_json(*args)
        assert code == 2 and doc["error"]["kind"] == "UsageError"
        assert target.read_bytes() == b"OTRO PROCESO"

    def test_no_replace_race_frames_keeps_a_file_that_appeared_after_the_check(
        self, view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        folder = view_fresh / "qa" / "muestras"
        folder.mkdir(parents=True)
        real = frames_cmd.png_bytes

        def racing(image: Any) -> bytes:
            (folder / "a1_f30.png").write_bytes(b"OTRO PROCESO")
            return real(image)

        monkeypatch.setattr(frames_cmd, "png_bytes", racing)
        code, doc, _ = kcut_json(
            "frames", "a1", "30", "--out", "qa/muestras", *project_args(view_fresh)
        )
        assert code == 2 and doc["error"]["kind"] == "UsageError"
        assert (folder / "a1_f30.png").read_bytes() == b"OTRO PROCESO"

    def test_no_replace_race_under_kcut_even_an_out_is_replaced_without_force(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        args = ("frames", "a1", "30", "--out", ".kcut/mias", *project_args(view_fresh))
        assert kcut_json(*args)[0] == 0
        (view_fresh / ".kcut" / "mias" / "a1_f30.png").write_bytes(b"viejo")
        assert kcut_json(*args)[0] == 0
        assert (view_fresh / ".kcut" / "mias" / "a1_f30.png").read_bytes() != b"viejo"

    def test_out_no_overwrite_frames_second_run_in_the_same_folder_is_refused(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        args = ("frames", "a1", "30", "--out", "qa/otra", *project_args(view_fresh))
        assert kcut_json(*args)[0] == 0
        stamp = os.stat(view_fresh / "qa" / "otra" / "a1_f30.png").st_mtime_ns
        code, doc, _ = kcut_json(*args)
        assert code == 2 and "a1_f30.png" in doc["error"]["message"]
        assert os.stat(view_fresh / "qa" / "otra" / "a1_f30.png").st_mtime_ns == stamp


class TestOutBadName:
    @pytest.mark.parametrize(
        "name",
        [
            "edit/a*b.png",
            "edit/x?.png",
            "edit/<x>.png",
            "edit/p|q.png",
            'edit/"q".png',
            "edit/" + "a" * 300 + ".png",
        ],
    )
    def test_out_bad_name_view_is_a_project_error_never_an_internal_one(
        self, view_fresh: Path, kcut_json: Run, name: str
    ) -> None:
        code, doc, _ = kcut_json("view", "a1", "0", "2s", "--out", name, *project_args(view_fresh))
        assert code == 3 and doc["error"]["kind"] == "ProjectError"

    def test_out_bad_name_a_parent_that_is_a_file(self, view_fresh: Path, kcut_json: Run) -> None:
        (view_fresh / "edit" / "vista.png").write_bytes(b"un archivo")
        code, doc, _ = kcut_json(
            "view", "a1", "0", "2s", "--out", "edit/vista.png/otra.png", *project_args(view_fresh)
        )
        assert code == 3 and doc["error"]["kind"] == "ProjectError"

    def test_out_bad_name_frames_with_a_folder_that_cannot_be_made(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        (view_fresh / "edit" / "plano").write_bytes(b"un archivo")
        for folder in ("edit/plano", "edit/a*b", "edit/" + "d" * 300):
            code, doc, _ = kcut_json(
                "frames", "a1", "30", "--out", folder, *project_args(view_fresh)
            )
            assert code == 3 and doc["error"]["kind"] == "ProjectError", folder
            assert code != 10 and json.dumps(doc)
