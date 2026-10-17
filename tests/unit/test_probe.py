"""ffprobe JSON -> whitelisted MediaInfo: HDR, Dolby Vision, rotation, VFR, range, privacy."""

import copy
import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from kcut.errors import ProjectError
from kcut.ff.color import is_hdr
from kcut.ingest.probe import AudioInfo, VideoInfo, parse_ffprobe

DATA = Path(__file__).parents[1] / "data" / "ffprobe"


def _load(name: str) -> dict[str, Any]:
    data = json.loads((DATA / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.fixture
def iphone() -> dict[str, Any]:
    return _load("iphone_hlg_dv.json")


def _video(data: dict[str, Any]) -> dict[str, Any]:
    return next(s for s in data["streams"] if s["codec_type"] == "video")


class TestIphoneHlgDolbyVision:
    def test_video_fields(self, iphone: dict[str, Any]) -> None:
        video = parse_ffprobe(iphone).video
        assert video is not None
        assert (video.codec, video.w, video.h) == ("hevc", 3840, 2160)
        assert (video.display_w, video.display_h, video.rotation) == (2160, 3840, -90)
        assert (video.fps_r, video.fps_avg, video.vfr) == ("60/1", "35460/593", True)
        assert (video.pix_fmt, video.bit_depth) == ("yuv420p10le", 10)
        assert video.color_transfer == "arib-std-b67"
        assert video.color_primaries == "bt2020"
        assert (video.color_space, video.color_range) == ("bt2020nc", "tv")
        assert video.hdr == "hlg"
        assert (video.dolby_vision, video.dv_profile, video.start_ms) == (True, 8, 0)

    def test_audio_and_format(self, iphone: dict[str, Any]) -> None:
        info = parse_ffprobe(iphone)
        assert info.audio == AudioInfo("aac", 44100, 2, 0, 1)
        assert info.duration_ms == 131233
        assert info.size_bytes == 1534023111
        assert info.format_name.startswith("mov,mp4")

    def test_the_data_stream_is_ignored(self, iphone: dict[str, Any]) -> None:
        assert parse_ffprobe(iphone).audio is not None
        assert parse_ffprobe(iphone).video is not None

    def test_no_location_or_device_model_survives(self, iphone: dict[str, Any]) -> None:
        text = repr(parse_ffprobe(iphone))
        for leaked in (
            "18.4861",
            "069.9312",
            "iPhone",
            "Apple",
            "com.apple",
            "2026-10-14",
            "ISO6709",
        ):
            assert leaked not in text

    def test_only_whitelisted_fields_exist(self) -> None:
        video_fields = {f.name for f in dataclasses.fields(VideoInfo)}
        assert video_fields == {
            "codec",
            "w",
            "h",
            "display_w",
            "display_h",
            "rotation",
            "fps_r",
            "fps_avg",
            "vfr",
            "pix_fmt",
            "bit_depth",
            "color_transfer",
            "color_primaries",
            "color_space",
            "color_range",
            "hdr",
            "dolby_vision",
            "dv_profile",
            "start_ms",
        }
        assert {f.name for f in dataclasses.fields(AudioInfo)} == {
            "codec",
            "sample_rate",
            "channels",
            "start_ms",
            "streams",
        }


class TestScreenRecording:
    def test_sdr_full_range_cfr_without_audio(self) -> None:
        info = parse_ffprobe(_load("screen_sdr_pc.json"))
        video = info.video
        assert video is not None
        assert (video.w, video.h, video.display_w, video.display_h) == (1894, 866, 1894, 866)
        assert (video.fps_r, video.fps_avg, video.vfr) == ("30/1", "30/1", False)
        assert (video.color_range, video.color_space, video.hdr) == ("pc", "bt709", None)
        assert (video.rotation, video.dolby_vision, video.dv_profile) == (0, False, None)
        assert video.bit_depth == 8
        assert info.audio is None
        assert info.duration_ms == 8000


class TestAudioOnly:
    def test_cover_art_is_not_video(self) -> None:
        info = parse_ffprobe(_load("audio_only.json"))
        assert info.video is None
        assert info.audio == AudioInfo("aac", 48000, 2, 0, 1)
        assert info.duration_ms == 60000


class TestRules:
    def test_rotation_swaps_the_displayed_size(self, iphone: dict[str, Any]) -> None:
        for angle, swapped in [(90, True), (270, True), (-270, True), (180, False), (0, False)]:
            data = copy.deepcopy(iphone)
            _video(data)["side_data_list"][0]["rotation"] = angle
            video = parse_ffprobe(data).video
            assert video is not None
            assert (video.display_w, video.display_h) == ((2160, 3840) if swapped else (3840, 2160))

    def test_rotate_tag_is_the_fallback(self, iphone: dict[str, Any]) -> None:
        data = copy.deepcopy(iphone)
        stream = _video(data)
        del stream["side_data_list"]
        stream["tags"]["rotate"] = "90"
        video = parse_ffprobe(data).video
        assert video is not None
        assert (video.rotation, video.display_w, video.dolby_vision) == (90, 2160, False)

    @pytest.mark.parametrize(
        ("real", "avg", "vfr"),
        [
            ("30/1", "30/1", False),
            ("30/1", "30000/1001", False),  # 29.97 is 0.0999 % under: inside the tolerance
            ("30/1", "29/1", True),
            ("60/1", "35460/593", True),
            ("30/1", "0/0", False),
            ("0/0", "30/1", False),
        ],
    )
    def test_vfr_needs_more_than_0_1_percent_difference(
        self, iphone: dict[str, Any], real: str, avg: str, vfr: bool
    ) -> None:
        data = copy.deepcopy(iphone)
        _video(data)["r_frame_rate"], _video(data)["avg_frame_rate"] = real, avg
        video = parse_ffprobe(data).video
        assert video is not None
        assert video.vfr is vfr

    @pytest.mark.parametrize(("transfer", "hdr"), [("arib-std-b67", "hlg"), ("smpte2084", "pq")])
    def test_hdr_kinds(self, iphone: dict[str, Any], transfer: str, hdr: str) -> None:
        data = copy.deepcopy(iphone)
        _video(data)["color_transfer"] = transfer
        video = parse_ffprobe(data).video
        assert video is not None
        assert video.hdr == hdr == is_hdr(transfer)

    def test_sdr_transfers_are_not_hdr(self) -> None:
        assert is_hdr("bt709") is None
        assert is_hdr(None) is None

    def test_dolby_vision_profile_is_read_from_its_block(self, iphone: dict[str, Any]) -> None:
        data = copy.deepcopy(iphone)
        _video(data)["side_data_list"][1]["dv_profile"] = 5
        video = parse_ffprobe(data).video
        assert video is not None
        assert (video.dolby_vision, video.dv_profile) == (True, 5)

    @pytest.mark.parametrize(
        ("pix_fmt", "raw", "depth"),
        [
            ("yuv420p10le", None, 10),
            ("yuv420p", None, 8),
            ("yuv420p10be", None, 10),
            ("yuv420p12le", "12", 12),
            ("yuv420p", "8", 8),
        ],
    )
    def test_bit_depth(
        self, iphone: dict[str, Any], pix_fmt: str, raw: str | None, depth: int
    ) -> None:
        data = copy.deepcopy(iphone)
        stream = _video(data)
        stream["pix_fmt"] = pix_fmt
        stream.pop("bits_per_raw_sample")
        if raw is not None:
            stream["bits_per_raw_sample"] = raw
        video = parse_ffprobe(data).video
        assert video is not None
        assert video.bit_depth == depth

    def test_start_ms_is_relative_to_the_container(self, iphone: dict[str, Any]) -> None:
        data = copy.deepcopy(iphone)
        data["format"]["start_time"] = "0.100000"
        data["streams"][0]["start_time"] = "0.133000"
        data["streams"][1]["start_time"] = "0.050000"
        info = parse_ffprobe(data)
        assert info.video is not None
        assert info.video.start_ms == 33
        assert info.audio is not None
        assert info.audio.start_ms == -50

    def test_several_audio_streams_are_counted(self, iphone: dict[str, Any]) -> None:
        data = copy.deepcopy(iphone)
        data["streams"].append(copy.deepcopy(data["streams"][1]))
        info = parse_ffprobe(data)
        assert info.audio is not None
        assert info.audio.streams == 2

    def test_a_long_image_codec_stream_is_real_video(self, iphone: dict[str, Any]) -> None:
        data = copy.deepcopy(iphone)
        stream = _video(data)
        stream.update(codec_name="mjpeg", duration="5.000000")
        stream["disposition"] = {"attached_pic": 0}
        assert parse_ffprobe(data).video is not None

    def test_a_short_png_stream_is_a_cover(self, iphone: dict[str, Any]) -> None:
        data = copy.deepcopy(iphone)
        stream = _video(data)
        stream.update(codec_name="png", duration="0.040000")
        assert parse_ffprobe(data).video is None

    def test_an_attached_picture_flag_is_a_cover_whatever_its_duration(
        self, iphone: dict[str, Any]
    ) -> None:
        data = copy.deepcopy(iphone)
        stream = _video(data)
        stream.update(codec_name="mjpeg", duration="131.0")
        stream["disposition"] = {"attached_pic": 1}
        assert parse_ffprobe(data).video is None

    def test_missing_values_do_not_crash(self) -> None:
        data = {
            "format": {"duration": "N/A"},
            "streams": [{"codec_type": "audio", "codec_name": "mp3", "duration": "3.5"}],
        }
        info = parse_ffprobe(data)
        assert info.duration_ms == 3500
        assert info.audio == AudioInfo("mp3", 0, 0, 0, 1)
        assert info.video is None


class TestBadInput:
    @pytest.mark.parametrize(
        "data", [{}, {"format": {}}, {"streams": []}, {"format": [], "streams": []}]
    )
    def test_not_an_ffprobe_document(self, data: dict[str, Any]) -> None:
        with pytest.raises(ProjectError):
            parse_ffprobe(data)

    def test_non_dict_streams_are_skipped(self) -> None:
        info = parse_ffprobe({"format": {"duration": "1.0"}, "streams": ["x", 3, None]})
        assert (info.video, info.audio) == (None, None)
