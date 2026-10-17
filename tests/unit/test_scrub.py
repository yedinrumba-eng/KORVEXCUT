"""proc.scrub_media_metadata: nothing about where or with what a clip was shot may leak."""

from kcut.proc import scrub_media_metadata
from kcut.scrub import MetadataScrubber

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


class TestWholeWordKeys:
    """Keys match by whole word and only when short: English sentences with a colon survive."""

    def test_error_sentences_that_contain_a_key_word_are_kept(self) -> None:
        text = (
            "Unable to make progress: no space left on device\n"
            "Could not determine model: unsupported codec\n"
            "Subtitle: none\n"
            "makeup: 1\n"
            "datamodel: 2\n"
        )
        assert scrub_media_metadata(text) == text

    def test_short_keys_with_a_sensitive_word_are_dropped(self) -> None:
        text = (
            "com.apple.quicktime.make: Apple\n"
            "GPS Latitude Ref: N\n"
            "GPSLatitude: 18 deg\n"
            "location-eng   : +18.4861-069.9312/\n"
            "serial_number: C02XYZ\n"
            "encoded_by: Yedin\n"
            "Model : iPhone 15 Pro\n"
            "title: Boda de Ana\n"
            "Duration: 00:00:05.00\n"
        )
        assert scrub_media_metadata(text) == "Duration: 00:00:05.00\n"


class TestTagLines:
    def test_ffprobe_default_output_loses_sensitive_tags(self) -> None:
        text = (
            "[FORMAT]\r\n"
            "filename=crudo/IMG_0001.MOV\r\n"
            "duration=131.230000\r\n"
            "TAG:major_brand=qt\r\n"
            "TAG:creation_time=2026-10-14T20:11:03.000000Z\r\n"
            "TAG:com.apple.quicktime.location.ISO6709=+18.4861-069.9312+012.345/\r\n"
            "TAG:com.apple.quicktime.make=Apple\r\n"
            "TAG:com.apple.quicktime.model=iPhone 15 Pro\r\n"
            "TAG:location=+18.4861-069.9312/\r\n"
            "TAG:artist=Yedin\r\n"
            "TAG:comment=casa de mami\r\n"
            "TAG:copyright=Yedin 2026\r\n"
            "TAG:encoder=Lavf61.7.100\r\n"
            "[/FORMAT]\r\n"
        )
        assert scrub_media_metadata(text) == (
            "[FORMAT]\r\n"
            "filename=crudo/IMG_0001.MOV\r\n"
            "duration=131.230000\r\n"
            "TAG:major_brand=qt\r\n"
            "TAG:encoder=Lavf61.7.100\r\n"
            "[/FORMAT]\r\n"
        )


class TestJsonPairs:
    def test_pretty_ffprobe_json_loses_sensitive_pairs(self) -> None:
        text = (
            "{\n"
            '    "format": {\n'
            '        "filename": "crudo/IMG_0001.MOV",\n'
            '        "duration": "131.230000",\n'
            '        "tags": {\n'
            '            "major_brand": "qt",\n'
            '            "creation_time": "2026-10-14T20:11:03.000000Z",\n'
            '            "com.apple.quicktime.location.ISO6709": "+18.4861-069.9312+012.345/",\n'
            '            "com.apple.quicktime.make": "Apple",\n'
            '            "com.apple.quicktime.model": "iPhone 15 Pro",\n'
            '            "description": "la \\"boda\\" de Ana",\n'
            '            "encoder": "Lavf61.7.100"\n'
            "        }\n"
            "    }\n"
            "}\n"
        )
        assert scrub_media_metadata(text) == (
            "{\n"
            '    "format": {\n'
            '        "filename": "crudo/IMG_0001.MOV",\n'
            '        "duration": "131.230000",\n'
            '        "tags": {\n'
            '            "major_brand": "qt",\n'
            '            "encoder": "Lavf61.7.100"\n'
            "        }\n"
            "    }\n"
            "}\n"
        )

    def test_one_line_json_keeps_the_innocent_pairs(self) -> None:
        text = '{"title": "Boda de Ana", "duration": "5.0", "serial": "C02XYZ"}\n'
        assert scrub_media_metadata(text) == '{ "duration": "5.0", }\n'


class TestCoordinates:
    def test_iso6709_anywhere_is_replaced(self) -> None:
        text = "geo +18.4861-069.9312 end\n"
        assert scrub_media_metadata(text) == "geo [ubicacion omitida] end\n"

    def test_two_coordinates_on_one_line(self) -> None:
        text = "a +40.7128-074.0060 b -33.8688+151.2093 c\n"
        assert scrub_media_metadata(text) == "a [ubicacion omitida] b [ubicacion omitida] c\n"

    def test_trailing_altitude_and_slash_go_too(self) -> None:
        text = "at +18.4861-069.9312+012.345/ now\n"
        assert scrub_media_metadata(text) == "at [ubicacion omitida] now\n"

    def test_degrees_minutes_seconds_and_compact_forms(self) -> None:
        text = (
            "dms +181030-0695555/ dm +1810.5-06955.9/ alt +181030.5-0695555.25+12/ deg +18-069/\n"
        )
        assert scrub_media_metadata(text) == (
            "dms [ubicacion omitida] dm [ubicacion omitida] alt [ubicacion omitida] "
            "deg [ubicacion omitida]\n"
        )

    def test_numbers_that_are_not_coordinates_are_kept(self) -> None:
        text = (
            "bitrate: 21034 kb/s, 30000/1001 fps, 1/90000 tbn\n"
            "frame=  10 fps=0.0 q=-1.0 size=N/A time=00:00:00.33 speed=1.2x\n"
            "2026-10-14 offset -0.8 ms\n"
        )
        assert scrub_media_metadata(text) == text

    def test_empty_text(self) -> None:
        assert scrub_media_metadata("") == ""


def test_scrubber_keeps_a_metadata_block_open_across_feeds() -> None:
    """Streaming: the block that starts in one chunk still hides its lines in the next one."""
    scrubber = MetadataScrubber()
    out = scrubber.feed("x\n  Metadata:\n    major_brand: qt\n")
    out += scrubber.feed("    handler_name: Core Media Video\n  Duration: 5\n")
    assert out == "x\n  Duration: 5\n"
