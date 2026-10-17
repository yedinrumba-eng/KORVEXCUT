"""`kcut ingest`: audio recorders, silent video, unreadable files, failures, missing tools."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from kcut import cli, proc
from kcut.errors import ToolError
from kcut.ingest import workfiles
from tests.fixtures.synth_media import (
    has_flite,
    make_audio_track,
    make_silent_video,
    make_unrelated_audio,
)
from tests.integration.ingest_helpers import edit_toml, ingest, inventory

pytestmark = pytest.mark.ffmpeg


class TestExtraClasses:
    @pytest.mark.slow
    def test_an_audio_recorder_is_synced_as_s1(self, two_cameras: Path) -> None:
        make_audio_track(two_cameras / "crudo" / "grabadora.m4a", 1.0, has_flite())
        assert ingest(two_cameras)[0] == 0
        inv = inventory(two_cameras)
        s1 = inv.by_id("s1")
        assert s1 is not None and s1.clip_class == "audio"
        assert s1.video is None and s1.work is not None
        assert s1.work.proxy is None and s1.work.wav16 == ".kcut/wav16/s1_grabadora.wav"
        member = next(m for m in inv.sync.members if m.id == "s1")
        assert 999 <= member.offset_ms <= 1001

    @pytest.mark.slow
    def test_unrelated_audio_is_rejected_and_flagged(self, two_cameras: Path) -> None:
        make_unrelated_audio(two_cameras / "crudo" / "ruido.m4a")
        assert ingest(two_cameras)[0] == 0
        inv = inventory(two_cameras)
        assert [r.id for r in inv.sync.rejected] == ["s1"]
        assert inv.sync.rejected[0].reason
        ruido = inv.by_id("s1")
        assert ruido is not None and ruido.warnings == ("sync_rejected",)
        assert [m.id for m in inv.sync.members] == ["a2"]

    @pytest.mark.slow
    def test_a_video_with_silent_audio_is_video_mudo(self, blank: Path) -> None:
        make_silent_video(blank / "crudo" / "silencio.mp4")
        assert ingest(blank)[0] == 0
        clip = inventory(blank).by_id("b1")
        assert clip is not None and clip.audio is not None
        assert clip.clip_class == "video_mudo"
        assert (clip.audio.silent, clip.audio.peak_dbfs) == (True, -120.0)
        assert clip.warnings == ("silent_audio",)
        assert inventory(blank).sync.master is None

    @pytest.mark.slow
    def test_a_single_camera_has_a_master_and_no_members(self, two_cameras: Path) -> None:
        (two_cameras / "crudo" / "cam b.mov").unlink()
        assert ingest(two_cameras)[0] == 0
        sync = inventory(two_cameras).sync
        assert (sync.master, sync.members, sync.rejected) == ("a1", (), ())


class TestBadInput:
    @pytest.mark.slow
    def test_a_broken_video_is_unknown_and_the_run_continues(self, two_cameras: Path) -> None:
        (two_cameras / "crudo" / "roto.mp4").write_bytes(b"esto no es un video" * 50)
        code, doc = ingest(two_cameras)
        assert code == 0
        inv = inventory(two_cameras)
        broken = inv.by_id("u1")
        assert broken is not None
        assert (broken.clip_class, broken.warnings) == ("desconocido", ("probe_failed",))
        assert broken.video is None and broken.work is None
        assert {"id": "u1", "code": "probe_failed"} in doc["warnings"]  # type: ignore[operator]
        assert inv.by_id("a1") is not None

    @pytest.mark.slow
    def test_an_unreadable_image_is_unknown(self, blank: Path) -> None:
        (blank / "crudo" / "falsa.png").write_bytes(b"no soy un png")
        assert ingest(blank)[0] == 0
        clip = inventory(blank).by_id("u1")
        assert clip is not None and clip.warnings == ("probe_failed",)

    @pytest.mark.slow
    def test_hidden_files_and_folders_are_skipped(self, blank: Path) -> None:
        (blank / "crudo" / ".oculto.txt").write_text("x", encoding="utf-8")
        (blank / "crudo" / ".carpeta").mkdir()
        (blank / "crudo" / ".carpeta" / "nota.txt").write_text("x", encoding="utf-8")
        (blank / "crudo" / "visible.txt").write_text("x", encoding="utf-8")
        assert ingest(blank)[0] == 0
        assert [c.file for c in inventory(blank).clips] == ["crudo/visible.txt"]

    @pytest.mark.slow
    def test_nested_folders_are_scanned(self, blank: Path) -> None:
        (blank / "crudo" / "dia 1" / "cámara").mkdir(parents=True)
        (blank / "crudo" / "dia 1" / "cámara" / "nota.txt").write_text("x", encoding="utf-8")
        assert ingest(blank)[0] == 0
        assert [c.file for c in inventory(blank).clips] == ["crudo/dia 1/cámara/nota.txt"]

    @pytest.mark.slow
    def test_empty_crudo(self, blank: Path) -> None:
        code, doc = ingest(blank)
        assert code == 0
        assert (doc["clips"], doc["by_class"]) == (0, {})
        assert inventory(blank).clips == ()

    @pytest.mark.slow
    def test_a_missing_crudo_folder_is_a_project_error(self, blank: Path) -> None:
        shutil.rmtree(blank / "crudo")
        assert ingest(blank)[0] == 3

    @pytest.mark.slow
    def test_a_corrupt_previous_inventory_is_rebuilt(self, two_cameras: Path) -> None:
        ingest(two_cameras)
        (two_cameras / ".kcut" / "inventory.json").write_text("{ roto", encoding="utf-8")
        assert ingest(two_cameras)[0] == 0
        assert [c.id for c in inventory(two_cameras).clips] == ["a1", "a2"]


class TestProxyFailure:
    @pytest.mark.slow
    def test_a_failed_proxy_saves_the_inventory_with_null_and_exits_4(
        self,
        two_cameras: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        real = workfiles.ensure_proxy

        def flaky(
            project: object, clip: object, log: Path | None = None, notices: object = None
        ) -> Path:
            if getattr(clip, "id", "") == "a1":
                raise ToolError("ffmpeg se cayo")
            return real(project, clip, log, notices)  # type: ignore[arg-type]

        monkeypatch.setattr(workfiles, "ensure_proxy", flaky)
        assert cli.main(["ingest", "--project", str(two_cameras), "--json"]) == 4
        doc = json.loads(capsys.readouterr().out)
        assert doc["ok"] is False
        assert doc["error"]["kind"] == "ToolError"
        assert "a1" in doc["error"]["message"]
        inv = inventory(two_cameras)
        a1, a2 = inv.by_id("a1"), inv.by_id("a2")
        assert a1 is not None and a1.work is not None and a1.work.proxy is None
        assert a2 is not None and a2.work is not None
        assert a2.work.proxy == ".kcut/proxy/a2_cam-b.mp4"
        assert inv.sync.members[0].id == "a2"


class TestMissingTools:
    def test_a_missing_ffprobe_is_exit_7_and_not_a_probe_failure(
        self, blank: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (blank / "crudo" / "algo.mp4").write_bytes(b"x" * 100)
        monkeypatch.setenv("KCUT_FFPROBE", str(tmp_path / "no-existe" / "ffprobe.exe"))
        assert cli.main(["ingest", "--project", str(blank), "--json"]) == 7
        assert not (blank / ".kcut" / "inventory.json").exists()


class TestDisplayGeometryAndFps:
    @pytest.fixture
    def screen(self, blank: Path, synth_project: tuple[Path, object]) -> Path:
        shutil.copy2(synth_project[0] / "crudo" / "pantalla.mp4", blank / "crudo" / "pantalla.mp4")
        return blank

    @pytest.mark.slow
    def test_a_rotated_clip_gets_a_proxy_of_its_displayed_size(
        self, screen: Path, tmp_path: Path
    ) -> None:
        rotated = screen / "crudo" / "girado.mp4"
        flipped = subprocess.run(
            [
                str(proc.tool_path("ffmpeg")),
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-display_rotation",
                "90",
                "-i",
                str(screen / "crudo" / "pantalla.mp4"),
                "-c",
                "copy",
                str(rotated),
            ],
            capture_output=True,
            check=False,
        )
        assert flipped.returncode == 0, flipped.stderr
        (screen / "crudo" / "pantalla.mp4").unlink()
        assert ingest(screen, proxies=True)[0] == 0
        clip = inventory(screen).by_id("b1")
        assert clip is not None and clip.video is not None and clip.work is not None
        assert (clip.video.w, clip.video.h) == (1894, 866)
        assert (clip.video.display_w, clip.video.display_h) == (866, 1894)
        assert abs(clip.video.rotation) == 90
        assert clip.warnings == ("rotation",)
        assert (clip.work.proxy_w, clip.work.proxy_h) == (438, 960)
        assert clip.work.proxy is not None
        shown = subprocess.run(
            [
                str(proc.tool_path("ffprobe")),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                str(screen / clip.work.proxy),
            ],
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        assert shown.stdout.strip() == "438,960"

    @pytest.mark.slow
    def test_the_project_fps_drives_frames_and_the_proxy_rate(self, screen: Path) -> None:
        edit_toml(screen, "fps = 30", "fps = 25")
        assert ingest(screen, proxies=True)[0] == 0
        clip = inventory(screen).by_id("b1")
        assert clip is not None and clip.work is not None and clip.work.proxy is not None
        assert (inventory(screen).fps, clip.duration_ms, clip.frames) == (25, 8000, 200)
        probed = subprocess.run(
            [
                str(proc.tool_path("ffprobe")),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate,nb_frames",
                "-of",
                "csv=p=0",
                str(screen / clip.work.proxy),
            ],
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        assert probed.stdout.strip().split(",") == ["25/1", "200"]
