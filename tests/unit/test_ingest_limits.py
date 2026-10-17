"""Resource limits of ingest: blockwise peak, long-duration flags, per-job timeouts."""

from pathlib import Path

import numpy as np
import pytest

from kcut import proc
from kcut.audio.wavio import read_wav_s16_mono, wav_peak, write_wav_s16_mono
from kcut.config.load import parse_config
from kcut.config.model import IngestSection
from kcut.ingest import examine as examine_module
from kcut.ingest import workfiles
from kcut.ingest.examine import FFPROBE_TIMEOUT_S, dbfs, duration_flags, examine
from kcut.ingest.inventory import Clip, ClipAudio, Notice, WorkFiles
from kcut.ingest.probe import AudioInfo, MediaInfo
from kcut.ingest.scan import Found
from kcut.paths import Layout
from kcut.proc import RunResult
from kcut.project import Project
from tests.unit.media_fakes import make_video

HOUR_MS = 3_600_000


@pytest.fixture
def project(tmp_path: Path) -> Project:
    root = tmp_path / "proyecto ñandú"
    (root / "crudo").mkdir(parents=True)
    (root / ".kcut").mkdir()
    (root / "crudo" / "a.mp4").write_bytes(b"x")
    return Project(root=root, config=parse_config("", default_name="x"), layout=Layout(root))


def _clip(duration_ms: int, with_audio: bool = True) -> Clip:
    audio = ClipAudio("aac", 44100, 1, 0, 1, -3.0, False) if with_audio else None
    work = WorkFiles(None, None, 540, 960)
    return Clip(
        "a1",
        "crudo/a.mp4",
        "a",
        "video_voz",
        "sha256:aaaaaaaa",
        1,
        duration_ms,
        30,
        make_video(),
        audio,
        None,
        work,
        (),
    )


class TestBlockwisePeak:
    def test_the_blockwise_peak_equals_numpy_over_the_whole_file(self, tmp_path: Path) -> None:
        rng = np.random.default_rng(11)
        x = (rng.standard_normal(2_500_000) * 0.1).astype(np.float32)
        x[1_999_999] = 0.7311
        write_wav_s16_mono(tmp_path / "a.wav", x, 16000)
        whole, _ = read_wav_s16_mono(tmp_path / "a.wav")
        expected = float(np.max(np.abs(whole)))
        assert wav_peak(tmp_path / "a.wav") == expected  # 3 blocks of 1 048 576 frames
        assert dbfs(wav_peak(tmp_path / "a.wav")) == dbfs(expected)

    def test_the_peak_in_the_last_partial_block_is_seen(self, tmp_path: Path) -> None:
        x = np.zeros(1_048_576 + 5, dtype=np.float32)
        x[-1] = -0.5
        write_wav_s16_mono(tmp_path / "a.wav", x, 16000)
        assert wav_peak(tmp_path / "a.wav") == pytest.approx(0.5, abs=1 / 32768)

    @pytest.mark.parametrize(
        ("linear", "db"), [(1.0, 0.0), (0.5, -6.0), (0.001, -60.0), (0.0, -120.0)]
    )
    def test_dbfs_has_one_decimal_and_a_floor(self, linear: float, db: float) -> None:
        assert dbfs(linear) == db

    def test_dbfs_floor_for_a_denormal_peak(self) -> None:
        assert dbfs(1e-12) == -120.0


class TestDurationFlags:
    def test_defaults_are_3_and_12_hours(self) -> None:
        cfg = parse_config("", default_name="x").ingest
        assert duration_flags(3 * HOUR_MS, cfg) == ()
        assert duration_flags(3 * HOUR_MS + 1, cfg) == ("long_duration",)
        assert duration_flags(12 * HOUR_MS, cfg) == ("long_duration",)
        assert duration_flags(12 * HOUR_MS + 1, cfg) == ("long_duration", "too_long")

    def test_thresholds_come_from_the_config(self) -> None:
        cfg = IngestSection(warn_duration_h=0.5, max_duration_h=1.0)
        assert duration_flags(30 * 60 * 1000, cfg) == ()
        assert duration_flags(30 * 60 * 1000 + 1, cfg) == ("long_duration",)
        assert duration_flags(60 * 60 * 1000 + 1, cfg) == ("long_duration", "too_long")

    def test_a_normal_clip_has_no_flags(self) -> None:
        cfg = parse_config("", default_name="x").ingest
        assert duration_flags(131_233, cfg) == ()


