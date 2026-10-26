"""`kcut view` and `kcut frames` on the synthetic project, with real ffmpeg (spec S1.4).

The project is a copy of the session's synthetic one (cameras a1 and a2, the screen b1, a photo),
so what these tests write under `.kcut/` or `edit/` does not reach the other tests. The clip whose
video starts 0.5 s after its audio (row 14) is in `view_frames_late.py` and collected from here.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from kcut.ingest.inventory import load_inventory as read_inventory
from kcut.paths import resolve_in_project
from kcut.project import open_project
from kcut.transcribe.cache import file_sha256, save_transcript, wav16_length_ms
from kcut.transcribe.model import Segment, Transcript, Word
from tests.conftest import run_kcut
from tests.integration.ingest_helpers import snapshot
from tests.integration.view_frames_caps import *  # noqa: F403
from tests.integration.view_frames_helpers import Run, gray, project_args, remove, size
from tests.integration.view_frames_late import *  # noqa: F403
from tests.integration.view_frames_step0 import *  # noqa: F403
from tests.integration.view_frames_stream import *  # noqa: F403
from tests.unit.transcribe_fakes import params_for

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]

FLASH_FRAME = 90  # camera a1 flashes white on its frame 90 (synth_media)
NO_FLASH = 60


class TestFrames:
    def test_frames_the_flash_is_frame_90_and_frame_60_is_not(self, view_shared: Path) -> None:
        shown = run_kcut("frames", "a1", str(FLASH_FRAME), "--project", str(view_shared), "--json")
        other = run_kcut("frames", "a1", str(NO_FLASH), "--project", str(view_shared), "--json")
        assert shown.returncode == 0 and other.returncode == 0, shown.stderr + other.stderr
        flash = json.loads(shown.stdout)["frames"][0]
        assert flash == {"f": FLASH_FRAME, "png": ".kcut/frames/a1_f90.png"}
        assert gray(view_shared / flash["png"]) >= 200
        assert gray(view_shared / json.loads(other.stdout)["frames"][0]["png"]) <= 180

    def test_frames_the_proxy_frame_is_exact_the_neighbours_are_not_the_flash(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        for f in (FLASH_FRAME - 1, FLASH_FRAME + 1):
            code, doc, err = kcut_json("frames", "a1", str(f), "--project", str(view_shared))
            assert code == 0, err
            assert gray(view_shared / doc["frames"][0]["png"]) <= 180

    def test_frames_times_in_seconds_and_in_clock_form_read_the_same_frame(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json(
            "frames", "a1", "3s", "0:03", "90", "--project", str(view_shared)
        )
        assert code == 0, err
        assert [item["f"] for item in doc["frames"]] == [90]  # 001.22: the same frame, once
        assert all(gray(view_shared / item["png"]) >= 200 for item in doc["frames"])

    def test_frames_several_times_make_a_sheet_named_by_the_first_and_the_last(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json("frames", "a1", "60", "90", "120", "--project", str(view_shared))
        assert code == 0, err
        assert [item["f"] for item in doc["frames"]] == [60, 90, 120]
        assert doc["sheet"] == ".kcut/frames/a1_sheet_60-120.png"
        width, height = size(view_shared / doc["frames"][0]["png"])
        assert size(view_shared / doc["sheet"]) == (3 * width, height + 24)

    def test_frames_one_time_makes_no_sheet(self, view_shared: Path, kcut_json: Run) -> None:
        code, doc, _ = kcut_json("frames", "a1", "30", "--project", str(view_shared))
        assert code == 0 and doc["sheet"] is None

    def test_frames_width_and_grid_are_honoured_and_the_aspect_is_kept(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json(
            "frames", "a1", "30", "--width", "300", "--grid", "20", *project_args(view_shared)
        )
        assert code == 0, err
        path = view_shared / doc["frames"][0]["png"]
        width, height = size(path)
        assert width == 300 and abs(height - 300 * 960 / 540) <= 1  # the 9:16 proxy
        pixels = np.asarray(Image.open(path).convert("RGB"))
        assert tuple(pixels[height - 1, 60]) == (0, 255, 255)  # a grid line at 20 %

    def test_frames_a_screen_without_audio_works_too(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json("frames", "b1", "30", "--project", str(view_shared))
        assert code == 0, err
        assert size(view_shared / doc["frames"][0]["png"])[0] == 540

    def test_frames_out_writes_in_the_folder_asked(self, view_shared: Path, kcut_json: Run) -> None:
        code, doc, err = kcut_json(
            "frames", "a1", "30", "60", "--out", "qa/muestras", *project_args(view_shared)
        )
        assert code == 0, err
        assert doc["frames"][0]["png"] == "qa/muestras/a1_f30.png"
        assert doc["sheet"] == "qa/muestras/a1_sheet_30-60.png"
        assert all((view_shared / item["png"]).is_file() for item in doc["frames"])

    def test_frames_human_output_lists_the_files(self, view_shared: Path) -> None:
        done = run_kcut("frames", "a1", "30", "--project", str(view_shared))
        assert done.returncode == 0 and "[OK] .kcut/frames/a1_f30.png" in done.stdout

    @pytest.mark.parametrize(
        "args",
        [
            ["z9", "30"],  # unknown clip
            ["a1", "abc"],  # not a time
            ["a1", "-3"],
            ["a1", "360"],  # the clip has 360 frames: 0..359
            ["a1", "13s"],  # past the end
            ["a1", "30", "--width", "63"],
            ["a1", "30", "--width", "1921"],
            ["a1", "30", "--grid", "0"],
            ["a1", "30", "--grid", "100"],
        ],
    )
    def test_frames_what_makes_no_sense_is_exit_2(
        self, view_shared: Path, kcut_json: Run, args: list[str]
    ) -> None:
        code, doc, _ = kcut_json("frames", *args, *project_args(view_shared))
        assert code == 2 and doc["error"]["kind"] == "UsageError"

    def test_frames_no_proxy_is_exit_3_and_says_ingest(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        remove(view_fresh, "a1", "proxy")
        code, doc, _ = kcut_json("frames", "a1", "30", *project_args(view_fresh))
        assert code == 3 and doc["error"]["message"] == "falta el proxy de a1; corre kcut ingest"

    def test_frames_out_crudo_is_refused_and_crudo_stays_as_it_was(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        before = snapshot(view_fresh / "crudo")
        code, doc, _ = kcut_json("frames", "a1", "30", "--out", "crudo", *project_args(view_fresh))
        assert code == 3 and doc["error"]["kind"] == "ProjectError"
        assert snapshot(view_fresh / "crudo") == before  # same hash, same mtime, no new file

    def test_frames_out_outside_the_project_or_absolute_is_exit_3(
        self, view_fresh: Path, kcut_json: Run, tmp_path: Path
    ) -> None:
        for out in ("../fuera", str(tmp_path / "fuera")):
            code, doc, _ = kcut_json("frames", "a1", "30", "--out", out, *project_args(view_fresh))
            assert code == 3 and doc["error"]["kind"] == "ProjectError", out
        assert not (tmp_path / "fuera").exists()


class TestView:
    def test_view_png(self, view_shared: Path) -> None:
        done = run_kcut(
            "view", "a1", "60", "240", "--filmstrip", "6", "--project", str(view_shared), "--json"
        )
        assert done.returncode == 0, done.stderr
        doc = json.loads(done.stdout)
        assert set(doc) == {"ok", "png", "words", "silences", "notice", "warnings"}
        assert doc["ok"] is True and doc["png"] == ".kcut/view/a1_60-240.png"
        assert isinstance(doc["silences"], int) and doc["warnings"] == []
        assert size(view_shared / doc["png"]) == (2400, 640)  # 420 + the strip of 220

    def test_view_no_transcript_draws_the_wave_with_a_notice(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json("view", "a1", "0", "3s", *project_args(view_shared))
        assert code == 0, err
        assert doc["words"] == 0 and doc["notice"] == "sin transcripcion"
        assert size(view_shared / doc["png"]) == (2400, 420)  # no filmstrip asked: no strip

    def test_view_with_a_transcript_draws_its_words(self, view_fresh: Path, kcut_json: Run) -> None:
        project = open_project(str(view_fresh))
        clip = read_inventory(view_fresh / ".kcut" / "inventory.json").by_id("a1")
        assert clip is not None and clip.work is not None and clip.work.wav16 is not None
        wav = resolve_in_project(view_fresh, clip.work.wav16)
        words = [
            Word("a1:w0000", 0, "Hola,", 3450, 3650, 0.9),  # on a tone: not a silence
            Word("a1:w0001", 1, "mundo", 5150, 5400, 0.2),  # on a tone too, but p = 0.2
            Word("a1:w0002", 2, "fin", 9000, 9300, 0.9),
        ]
        transcript = Transcript(
            "a1", "ab" * 32, "es", 0.98, wav16_length_ms(wav), words,
            [Segment(4000, 5000, "Hola, mundo")], params_for(), 1.0,
        )  # fmt: skip
        save_transcript(project, transcript, file_sha256(wav))
        code, doc, err = kcut_json("view", "a1", "3s", "6s", *project_args(view_fresh))
        assert code == 0, err
        assert doc["words"] == 2 and doc["notice"] is None  # "fin" is at 9 s: outside 3 s - 6 s
        pixels = np.asarray(Image.open(view_fresh / doc["png"]).convert("RGB"))
        assert np.any(np.all(pixels == (240, 200, 40), axis=-1))  # "Hola," is sure
        assert np.any(np.all(pixels == (255, 120, 30), axis=-1))  # "mundo": p = 0.2 < low_prob

    def test_view_out_writes_the_png_where_asked_whatever_the_case_of_the_extension(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json(
            "view", "a1", "0", "2s", "--out", "edit/vista.PNG", *project_args(view_shared)
        )
        assert code == 0, err
        assert doc["png"] == "edit/vista.PNG" and (view_shared / "edit" / "vista.PNG").is_file()

    def test_view_human_output_is_one_ok_line(self, view_shared: Path) -> None:
        done = run_kcut("view", "a1", "0", "2s", "--project", str(view_shared))
        assert done.returncode == 0 and "[OK] .kcut/view/a1_0-60.png" in done.stdout

    def test_view_no_wav16_is_exit_3_and_says_ingest(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        remove(view_fresh, "a1", "wav16")
        code, doc, _ = kcut_json("view", "a1", "0", "2s", *project_args(view_fresh))
        assert code == 3
        assert doc["error"]["message"] == "falta el wav16 de a1; corre kcut ingest"

    def test_view_no_audio_is_exit_2_and_points_to_frames(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        code, doc, _ = kcut_json("view", "b1", "0", "2s", *project_args(view_shared))
        assert code == 2 and doc["error"]["message"] == "b1 no tiene audio; usa kcut frames"

    @pytest.mark.parametrize("count", ["13", "-1", "100"])
    def test_view_filmstrip_range_is_0_to_12(
        self, view_shared: Path, kcut_json: Run, count: str
    ) -> None:
        code, doc, _ = kcut_json(
            "view", "a1", "0", "2s", "--filmstrip", count, *project_args(view_shared)
        )
        assert code == 2 and "--filmstrip" in doc["error"]["message"]

    def test_view_filmstrip_12_is_the_most_and_0_the_default(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json(
            "view", "a1", "0", "2s", "--filmstrip", "12", *project_args(view_shared)
        )
        assert code == 0, err
        assert size(view_shared / doc["png"]) == (2400, 640)

    def test_view_filmstrip_no_proxy_is_exit_3_but_without_a_filmstrip_it_works(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        remove(view_fresh, "a1", "proxy")
        code, doc, _ = kcut_json(
            "view", "a1", "0", "2s", "--filmstrip", "3", *project_args(view_fresh)
        )
        assert code == 3 and doc["error"]["message"] == "falta el proxy de a1; corre kcut ingest"
        assert kcut_json("view", "a1", "0", "2s", *project_args(view_fresh))[0] == 0

    @pytest.mark.parametrize(
        "args",
        [
            ["z9", "0", "2s"],  # unknown clip
            ["a1", "60", "60"],  # empty
            ["a1", "60", "30"],  # backwards
            ["a1", "0", "61s"],  # more than 60 s
            ["a1", "0", "13s"],  # past the 12 s of audio
            ["a1", "uno", "2s"],
        ],
    )
    def test_view_what_makes_no_sense_is_exit_2(
        self, view_shared: Path, kcut_json: Run, args: list[str]
    ) -> None:
        code, doc, _ = kcut_json("view", *args, *project_args(view_shared))
        assert code == 2 and doc["error"]["kind"] == "UsageError"

    def test_view_out_that_is_not_a_png_is_exit_2(self, view_shared: Path, kcut_json: Run) -> None:
        for out in ("x.txt", "x.png.txt", "x", "x.jpg"):
            code, doc, _ = kcut_json(
                "view", "a1", "0", "2s", "--out", out, *project_args(view_shared)
            )
            assert code == 2 and doc["error"]["kind"] == "UsageError", out
        assert not (view_shared / "x.txt").exists()

    def test_view_out_crudo_is_refused_and_crudo_stays_as_it_was(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        before = snapshot(view_fresh / "crudo")
        code, doc, _ = kcut_json(
            "view", "a1", "60", "240", "--out", "crudo/x.png", *project_args(view_fresh)
        )
        assert code == 3 and doc["error"]["kind"] == "ProjectError"
        assert snapshot(view_fresh / "crudo") == before
        assert not (view_fresh / "crudo" / "x.png").exists()

    def test_view_out_outside_the_project_is_exit_3(self, view_fresh: Path, kcut_json: Run) -> None:
        for out in ("../fuera.png", "C:/fuera.png", "//servidor/x/fuera.png"):
            code, doc, _ = kcut_json(
                "view", "a1", "0", "2s", "--out", out, *project_args(view_fresh)
            )
            assert code == 3 and doc["error"]["kind"] == "ProjectError", out
