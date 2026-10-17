"""ffmpeg/ffprobe argument builders and color chains: exact lists, no paths inside filters."""

import dataclasses
import math
from pathlib import Path

import pytest

from kcut.ff.args import ffprobe_args, fnum, mezz_args, proxy_args, wav_args
from kcut.ff.color import CHAIN_VERSION, HDR_TO_SDR, TAGS_BT709, sdr_scale, video_chain
from tests.unit.media_fakes import make_hlg_video, make_video

FFMPEG = Path("C:/tools/ffmpeg/bin/ffmpeg.exe")
FFPROBE = Path("C:/tools/ffmpeg/bin/ffprobe.exe")
SRC = Path("C:/Users/Yedin/Mis videos/proyecto ñandú/crudo/cam a.mp4")
DST = Path("C:/Users/Yedin/Mis videos/proyecto ñandú/.kcut/proxy/a1_cam-a.partial.mp4")
QUIET = ["-hide_banner", "-nostdin", "-loglevel", "error"]
COLOR = [
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
]

SDR = make_video()
HLG = make_hlg_video()


class TestFnum:
    @pytest.mark.parametrize(
        ("value", "text"),
        [
            (0, "0"),
            (0.0, "0"),
            (-0.0, "0"),
            (1.5, "1.5"),
            (2.0, "2"),
            (100.0, "100"),
            (1 / 30, "0.033333"),
            (12.3456789, "12.345679"),
            (0.0000001, "0"),
            (-1.25, "-1.25"),
        ],
    )
    def test_formats(self, value: float, text: str) -> None:
        assert fnum(value) == text

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_not_finite_raises(self, bad: float) -> None:
        with pytest.raises(ValueError):
            fnum(bad)


class TestFfprobeArgs:
    def test_exact_list(self) -> None:
        assert ffprobe_args(FFPROBE, SRC) == [
            str(FFPROBE),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(SRC),
        ]


class TestLengthCap:
    """`-t` caps the output: the declared duration of a file is not trusted (001.6)."""

    def test_wav_and_proxy_take_the_cap_before_the_metadata_flag(self) -> None:
        for args in (
            wav_args(FFMPEG, SRC, DST, 16000, 43260.0),
            proxy_args(FFMPEG, SRC, DST, "fps=30", 30, 43260.0),
        ):
            assert args[args.index("-t") + 1] == "43260"
            assert args.index("-t") < args.index("-map_metadata")
            assert args[-1] == str(DST)

    def test_without_a_cap_there_is_no_t(self) -> None:
        assert "-t" not in wav_args(FFMPEG, SRC, DST, 16000)
        assert "-t" not in proxy_args(FFMPEG, SRC, DST, "fps=30", 30)


class TestWavArgs:
    def test_exact_list_16k_to_a_partial_file(self) -> None:
        dst = Path("C:/p/.kcut/wav16/a1_cam-a.partial.wav")
        assert wav_args(FFMPEG, SRC, dst, 16000) == [
            str(FFMPEG),
            *QUIET,
            "-y",
            "-i",
            str(SRC),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-af",
            "aresample=16000:resampler=soxr:first_pts=0",
            "-c:a",
            "pcm_s16le",
            "-map_metadata",
            "-1",
            str(dst),
        ]

    def test_48k(self) -> None:
        args = wav_args(FFMPEG, SRC, Path("C:/p/x.partial.wav"), 48000)
        assert "aresample=48000:resampler=soxr:first_pts=0" in args

    def test_overwrite_flag_only_for_partial_files(self) -> None:
        assert "-y" not in wav_args(FFMPEG, SRC, Path("C:/p/final.wav"), 16000)
        assert "-y" in wav_args(FFMPEG, SRC, Path("C:/p/final.partial.wav"), 16000)

    def test_metadata_is_dropped_before_the_output(self) -> None:
        args = wav_args(FFMPEG, SRC, Path("C:/p/x.partial.wav"), 16000)
        assert args.index("-map_metadata") == len(args) - 3
        assert args[-2] == "-1"


class TestProxyArgs:
    def test_exact_list(self) -> None:
        chain = video_chain(SDR, 540, 960, 30)
        assert proxy_args(FFMPEG, SRC, DST, chain, 30) == [
            str(FFMPEG),
            *QUIET,
            "-y",
            "-i",
            str(SRC),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            chain,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-g",
            "30",
            "-keyint_min",
            "30",
            "-pix_fmt",
            "yuv420p",
            *COLOR,
            "-map_metadata",
            "-1",
            "-movflags",
            "+faststart",
            str(DST),
        ]

    def test_gop_follows_the_fps(self) -> None:
        args = proxy_args(FFMPEG, SRC, DST, "fps=24", 24)
        assert args[args.index("-g") + 1] == "24"
        assert args[args.index("-keyint_min") + 1] == "24"

    def test_metadata_is_dropped(self) -> None:
        args = proxy_args(FFMPEG, SRC, DST, "fps=30", 30)
        assert args[args.index("-map_metadata") + 1] == "-1"
        assert args.index("-map_metadata") < args.index("-movflags")


