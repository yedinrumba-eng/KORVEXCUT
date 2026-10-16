"""proc.scrub_media_metadata: nothing about where or with what a clip was shot may leak."""

from kcut.proc import scrub_media_metadata

IPHONE_DUMP = """\
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'crudo/IMG_0001.MOV':
  Metadata:
    major_brand     : qt
    minor_version   : 0
    compatible_brands: qt
    creation_time   : 2026-10-14T20:11:03.000000Z
    com.apple.quicktime.location.ISO6709: +18.4861-069.9312+012.345/
    com.apple.quicktime.make: Apple
    com.apple.quicktime.model: iPhone 15 Pro
    com.apple.quicktime.software: 17.5.1
  Duration: 00:02:11.23, start: 0.000000, bitrate: 21034 kb/s
  Stream #0:0[0x1](und): Video: hevc (Main 10), yuv420p10le, 1080x1920, 59.99 fps
    Metadata:
      creation_time   : 2026-10-14T20:11:03.000000Z
      handler_name    : Core Media Video
      vendor_id       : [0][0][0][0]
  Stream #0:1[0x2](und): Audio: aac (LC), 48000 Hz, mono, fltp, 98 kb/s
    Metadata:
      handler_name    : Core Media Audio
Error opening output file x.mp4
"""

SECRETS = (
    "18.4861",
    "069.9312",
    "ISO6709",
    "iPhone",
    "Apple",
    "com.apple",
    "creation_time",
    "2026-10-14T20",
    "handler_name",
    "major_brand",
)


class TestMetadataBlocks:
    def test_real_mov_dump_loses_every_secret(self) -> None:
        cleaned = scrub_media_metadata(IPHONE_DUMP)
        for secret in SECRETS:
            assert secret not in cleaned, secret

    def test_lines_outside_the_blocks_survive(self) -> None:
        cleaned = scrub_media_metadata(IPHONE_DUMP)
        assert "Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'crudo/IMG_0001.MOV':\n" in cleaned
        assert "  Duration: 00:02:11.23, start: 0.000000, bitrate: 21034 kb/s\n" in cleaned
        assert "Stream #0:0[0x1](und): Video: hevc (Main 10)" in cleaned
        assert "Stream #0:1[0x2](und): Audio: aac (LC)" in cleaned
        assert cleaned.endswith("Error opening output file x.mp4\n")

    def test_block_ends_at_the_first_line_that_is_not_more_indented(self) -> None:
        text = "  Metadata:\n    a: 1\n  Duration: 5\n    Metadata:\n      b: 2\n    keep: 3\n"
        assert scrub_media_metadata(text) == "  Duration: 5\n    keep: 3\n"

    def test_crlf_line_endings_are_kept(self) -> None:
        text = "x\r\n  Metadata:\r\n    a: 1\r\ny\r\n"
        assert scrub_media_metadata(text) == "x\r\ny\r\n"


class TestKeyedLines:
    def test_sensitive_keys_are_dropped_case_insensitively(self) -> None:
        text = "\n".join(
            [
                "Location: somewhere",
                "GPS Latitude: 1",
                "gpsdata: 2",
                "com.apple.quicktime.anything: 3",
                "Make : Apple",
                "MODEL: x",
                "creation_time   : 2026-10-14T20:11:03.000000Z",
                "kept: yes",
            ]
        )
        assert scrub_media_metadata(text) == "kept: yes"

    def test_only_the_innocent_line_remains(self) -> None:
        text = (
            "location : a\ngps: b\ncom.apple.x: c\nmake: d\nmodel: e\ncreation_time: f\nfps: 30\n"
        )
        assert scrub_media_metadata(text) == "fps: 30\n"

    def test_ordinary_lines_are_untouched(self) -> None:
        text = (
            "Duration: 00:00:10.50, start: 0.000000, bitrate: 1200 kb/s\n"
            "frame=  10 fps=0.0 q=-1.0 size=N/A time=00:00:00.33\n"
            "crudo/clip.mp4: No such file or directory\n"
            '[Parsed_loudnorm_0 @ 000001] {"input_i" : "-23.5"}\n'
        )
        assert scrub_media_metadata(text) == text


class TestCoordinates:
    def test_iso6709_anywhere_is_replaced(self) -> None:
        text = "geo +18.4861-069.9312 end\n"
        assert scrub_media_metadata(text) == "geo [ubicacion omitida] end\n"

    def test_two_coordinates_on_one_line(self) -> None:
        text = "a +40.7128-074.0060 b -33.8688+151.2093 c\n"
        assert scrub_media_metadata(text) == "a [ubicacion omitida] b [ubicacion omitida] c\n"

    def test_empty_text(self) -> None:
        assert scrub_media_metadata("") == ""
