"""Parsers of ffmpeg capabilities, fed with text captured from real ffmpeg runs.

Two real captures: ffmpeg 8.1.1 (gyan full build, two flag columns) and ffmpeg n7.0.1 (Playwright
build, three flag columns). Both are trimmed or whole outputs with the original CRLF endings.
"""

import pytest

from kcut.doctor.ffmpeg_caps import parse_encoders, parse_filters, parse_version

VERSION_811 = (
    "ffmpeg version 8.1.1-full_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers\r\n"
    "built with gcc 15.2.0 (Rev13, Built by MSYS2 project)\r\n"
)
VERSION_701 = "ffmpeg version n7.0.1-playwright-build-1011 Copyright (c) 2000-2024 the FFmpeg\r\n"

FILTERS_811 = (
    "Filters:\r\n"
    "  T.. = Timeline support\r\n"
    "  .S. = Slice threading\r\n"
    "  A = Audio input/output\r\n"
    "  V = Video input/output\r\n"
    "  N = Dynamic number and/or type of input/output\r\n"
    "  | = Source or sink filter\r\n"
    "  ------\r\n"
    " TS aap               AA->A      Apply Affine Projection algorithm to first audio stream.\r\n"
    " .. abench            A->A       Benchmark part of a filtergraph.\r\n"
    " .. acompressor       A->A       Audio compressor.\r\n"
    " .. asplit            A->N       Pass on the audio input to N audio outputs.\r\n"
    " .. anullsink         A->|       Do absolutely nothing with the input audio.\r\n"
    " .. flite             |->A       Synthesize voice from text using libflite.\r\n"
    " TS highpass          A->A       Apply a high-pass filter with 3dB point frequency.\r\n"
    " .S tonemap           V->V       Conversion to/from different dynamic ranges.\r\n"
    " .. tonemap_opencl    V->V       Perform HDR to SDR conversion with tonemapping.\r\n"
    " .S zscale            V->V       Apply resizing, colorspace and bit depth conversion.\r\n"
)
FILTERS_811_NAMES = {
    "aap",
    "abench",
    "acompressor",
    "asplit",
    "anullsink",
    "flite",
    "highpass",
    "tonemap",
    "tonemap_opencl",
    "zscale",
}

FILTERS_701 = (
    "Filters:\r\n"
    "  T.. = Timeline support\r\n"
    "  .S. = Slice threading\r\n"
    "  ..C = Command support\r\n"
    "  A = Audio input/output\r\n"
    "  V = Video input/output\r\n"
    "  N = Dynamic number and/or type of input/output\r\n"
    "  | = Source or sink filter\r\n"
    " ... aformat           A->A       Convert the input audio to one of the specified formats.\r\n"
    " ... anull             A->A       Pass the source unchanged to the output.\r\n"
    " ... atrim             A->A       Pick one continuous section from the input.\r\n"
    " ..C crop              V->V       Crop the input video.\r\n"
    " ... format            V->V       Convert the input video to one of the pixel formats.\r\n"
    " TS. hflip             V->V       Horizontally flip the input video.\r\n"
    " ... null              V->V       Pass the source unchanged to the output.\r\n"
    " ... pad               V->V       Pad the input video.\r\n"
    " ..C scale             V->V       Scale the input video size and/or convert the format.\r\n"
    " .S. transpose         V->V       Transpose input video.\r\n"
    " ... trim              V->V       Pick one continuous section from the input.\r\n"
    " T.. vflip             V->V       Flip the input video vertically.\r\n"
    " ... abuffer           |->A       Buffer audio frames, and make them accessible.\r\n"
    " ... buffer            |->V       Buffer video frames, and make them accessible.\r\n"
    " ... abuffersink       A->|       Buffer audio frames, and make them available.\r\n"
    " ... buffersink        V->|       Buffer video frames, and make them available.\r\n"
)
FILTERS_701_NAMES = {
    "aformat",
    "anull",
    "atrim",
    "crop",
    "format",
    "hflip",
    "null",
    "pad",
    "scale",
    "transpose",
    "trim",
    "vflip",
    "abuffer",
    "buffer",
    "abuffersink",
    "buffersink",
}

