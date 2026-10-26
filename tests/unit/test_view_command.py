"""`kcut view` on a project written by hand (no ffmpeg): the rules of the window, the audio, the
silences and the output (spec S1.4, 001.15). The pictures with frames are integration tests."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from kcut import cli
from kcut.audio.wavio import write_wav_s16_mono
from tests.unit.test_pack_command import LAYOUT
from tests.unit.transcribe_fakes import SR, FakeClip, build_project, install_fake_engine, tone

# LAYOUT: quiet 0-1 s, loud 1-3 s, quiet 3-4.5 s, loud 4.5-6 s, quiet 6-8 s (240 frames at 30 fps)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return build_project(tmp_path / "proyecto ñandú", [FakeClip("a1", LAYOUT)], master="a1").root


def _view(
    root: Path, capsys: pytest.CaptureFixture[str], *args: str
) -> tuple[int, dict[str, Any], str]:
    capsys.readouterr()
    code = cli.main(["view", *args, "--project", str(root), "--json"])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


class TestWindow:
    @pytest.mark.parametrize(
        ("start", "end", "bands"),
        [("0", "8s", 3), ("2s", "4s", 1), ("2s", "2.5s", 0), ("7s", "8s", 1), ("0", "1s", 1)],
    )
    def test_view_command_the_bands_are_the_silences_that_touch_the_window(
        self, root: Path, capsys: pytest.CaptureFixture[str], start: str, end: str, bands: int
    ) -> None:
        code, doc, err = _view(root, capsys, "a1", start, end)
        assert code == 0, err
        assert doc["silences"] == bands

    def test_view_command_a_window_of_exactly_60_seconds_is_accepted_and_one_frame_more_not(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        long = build_project(tmp_path / "largo", [FakeClip("a1", tone(70.0, 0))], master="a1").root
        assert _view(long, capsys, "a1", "0", "60s")[0] == 0
        code, doc, _ = _view(long, capsys, "a1", "0", "1801")
        assert code == 2 and "60 s" in doc["error"]["message"]

    def test_view_command_the_end_may_be_the_last_frame_of_the_audio(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert _view(root, capsys, "a1", "0", "240")[0] == 0  # 8 s = 240 frames
        code, doc, _ = _view(root, capsys, "a1", "0", "241")
        assert code == 2 and "pasa del final del audio" in doc["error"]["message"]

    def test_view_command_the_end_is_checked_against_the_wav16_not_the_inventory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # the container claimed 1 s but the wav16 holds 8 s: 5 s are there to look at
        lying = build_project(
            tmp_path / "miente", [FakeClip("a1", LAYOUT, declared_ms=1000)], master="a1"
        ).root
        assert _view(lying, capsys, "a1", "0", "5s")[0] == 0

    @pytest.mark.parametrize(
        ("args", "text"),
        [
            (["z9", "0", "2s"], "no existe el clip"),
            (["a1", "60", "60"], "el fin tiene que ir después del inicio"),
            (["a1", "60", "59"], "el fin tiene que ir después del inicio"),
            (["a1", "0", "61s"], "pasa de 60 s"),
            (["a1", "x", "2s"], "no entiendo el tiempo"),
            (["a1", "0", "1:75"], "menos de 60"),
        ],
    )
    def test_view_command_a_window_that_makes_no_sense_is_exit_2(
        self, root: Path, capsys: pytest.CaptureFixture[str], args: list[str], text: str
    ) -> None:
        code, doc, _ = _view(root, capsys, *args)
        assert code == 2 and text in doc["error"]["message"]


class TestOutput:
    def test_view_command_the_default_png_is_in_the_view_folder_with_the_frames_in_its_name(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, doc, _ = _view(root, capsys, "a1", "1s", "3s")
        assert code == 0 and doc["png"] == ".kcut/view/a1_30-90.png"
        with Image.open(root / doc["png"]) as image:
            assert image.size == (2400, 420) and image.format == "PNG"
        assert doc["notice"] == "sin transcripcion" and doc["words"] == 0

    def test_view_command_out_goes_where_asked(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, doc, _ = _view(root, capsys, "a1", "1s", "3s", "--out", "edit/mira/uno.png")
        assert code == 0 and doc["png"] == "edit/mira/uno.png"
        assert (root / "edit" / "mira" / "uno.png").is_file()

    def test_view_command_a_second_run_replaces_the_picture_and_leaves_no_tmp(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert _view(root, capsys, "a1", "1s", "3s")[0] == 0
        assert _view(root, capsys, "a1", "1s", "3s")[0] == 0
        assert sorted(p.name for p in (root / ".kcut" / "view").iterdir()) == ["a1_30-90.png"]

    def test_view_command_human_mode_prints_one_ok_line_with_the_path(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        capsys.readouterr()
        assert cli.main(["view", "a1", "1s", "3s", "--project", str(root)]) == 0
        assert capsys.readouterr().out == "[OK] .kcut/view/a1_30-90.png\n"

    def test_view_command_an_out_that_is_not_png_writes_nothing(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _, _ = _view(root, capsys, "a1", "1s", "3s", "--out", "edit/x.txt")
        assert code == 2 and not (root / "edit" / "x.txt").exists()


class TestMissingPieces:
    def test_view_command_a_missing_wav16_is_exit_3_and_says_ingest(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (root / ".kcut" / "wav16" / "a1_cam.wav").unlink()
        code, doc, _ = _view(root, capsys, "a1", "1s", "3s")
        assert code == 3 and doc["error"]["message"] == "falta el wav16 de a1; corre kcut ingest"

    def test_view_command_a_clip_without_video_cannot_have_a_filmstrip(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, doc, _ = _view(root, capsys, "a1", "1s", "3s", "--filmstrip", "3")
        assert code == 2 and doc["error"]["message"] == "a1 no tiene video"
        assert _view(root, capsys, "a1", "1s", "3s", "--filmstrip", "0")[0] == 0

    def test_view_command_a_transcript_of_another_audio_stops_it_like_pack_does(
        self, root: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_engine(monkeypatch, {"a1": [("hola", 1000, 1400, 0.9)]})
        assert cli.main(["transcribe", "--project", str(root)]) == 0
        longer = np.concatenate([LAYOUT, tone(0.5)])
        write_wav_s16_mono(root / ".kcut" / "wav16" / "a1_cam.wav", longer, SR)
        code, doc, _ = _view(root, capsys, "a1", "1s", "3s")
        assert code == 1 and doc["error"]["kind"] == "CheckFailed"
        assert "es de otro audio; corre kcut transcribe" in doc["error"]["message"]
