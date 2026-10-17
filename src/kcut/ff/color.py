"""Color chains: explicit bt709 everywhere, the one approved HDR to SDR tone-map (spec 0.7)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from kcut.ingest.probe import VideoInfo

HDR_TO_SDR = (
    "zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)
CHAIN_VERSION = "tm2"
# Explicit bt709 limited-range tags on the frames: ffmpeg 8 drops `-color_primaries` and
# `-color_trc` from the output flags when the frames do not carry them.
TAGS_BT709 = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"

_BT601_SPACES = frozenset({"smpte170m", "bt470bg"})
_MATRICES = frozenset({"bt601", "bt709"})
_RANGES = frozenset({"tv", "pc"})


def is_hdr(transfer: str | None) -> Literal["hlg", "pq"] | None:
    """`arib-std-b67` is HLG, `smpte2084` is PQ; anything else is SDR."""
    if transfer == "arib-std-b67":
        return "hlg"
    if transfer == "smpte2084":
        return "pq"
    return None


def sdr_scale(w: int, h: int, in_matrix: str, in_range: str) -> str:
    """Scale to `w`x`h`, reading the source with its own matrix/range and writing bt709 tv."""
    if in_matrix not in _MATRICES or in_range not in _RANGES:
        raise ValueError(f"matriz o rango no permitido: {in_matrix!r}, {in_range!r}")
    return (
        f"scale={int(w)}:{int(h)}:flags=lanczos:in_color_matrix={in_matrix}:in_range={in_range}"
        ":out_color_matrix=bt709:out_range=tv,format=yuv420p"
    )


def video_chain(info: VideoInfo, w: int, h: int, fps: int) -> str:
    """CFR + resize + SDR bt709 yuv420p chain for one video stream."""
    rate = f"fps={int(fps)}"
    if info.hdr is not None:
        return f"{rate},scale={int(w)}:{int(h)}:flags=lanczos,{HDR_TO_SDR},{TAGS_BT709}"
    matrix = "bt601" if info.color_space in _BT601_SPACES else "bt709"
    color_range = "pc" if info.color_range == "pc" else "tv"
    return f"{rate},{sdr_scale(w, h, matrix, color_range)},{TAGS_BT709}"