ENCODER_LEGEND = (
    "Encoders:\r\n"
    " V..... = Video\r\n"
    " A..... = Audio\r\n"
    " S..... = Subtitle\r\n"
    " .F.... = Frame-level multithreading\r\n"
    " ..S... = Slice-level multithreading\r\n"
    " ...X.. = Codec is experimental\r\n"
    " ....B. = Supports draw_horiz_band\r\n"
    " .....D = Supports direct rendering method 1\r\n"
    " ------\r\n"
)
ENCODERS_811 = ENCODER_LEGEND + (
    " V....D a64multi             Multicolor charset for Commodore 64 (codec a64_multi)\r\n"
    " V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC (codec h264)\r\n"
    " V..... libsvtav1            SVT-AV1(Scalable Video Technology for AV1) (codec av1)\r\n"
    " A....D aac                  AAC (Advanced Audio Coding)\r\n"
    " A....D pcm_s16le            PCM signed 16-bit little-endian\r\n"
    " S..... srt                  SubRip subtitle (codec subrip)\r\n"
)
ENCODERS_811_NAMES = {"a64multi", "libx264", "libsvtav1", "aac", "pcm_s16le", "srt"}
ENCODERS_701 = ENCODER_LEGEND + (
    " VF...D png                  PNG (Portable Network Graphics) image\r\n"
    " V....D libvpx               libvpx VP8 (codec vp8)\r\n"
)
ENCODERS_701_NAMES = {"png", "libvpx"}


class TestParseVersion:
    def test_gyan_release_build(self) -> None:
        assert parse_version(VERSION_811) == (8, 1, 1)

    def test_playwright_n_prefixed_build(self) -> None:
        assert parse_version(VERSION_701) == (7, 0, 1)

    def test_release_without_patch_number(self) -> None:
        assert parse_version("ffmpeg version 7.0 Copyright (c) 2000-2024") == (7, 0, 0)

    def test_git_build_is_unknown(self) -> None:
        text = "ffmpeg version N-117892-g1a2b3c4d5e Copyright (c) 2000-2024 the FFmpeg developers"
        assert parse_version(text) is None

    def test_date_stamped_git_build_is_unknown(self) -> None:
        assert parse_version("ffmpeg version 2024-05-01-git-abcdef-full_build Copyright") is None

    @pytest.mark.parametrize("text", ["", "hello", "ffprobe version 8.1.1"])
    def test_garbage_is_unknown(self, text: str) -> None:
        assert parse_version(text) is None


class TestParseFilters:
    def test_ffmpeg_8_two_flag_columns_exact_set(self) -> None:
        assert parse_filters(FILTERS_811) == FILTERS_811_NAMES

    def test_ffmpeg_7_three_flag_columns_exact_set(self) -> None:
        assert parse_filters(FILTERS_701) == FILTERS_701_NAMES

    def test_spec_examples_of_both_layouts(self) -> None:
        seven = " ... aresample         A->A       Audio resampling and converting.\n"
        eight = " .. acompressor       A->A       Audio compressor.\n"
        assert parse_filters(seven) == {"aresample"}
        assert parse_filters(eight) == {"acompressor"}

    def test_legend_lines_are_never_filters(self) -> None:
        legend = FILTERS_701.split(" ... aformat")[0]
        assert parse_filters(legend) == frozenset()
        assert parse_filters(FILTERS_811.split(" TS aap")[0]) == frozenset()

    def test_empty_text(self) -> None:
        assert parse_filters("") == frozenset()


class TestParseEncoders:
    def test_ffmpeg_8_exact_set(self) -> None:
        assert parse_encoders(ENCODERS_811) == ENCODERS_811_NAMES

    def test_ffmpeg_7_exact_set(self) -> None:
        assert parse_encoders(ENCODERS_701) == ENCODERS_701_NAMES

    def test_legend_lines_are_never_encoders(self) -> None:
        assert parse_encoders(ENCODER_LEGEND) == frozenset()
        assert "=" not in parse_encoders(ENCODERS_811)

    def test_empty_text(self) -> None:
        assert parse_encoders("") == frozenset()