def _found(project: Project, duration_ms: int, audio: bool = True) -> Found:
    path = project.root / "crudo" / "a.mp4"
    item = Found(rel="crudo/a.mp4", path=path, size=1, hash="sha256:" + "a" * 64)
    item.info = MediaInfo(
        duration_ms, 1, "mov", make_video(), AudioInfo("aac", 44100, 1, 0, 1) if audio else None
    )
    return item


class TestSimulatedDurations:
    @pytest.fixture(autouse=True)
    def _fake_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.staged: list[str] = []

        def fake_probe(path: Path, log: Path) -> MediaInfo:
            return self.next_info

        def fake_stage(project: Project, rel: str, *_a: object, **_k: object) -> Path:
            self.staged.append(rel)
            wav = project.layout.wav16 / "stage-x.wav"
            write_wav_s16_mono(wav, np.full(1600, 0.25, dtype=np.float32), 16000)
            return wav

        monkeypatch.setattr(examine_module, "_probe", fake_probe)
        monkeypatch.setattr(workfiles, "stage_wav16", fake_stage)

    def _run(self, project: Project, duration_ms: int) -> Found:
        self.next_info = MediaInfo(
            duration_ms, 1, "mov", make_video(), AudioInfo("aac", 1, 1, 0, 1)
        )
        item = Found(rel="crudo/a.mp4", path=project.root / "crudo" / "a.mp4", size=1, hash="h" * 8)
        examine(project, item, {}, project.root / "log.txt", [])
        return item

    def test_long_duration_is_flagged_and_still_processed(self, project: Project) -> None:
        item = self._run(project, 4 * HOUR_MS)
        assert item.flags == ("long_duration",)
        assert self.staged == ["crudo/a.mp4"]
        assert item.peak == dbfs(0.25)

    def test_too_long_is_registered_but_not_processed(self, project: Project) -> None:
        item = self._run(project, 13 * HOUR_MS)
        assert item.flags == ("long_duration", "too_long")
        assert self.staged == []
        assert item.wav is None and item.peak is None
        assert item.info is not None and not item.failed

    def test_a_normal_clip_gets_no_flags(self, project: Project) -> None:
        item = self._run(project, 60_000)
        assert item.flags == ()
        assert self.staged == ["crudo/a.mp4"]


class TestJobTimeouts:
    def test_the_formula_is_10x_the_duration_plus_60_seconds(self) -> None:
        assert workfiles.job_timeout_s(0) == 60.0
        assert workfiles.job_timeout_s(20_000) == 260.0
        assert workfiles.job_timeout_s(131_233) == pytest.approx(1372.33)

    def test_ffprobe_gets_60_seconds(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        seen: list[float | None] = []

        def fake_run(args: list[str], **kwargs: object) -> RunResult:
            seen.append(kwargs.get("timeout_s"))  # type: ignore[arg-type]
            return RunResult(0, b'{"format": {"duration": "1.0"}, "streams": []}', "")

        monkeypatch.setattr(proc, "run", fake_run)
        examine_module._probe(tmp_path / "a.mp4", tmp_path / "log.txt")
        assert seen == [60.0] == [FFPROBE_TIMEOUT_S]

    @pytest.fixture
    def recorded(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, float | None]]:
        calls: list[tuple[str, float | None]] = []

        def fake_run(args: list[str], **kwargs: object) -> RunResult:
            calls.append((Path(args[-1]).suffix, kwargs.get("timeout_s")))  # type: ignore[arg-type]
            Path(args[-1]).write_bytes(b"fake")
            return RunResult(0, b"", "")

        monkeypatch.setattr(proc, "run", fake_run)
        return calls

    def test_every_ffmpeg_job_carries_its_timeout(
        self, project: Project, recorded: list[tuple[str, float | None]]
    ) -> None:
        clip = _clip(20_000)
        workfiles.ensure_wav16(project, clip)
        workfiles.ensure_wav48(project, clip)
        workfiles.ensure_proxy(project, clip)
        assert recorded == [(".wav", 260.0), (".wav", 260.0), (".mp4", 260.0)]

    def test_staging_a_wav16_uses_the_probed_duration(
        self, project: Project, recorded: list[tuple[str, float | None]]
    ) -> None:
        workfiles.stage_wav16(project, "crudo/a.mp4", "sha256:" + "b" * 64, 100_000, None)
        assert recorded == [(".wav", 1060.0)]

    def test_a_cached_file_runs_nothing(
        self, project: Project, recorded: list[tuple[str, float | None]]
    ) -> None:
        clip = _clip(20_000)
        workfiles.ensure_wav16(project, clip)
        workfiles.ensure_wav16(project, clip)
        assert len(recorded) == 1


