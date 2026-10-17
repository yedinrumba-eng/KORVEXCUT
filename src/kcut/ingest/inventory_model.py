"""Dataclasses of the inventory (spec S1.2); JSON reading and writing live in `inventory.py`."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from kcut.ingest.classify import ClipClass
from kcut.ingest.probe import VideoInfo

SCHEMA = "kcut.inventory/1"


@dataclass(frozen=True)
class ImageMeta:
    w: int
    h: int
    has_alpha: bool


@dataclass(frozen=True)
class ClipAudio:
    codec: str
    sample_rate: int
    channels: int
    start_ms: int
    streams: int
    peak_dbfs: float
    silent: bool


@dataclass(frozen=True)
class WorkFiles:
    proxy: str | None
    wav16: str | None
    proxy_w: int | None
    proxy_h: int | None


@dataclass(frozen=True)
class Clip:
    id: str
    file: str
    slug: str
    clip_class: ClipClass
    qhash: str
    size_bytes: int
    duration_ms: int | None = None
    frames: int | None = None
    video: VideoInfo | None = None
    audio: ClipAudio | None = None
    image: ImageMeta | None = None
    work: WorkFiles | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyncMember:
    id: str
    offset_ms: int
    score: float
    second: float
    ratio: float | None
    drift_ms: int | None
    drift_windows: int
    method: str
    refine_corr: float | None = None
    sync_version: int = 1  # SYNC_VERSION of the algorithm that measured it; missing means 1


@dataclass(frozen=True)
class SyncRejected:
    id: str
    score: float
    ratio: float | None
    reason: str
    refine_corr: float | None = None
    lag_a_ms: int | None = None  # `sync_ambiguous` only: best lag at the 0.75 overlap floor
    lag_b_ms: int | None = None  # `sync_ambiguous` only: best lag at the 0.5 overlap floor
    sync_version: int = 1  # SYNC_VERSION of the algorithm that measured it; missing means 1


@dataclass(frozen=True)
class SyncInfo:
    master: str | None = None
    members: tuple[SyncMember, ...] = ()
    rejected: tuple[SyncRejected, ...] = ()


@dataclass(frozen=True)
class Notice:
    """A run-level warning that belongs to no single clip (`skipped_link`, `cache_rebuilt`...)."""

    code: str
    detail: str
    file: str | None = None


@dataclass(frozen=True)
class Inventory:
    generated: str
    fps: int
    clips: tuple[Clip, ...]
    sync: SyncInfo = field(default_factory=SyncInfo)
    id_high: Mapping[str, int] = field(default_factory=dict)
    schema: str = SCHEMA

    def by_id(self, clip_id: str) -> Clip | None:
        for clip in self.clips:
            if clip.id == clip_id:
                return clip
        return None
