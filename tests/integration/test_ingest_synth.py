"""`kcut ingest` on the synthetic project: ids, classes, sync, proxies, idempotency."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.ff.color import CHAIN_VERSION
from kcut.ingest.inventory import Clip, Inventory, load_inventory
from kcut.ingest.sync import HOP_MS
from kcut.ingest.workfiles import PROXY_PARAMS_VERSION
from tests.conftest import run_kcut
from tests.fixtures.synth_media import MediaTruth

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]

Project = tuple[Path, MediaTruth]


def _inventory(project: Project) -> Inventory:
    return load_inventory(project[0] / ".kcut" / "inventory.json")


def _clip(project: Project, clip_id: str) -> Clip:
    clip = _inventory(project).by_id(clip_id)
    assert clip is not None, clip_id
    return clip


def _ffprobe_stream(path: Path, kind: str = "v:0") -> dict[str, Any]:
    result = subprocess.run(
        [
            str(proc.tool_path("ffprobe")),
            "-v",
            "error",
            "-select_streams",
            kind,
            "-count_frames",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    return dict(json.loads(result.stdout)["streams"][0])


class TestIdsAndClasses:
    def test_ids_and_classes(self, synth_project: Project) -> None:
        inv = _inventory(synth_project)
        found = {c.file: (c.id, c.clip_class) for c in inv.clips}
        assert found == {
            "crudo/brief.txt": ("d1", "doc"),
            "crudo/cam a.mp4": ("a1", "video_voz"),
            "crudo/cam b.mov": ("a2", "video_voz"),
            "crudo/foto.png": ("i1", "imagen"),
            "crudo/pantalla.mp4": ("b1", "video_mudo"),
        }

    def test_the_second_camera_is_hlg(self, synth_project: Project) -> None:
        a2 = _clip(synth_project, "a2")
        assert a2.video is not None
        assert a2.video.hdr == "hlg"
        assert (a2.video.pix_fmt, a2.video.bit_depth) == ("yuv420p10le", 10)
        assert a2.video.color_primaries == "bt2020"
        assert a2.warnings == ("hdr",)

    def test_sdr_cameras_have_no_warnings(self, synth_project: Project) -> None:
        for clip_id in ("a1", "b1", "i1", "d1"):
            assert _clip(synth_project, clip_id).warnings == ()

    def test_video_facts(self, synth_project: Project) -> None:
        a1, b1 = _clip(synth_project, "a1"), _clip(synth_project, "b1")
        assert a1.video is not None and b1.video is not None
        assert (a1.video.w, a1.video.h, a1.video.vfr, a1.video.hdr) == (1440, 2560, False, None)
        assert (b1.video.w, b1.video.h) == (1894, 866)
        assert (a1.duration_ms, a1.frames) == (12000, 360)
        assert (b1.duration_ms, b1.frames) == (8000, 240)
        assert b1.audio is None

    def test_audio_facts(self, synth_project: Project) -> None:
        a1, a2 = _clip(synth_project, "a1"), _clip(synth_project, "a2")
        assert a1.audio is not None and a2.audio is not None
        assert (a1.audio.sample_rate, a2.audio.sample_rate) == (44100, 48000)
        assert not a1.audio.silent and not a2.audio.silent
        assert -20.0 < a1.audio.peak_dbfs <= 0.0

    def test_image_and_doc(self, synth_project: Project) -> None:
        i1, d1 = _clip(synth_project, "i1"), _clip(synth_project, "d1")
        assert i1.image is not None
        assert (i1.image.w, i1.image.h, i1.image.has_alpha) == (800, 600, True)
        assert i1.frames is None and i1.video is None and i1.work is None
        assert d1.size_bytes == len("brief de prueba")

    def test_the_inventory_never_holds_raw_ffprobe_data(self, synth_project: Project) -> None:
        text = (synth_project[0] / ".kcut" / "inventory.json").read_text(encoding="utf-8")
        for raw_key in ('"tags"', '"side_data_list"', '"codec_long_name"', '"format_name"'):
            assert raw_key not in text
        assert json.loads(text)["schema"] == "kcut.inventory/1"


class TestSync:
    def test_the_second_camera_is_found_1200_ms_after_the_first(
        self, synth_project: Project
    ) -> None:
        sync = _inventory(synth_project).sync
        assert sync.master == "a1"
        (member,) = sync.members
        assert member.id == "a2"
        assert 1199 <= member.offset_ms <= 1201
        assert member.method == "envelope+raw"
        assert member.score >= 0.35
        assert member.ratio is not None and member.ratio >= 1.5
        assert sync.rejected == ()

    def test_synthetic_clips_are_too_short_to_measure_drift(self, synth_project: Project) -> None:
        (member,) = _inventory(synth_project).sync.members
        assert (member.drift_ms, member.drift_windows) == (None, 0)

    def test_offset_matches_the_truth_of_the_fixture(self, synth_project: Project) -> None:
        _, truth = synth_project
        (member,) = _inventory(synth_project).sync.members
        assert abs(member.offset_ms - truth.offset_b_ms) <= 1


class TestProxies:
    @pytest.mark.parametrize(
        ("clip_id", "size"), [("a1", (540, 960)), ("a2", (540, 960)), ("b1", (960, 438))]
    )
    def test_proxies_size_color_and_frames(
        self, synth_project: Project, clip_id: str, size: tuple[int, int]
    ) -> None:
        root = synth_project[0]
        clip = _clip(synth_project, clip_id)
        assert clip.work is not None and clip.work.proxy is not None
        assert (clip.work.proxy_w, clip.work.proxy_h) == size
        stream = _ffprobe_stream(root / clip.work.proxy)
        assert (stream["width"], stream["height"]) == size
        assert stream["pix_fmt"] == "yuv420p"
        assert stream["color_space"] == "bt709"
        assert stream["color_primaries"] == "bt709"
        assert stream["color_transfer"] == "bt709"
        assert stream["color_range"] == "tv"
        assert stream["r_frame_rate"] == "30/1"
        assert clip.frames is not None
        assert abs(int(stream["nb_read_frames"]) - clip.frames) <= 1

    def test_hdr_proxy_is_fully_tagged_bt709(self, synth_project: Project) -> None:
        clip = _clip(synth_project, "a2")
        assert clip.work is not None and clip.work.proxy is not None
        stream = _ffprobe_stream(synth_project[0] / clip.work.proxy)
        assert stream["color_transfer"] == "bt709"
        assert stream["color_primaries"] == "bt709"

    def test_the_proxy_has_no_audio(self, synth_project: Project) -> None:
        clip = _clip(synth_project, "a1")
        assert clip.work is not None and clip.work.proxy is not None
        result = subprocess.run(
            [
                str(proc.tool_path("ffprobe")),
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(synth_project[0] / clip.work.proxy),
            ],
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        assert result.stdout.strip() == ""

    def test_work_files_live_under_short_ascii_names(self, synth_project: Project) -> None:
        root = synth_project[0]
        names = sorted(p.name for p in (root / ".kcut" / "proxy").glob("*.mp4"))
        assert names == ["a1_cam-a.mp4", "a2_cam-b.mp4", "b1_pantalla.mp4"]
        assert sorted(p.name for p in (root / ".kcut" / "wav16").glob("*.wav")) == [
            "a1_cam-a.wav",
            "a2_cam-b.wav",
        ]

    def test_every_work_file_has_a_sidecar_with_its_qhash(self, synth_project: Project) -> None:
        root = synth_project[0]
        for clip in _inventory(synth_project).clips:
            if clip.work is None:
                continue
            for rel in (clip.work.proxy, clip.work.wav16):
                if rel is None:
                    continue
                sidecar = json.loads((root / (rel + ".json")).read_text(encoding="utf-8"))
                assert sidecar["qhash"] == clip.qhash
                assert "params" in sidecar

    def test_wav16_is_mono_16k_s16(self, synth_project: Project) -> None:
        clip = _clip(synth_project, "a2")
        assert clip.work is not None and clip.work.wav16 is not None
        stream = _ffprobe_stream(synth_project[0] / clip.work.wav16, "a:0")
        assert (stream["codec_name"], stream["sample_rate"], stream["channels"]) == (
            "pcm_s16le",
            "16000",
            1,
        )

    def test_no_mezz(self, synth_project: Project) -> None:
        mezz = synth_project[0] / ".kcut" / "mezz"
        assert not mezz.exists() or not any(mezz.iterdir())


class TestReingest:
    def test_reingest_stable(self, synth_project: Project) -> None:
        root = synth_project[0]
        first = _inventory(synth_project)
        watched = sorted((root / ".kcut" / "proxy").glob("*.mp4")) + sorted(
            (root / ".kcut" / "wav16").glob("*.wav")
        )
        mtimes = {p: p.stat().st_mtime_ns for p in watched}
        assert len(watched) == 5

        result = run_kcut("ingest", "--project", str(root), "--json")
        assert result.returncode == 0, result.stderr
        again = _inventory(synth_project)

        assert [(c.id, c.file) for c in again.clips] == [(c.id, c.file) for c in first.clips]
        assert {p: p.stat().st_mtime_ns for p in watched} == mtimes
        assert [c.work for c in again.clips] == [c.work for c in first.clips]
        assert again.sync == first.sync

    def test_resync_recomputes_the_same_answer(self, synth_project: Project) -> None:
        first = _inventory(synth_project).sync
        result = run_kcut("ingest", "--project", str(synth_project[0]), "--resync", "--json")
        assert result.returncode == 0, result.stderr
        again = _inventory(synth_project).sync
        assert again.master == first.master
        assert abs(again.members[0].offset_ms - first.members[0].offset_ms) <= 1

    def test_the_sync_search_resolution_is_5_ms(self) -> None:
        assert HOP_MS == 5


def _proxy_and_sidecar(project: Project, clip_id: str) -> tuple[Path, Path]:
    clip = _clip(project, clip_id)
    assert clip.work is not None and clip.work.proxy is not None
    proxy = project[0] / clip.work.proxy
    return proxy, Path(str(proxy) + ".json")


def test_proxy_cache_invalidated_by_version(synth_project: Project) -> None:
    """A proxy cached with an older parameter version is rebuilt on the next ingest (001.4)."""
    proxy, sidecar = _proxy_and_sidecar(synth_project, "b1")
    other, _ = _proxy_and_sidecar(synth_project, "a1")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["params"]["params_version"] == PROXY_PARAMS_VERSION
    assert data["params"]["chain_version"] == CHAIN_VERSION == "tm2"
    data["params"]["params_version"] = PROXY_PARAMS_VERSION - 1
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    stamp, other_stamp = proxy.stat().st_mtime_ns, other.stat().st_mtime_ns

    result = run_kcut("ingest", "--project", str(synth_project[0]), "--json")

    assert result.returncode == 0, result.stderr
    assert proxy.stat().st_mtime_ns != stamp
    assert other.stat().st_mtime_ns == other_stamp  # only the stale one is rebuilt
    again = json.loads(sidecar.read_text(encoding="utf-8"))
    assert again["params"]["params_version"] == PROXY_PARAMS_VERSION


def test_a_proxy_cached_before_the_color_tags_is_rebuilt_with_all_four(
    synth_project: Project,
) -> None:
    proxy, sidecar = _proxy_and_sidecar(synth_project, "b1")
    old = {"qhash": _clip(synth_project, "b1").qhash, "params": {"chain_version": "tm1", "crf": 23}}
    sidecar.write_text(json.dumps(old), encoding="utf-8")
    stamp = proxy.stat().st_mtime_ns

    assert run_kcut("ingest", "--project", str(synth_project[0]), "--json").returncode == 0

    assert proxy.stat().st_mtime_ns != stamp
    stream = _ffprobe_stream(proxy)
    assert [stream[k] for k in ("color_space", "color_primaries", "color_transfer")] == [
        "bt709"
    ] * 3
    assert stream["color_range"] == "tv"