def test_notices_are_plain_values() -> None:
    assert Notice("cache_rebuilt", "x") == Notice("cache_rebuilt", "x")


def _small_limit_project(tmp_path: Path, max_h: float) -> Project:
    root = tmp_path / "proyecto ñandú"
    (root / "crudo").mkdir(parents=True)
    (root / ".kcut" / "wav16").mkdir(parents=True)
    (root / "crudo" / "a.mp4").write_bytes(b"x")
    text = f"[ingest]\nwarn_duration_h = 0.1\nmax_duration_h = {max_h}\n"
    return Project(root, parse_config(text, default_name="x"), Layout(root))


class TestRealLength:
    """The declared duration is not trusted: ffmpeg is capped and the real wav16 is re-measured."""

    def test_real_length_cap_is_in_the_job_args(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _small_limit_project(tmp_path, 0.5)
        calls: list[list[str]] = []

        def fake_run(args: list[str], **_kwargs: object) -> RunResult:
            calls.append(args)
            Path(args[-1]).write_bytes(b"fake")
            return RunResult(0, b"", "")

        monkeypatch.setattr(proc, "run", fake_run)
        clip = _clip(20_000)
        workfiles.ensure_wav16(project, clip)
        workfiles.ensure_wav48(project, clip)
        workfiles.ensure_proxy(project, clip)
        assert len(calls) == 3
        for args in calls:
            assert args[args.index("-t") + 1] == "1860"  # 0.5 h * 3600 + 60 s
            assert args.index("-t") < args.index("-map_metadata")

    def test_real_length_cap_follows_the_configured_maximum(self, tmp_path: Path) -> None:
        assert workfiles.max_job_seconds(_small_limit_project(tmp_path, 12.0)) == 43260.0
        assert workfiles.max_job_seconds(_small_limit_project(tmp_path / "otro", 0.1)) == 420.0

    def _examine(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        max_h: float,
        real_s: int,
        value: float,
    ) -> tuple[Found, Path]:
        """Examine a clip that declares 1 s but whose staged wav16 lasts `real_s` seconds."""
        project = _small_limit_project(tmp_path, max_h)
        wav = project.layout.wav16 / "stage-x.wav"

        def fake_stage(*_a: object, **_k: object) -> Path:
            write_wav_s16_mono(wav, np.full(real_s * 16000, value, dtype=np.float32), 16000)
            workfiles.sidecar_path(wav).write_text("{}", encoding="utf-8")
            return wav

        info = MediaInfo(1000, 1, "mov", make_video(), AudioInfo("aac", 1, 1, 0, 1))
        monkeypatch.setattr(workfiles, "stage_wav16", fake_stage)
        monkeypatch.setattr(examine_module, "_probe", lambda path, log: info)
        item = Found(rel="crudo/a.mp4", path=project.root / "crudo" / "a.mp4", size=1, hash="h" * 8)
        examine(project, item, {}, project.root / "log.txt", [])
        return item, wav

    def test_real_length_too_long_deletes_the_wav16(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The clip says 1 s; its audio is 400 s; the limit is 0.1 h = 360 s."""
        item, wav = self._examine(tmp_path, monkeypatch, 0.1, 400, 0.0)
        assert item.flags == ("long_duration", "too_long")
        assert item.wav is None and item.peak is None
        assert not item.failed and not item.wav_failed
        assert not wav.exists() and not workfiles.sidecar_path(wav).exists()

    def test_real_length_inside_the_limit_keeps_the_wav16(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        item, wav = self._examine(tmp_path, monkeypatch, 0.1, 10, 0.25)
        assert item.flags == ()
        assert item.wav == wav and wav.is_file()
        assert item.peak == dbfs(0.25)

    def test_real_length_over_the_warning_only_adds_long_duration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        item, wav = self._examine(tmp_path, monkeypatch, 0.2, 400, 0.0)  # warn 360 s, max 720 s
        assert item.flags == ("long_duration",)
        assert item.wav == wav and wav.is_file()