class TestMezzArgs:
    def test_exact_list(self) -> None:
        dst = Path("C:/p/.kcut/mezz/a1_45-135.partial.mp4")
        chain = video_chain(SDR, 1440, 2560, 30)
        assert mezz_args(FFMPEG, SRC, dst, chain, 30, 45, 90) == [
            str(FFMPEG),
            *QUIET,
            "-y",
            "-ss",
            "1.5",
            "-i",
            str(SRC),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            chain,
            "-frames:v",
            "90",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "14",
            "-g",
            "30",
            "-keyint_min",
            "30",
            "-pix_fmt",
            "yuv420p",
            *COLOR,
            "-map_metadata",
            "-1",
            str(dst),
        ]

    def test_start_is_formatted_with_fnum(self) -> None:
        args = mezz_args(FFMPEG, SRC, Path("C:/p/m.partial.mp4"), "fps=30", 30, 1, 5)
        assert args[args.index("-ss") + 1] == "0.033333"


class TestNoPathsInsideFilters:
    def test_filters_never_carry_a_path(self) -> None:
        chain = video_chain(HLG, 540, 960, 30)
        all_args = [
            proxy_args(FFMPEG, SRC, DST, chain, 30),
            mezz_args(FFMPEG, SRC, DST, chain, 30, 0, 10),
            wav_args(FFMPEG, SRC, DST, 16000),
        ]
        for args in all_args:
            for flag in ("-vf", "-af"):
                if flag in args:
                    value = args[args.index(flag) + 1]
                    assert "\\" not in value
                    assert "C:" not in value
                    assert "ñandú" not in value
                    assert str(SRC) not in value

    def test_every_argument_is_a_string(self) -> None:
        for args in (
            ffprobe_args(FFPROBE, SRC),
            wav_args(FFMPEG, SRC, DST, 16000),
            proxy_args(FFMPEG, SRC, DST, "fps=30", 30),
            mezz_args(FFMPEG, SRC, DST, "fps=30", 30, 0, 1),
        ):
            assert all(isinstance(a, str) for a in args)
            assert Path(args[0]).is_absolute()

    def test_the_paths_stay_whole_with_spaces_and_accents(self) -> None:
        args = proxy_args(FFMPEG, SRC, DST, "fps=30", 30)
        assert str(SRC) in args
        assert str(DST) in args


class TestColor:
    def test_hdr_chain_is_the_one_approved_for_this_machine(self) -> None:
        assert HDR_TO_SDR == (
            "zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
            "zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
        )
        assert CHAIN_VERSION == "tm2"
        assert TAGS_BT709 == (
            "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
        )

    def test_sdr_scale_exact(self) -> None:
        assert sdr_scale(540, 960, "bt709", "tv") == (
            "scale=540:960:flags=lanczos:in_color_matrix=bt709:in_range=tv"
            ":out_color_matrix=bt709:out_range=tv,format=yuv420p"
        )

    @pytest.mark.parametrize(
        ("matrix", "color_range"), [("bt470", "tv"), ("bt709", "limited"), ("x;y", "tv")]
    )
    def test_sdr_scale_only_takes_known_words(self, matrix: str, color_range: str) -> None:
        with pytest.raises(ValueError):
            sdr_scale(10, 10, matrix, color_range)

    def test_sdr_chain_is_cfr_then_the_explicit_scale(self) -> None:
        expected = "fps=30," + sdr_scale(540, 960, "bt709", "tv") + "," + TAGS_BT709
        assert video_chain(SDR, 540, 960, 30) == expected

    @pytest.mark.parametrize("space", ["smpte170m", "bt470bg"])
    def test_sd_sources_are_read_with_the_bt601_matrix(self, space: str) -> None:
        chain = video_chain(dataclasses.replace(SDR, color_space=space), 540, 960, 25)
        assert chain == "fps=25," + sdr_scale(540, 960, "bt601", "tv") + "," + TAGS_BT709

    @pytest.mark.parametrize("space", [None, "bt709", "unknown", "bt2020nc"])
    def test_everything_else_is_read_as_bt709(self, space: str | None) -> None:
        chain = video_chain(dataclasses.replace(SDR, color_space=space), 540, 960, 30)
        assert "in_color_matrix=bt709" in chain

    def test_full_range_sources_say_so(self) -> None:
        chain = video_chain(dataclasses.replace(SDR, color_range="pc"), 960, 438, 30)
        assert "in_range=pc" in chain
        assert "scale=960:438:" in chain

    @pytest.mark.parametrize("transfer", ["arib-std-b67", "smpte2084"])
    def test_hdr_chain_resizes_first_then_tone_maps(self, transfer: str) -> None:
        info = dataclasses.replace(HLG, color_transfer=transfer, hdr="hlg")
        assert video_chain(info, 540, 960, 30) == (
            "fps=30,scale=540:960:flags=lanczos," + HDR_TO_SDR + "," + TAGS_BT709
        )

    def test_every_chain_ends_with_the_bt709_tags(self) -> None:
        for info in (SDR, HLG, dataclasses.replace(SDR, color_range="pc")):
            assert video_chain(info, 540, 960, 30).endswith("," + TAGS_BT709)
