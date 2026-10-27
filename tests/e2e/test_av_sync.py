"""Picture and sound meet, from end to end (spec S1.5b rows 7 and 14).

The synthetic cameras flash white and beep at the same real instants, so after the cut the flashes
have to be at the output frames the EDL puts them (60 and 150) and the beeps at the seconds it puts
them (2.0 and 5.0): that proves the shift between cameras, the mezzanines and the voice track add up
to the sample. Row 14 does the same with a clip whose video starts half a second after its audio.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut.audio.wavio import read_f32
from tests.conftest import run_kcut
from tests.fixtures.av_probe import (
    beep_onsets,
    decode_audio,
    flash_frames,
    gray_per_frame,
)
from tests.fixtures.synth_edl import EdlTruth
from tests.fixtures.synth_late_video import (
    BEEP_CLOCK_S,
    FLASH_CLOCK_FRAME,
    make_late_video,
)

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow, pytest.mark.e2e]
FPS = 30
TRUTH = EdlTruth()


def _frame_of(seconds: float) -> float:
    return seconds * FPS


class TestExample:
    """Row 7: flashes at the output frames {60, 150} and beeps at {2.000, 5.000} s, to a frame."""

    def test_av_sync_the_flashes_are_at_the_output_frames_of_the_edl(
        self, rendered_example: tuple[Path, dict[str, Any]]
    ) -> None:
        root, _ = rendered_example
        flashes = flash_frames(gray_per_frame(root / ".kcut/build/v1/video.mp4", TRUTH.frames))
        assert len(flashes) >= 2
        for wanted in TRUTH.flash_out_f:
            assert any(abs(found - wanted) <= 1 for found in flashes), (wanted, flashes)
        assert all(any(abs(f - w) <= 1 for w in TRUTH.flash_out_f) for f in flashes), flashes

    def test_av_sync_the_beeps_are_at_the_seconds_of_the_edl_in_the_voice_track(
        self, rendered_example: tuple[Path, dict[str, Any]]
    ) -> None:
        root, _ = rendered_example
        onsets = beep_onsets(read_f32(root / ".kcut/build/v1/voice_raw.f32"))
        assert len(onsets) == 2, onsets
        for found, wanted in zip(onsets, TRUTH.beep_out_s, strict=True):
            assert abs(found - wanted) * FPS <= 1, (found, wanted)

    def test_av_sync_each_flash_has_its_beep_at_the_same_frame(
        self, rendered_example: tuple[Path, dict[str, Any]]
    ) -> None:
        """The flash of a camera and the beep of the voice are the same event in the room: after
        the cut they are still at the same frame, whichever camera shows them."""
        root, _ = rendered_example
        flashes = flash_frames(gray_per_frame(root / ".kcut/build/v1/video.mp4", TRUTH.frames))
        onsets = beep_onsets(read_f32(root / ".kcut/build/v1/voice_raw.f32"))
        for flash, beep in zip(sorted(flashes)[:: len(flashes) // 2 or 1], onsets, strict=False):
            assert abs(flash - _frame_of(beep)) <= 1, (flash, beep)

    def test_av_sync_the_review_mp4_keeps_the_same_alignment(
        self, rendered_example: tuple[Path, dict[str, Any]]
    ) -> None:
        """The AAC in `render.mp4` has an encoder delay: the file says so, so the decoded sound
        is still where it was (to a frame)."""
        root, _ = rendered_example
        decoded = beep_onsets(decode_audio(root / ".kcut/build/v1/render.mp4"))
        assert len(decoded) == 2, decoded
        for found, wanted in zip(decoded, TRUTH.beep_out_s, strict=True):
            assert abs(found - wanted) * FPS <= 1, (found, wanted)


@pytest.fixture(scope="module")
def late_render(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A project with one clip whose video starts 0.5 s after its audio (S1.4-14), plus a beep at
    the instant of its flash, and an EDL: voice 30 to 75 and a synchronized camera over it."""
    root = tmp_path_factory.mktemp("late-av") / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    make_late_video(root / "crudo" / "tarde.mov")
    done = run_kcut("ingest", "--project", str(root), "--json")
    assert done.returncode == 0, done.stderr
    inventory = json.loads((root / ".kcut" / "inventory.json").read_text(encoding="utf-8"))
    (clip,) = [c for c in inventory["clips"] if c["id"] == "a1"]
    document = {
        "schema": "kcut.edl/1",
        "version": 1,
        "fps": FPS,
        "output": {"w": 1080, "h": 1920},
        "frames": 45,
        "look": "neutro",
        "sources": {"a1": {"qhash": clip["qhash"]}},
        "clips": [{"kind": "voice", "at_f": 0, "src": "a1", "in_f": 30, "out_f": 75, "why": "x"}],
        "spans": [{"kind": "cam", "at_f": 0, "dur_f": 45, "src": "a1"}],
    }
    (root / "edit").mkdir(exist_ok=True)
    (root / "edit" / "edl-v1.json").write_text(json.dumps(document), encoding="utf-8")
    strategy = "---\nvideo: tarde\naprobado: si\n---\n# Estrategia\n"
    (root / "edit" / "estrategia.md").write_text(strategy, encoding="utf-8", newline="\n")
    rendered = run_kcut("render", "--no-graphics", "--json", "--project", str(root))
    assert rendered.returncode == 0, rendered.stderr
    return root


class TestVideoStartOffset:
    """Row 14 (T5): one clock. The video of the clip starts 0.5 s late, and the flash and the beep
    that are the same instant of the source land on the same output frame."""

    def test_av_sync_video_start_offset_the_flash_and_the_beep_meet_in_render_mp4(
        self, late_render: Path
    ) -> None:
        render = late_render / ".kcut/build/v1/render.mp4"
        flashes = flash_frames(gray_per_frame(render, 45))
        beeps = beep_onsets(decode_audio(render))
        assert len(flashes) == 1 and len(beeps) == 1, (flashes, beeps)
        assert abs(flashes[0] - _frame_of(beeps[0])) <= 1, (flashes, beeps)

    def test_av_sync_video_start_offset_both_are_where_the_source_clock_puts_them(
        self, late_render: Path
    ) -> None:
        """The flash is frame 45 of the clock and the clip is cut from frame 30: output frame 15."""
        render = late_render / ".kcut/build/v1/render.mp4"
        (flash,) = flash_frames(gray_per_frame(render, 45))
        (beep,) = beep_onsets(decode_audio(render))
        assert abs(flash - (FLASH_CLOCK_FRAME - 30)) <= 1
        assert abs(beep - (BEEP_CLOCK_S - 30 / FPS)) * FPS <= 1

    def test_av_sync_video_start_offset_the_voice_track_has_the_beep_at_the_same_place(
        self, late_render: Path
    ) -> None:
        (beep,) = beep_onsets(read_f32(late_render / ".kcut/build/v1/voice_raw.f32"))
        assert abs(beep - 0.5) * FPS <= 1
