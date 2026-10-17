"""Ready-made `VideoInfo` values for the unit tests."""

import dataclasses

from kcut.ingest.probe import VideoInfo


def make_video(**changes: object) -> VideoInfo:
    """A 1440x2560, 30 fps, 8-bit bt709 SDR video; `changes` overrides any field."""
    base = VideoInfo(
        codec="h264",
        w=1440,
        h=2560,
        display_w=1440,
        display_h=2560,
        rotation=0,
        fps_r="30/1",
        fps_avg="30/1",
        vfr=False,
        pix_fmt="yuv420p",
        bit_depth=8,
        color_transfer=None,
        color_primaries=None,
        color_space="bt709",
        color_range="tv",
        hdr=None,
        dolby_vision=False,
        dv_profile=None,
        start_ms=0,
    )
    return dataclasses.replace(base, **changes)


def make_hlg_video(**changes: object) -> VideoInfo:
    """The same video as 10-bit HLG bt2020."""
    return make_video(
        **{
            "pix_fmt": "yuv420p10le",
            "bit_depth": 10,
            "color_transfer": "arib-std-b67",
            "color_primaries": "bt2020",
            "color_space": "bt2020nc",
            "hdr": "hlg",
            **changes,
        }
    )
