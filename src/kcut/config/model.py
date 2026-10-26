"""Frozen dataclasses of `kcut.toml` (spec S1.2). Defaults live in `load.py`."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectSection:
    name: str
    language: str
    created: str


@dataclass(frozen=True)
class OutputSection:
    preset: str
    fps: int
    w: int
    h: int
    safe_top_px: int
    safe_bottom_px: int


@dataclass(frozen=True)
class BrandSection:
    accent: str
    accent2: str
    dark: str
    light: str


@dataclass(frozen=True)
class TranscribeSection:
    model: str
    compute_type: str
    beam_size: int
    cpu_threads: int
    fillers: tuple[str, ...]
    prompt_extra: str


@dataclass(frozen=True)
class AnalysisSection:
    silence_db: float
    min_silence_ms: int
    phrase_pause_ms: int
    long_pause_ms: int
    low_prob: float


@dataclass(frozen=True)
class SyncSection:
    master: str
    min_score: float
    min_ratio: float
    max_drift_ms: int
    min_refine_corr: float
    manual: Mapping[str, int]


@dataclass(frozen=True)
class CaptionsSection:
    enabled: bool
    uppercase: bool
    max_words: int
    max_chars: int
    y: float
    font_px: int
    color: str
    active_color: str
    stroke_color: str


@dataclass(frozen=True)
class VoiceChain:
    highpass_hz: int
    denoise_nr: float
    denoise_nf: float
    comp_threshold_db: float
    comp_ratio: float


@dataclass(frozen=True)
class AudioSection:
    voice_lufs: float
    target_lufs: float
    target_tp: float
    voice: VoiceChain


@dataclass(frozen=True)
class QaSection:
    min_transcript_match: float
    lufs_tolerance: float
    max_tp: float
    max_av_delta_ms: int


@dataclass(frozen=True)
class StoryboardSection:
    min_beat_ms: int


@dataclass(frozen=True)
class IngestSection:
    warn_duration_h: float
    max_duration_h: float


@dataclass(frozen=True)
class PrivacySection:
    """What Claude is not allowed to read: with `mask_pii`, phone, ID and card numbers and e-mail
    addresses are masked in `transcripcion.md` and `palabras.tsv` (spec 001.13)."""

    mask_pii: bool


@dataclass(frozen=True)
class ProjectConfig:
    project: ProjectSection
    output: OutputSection
    brand: BrandSection
    transcribe: TranscribeSection
    analysis: AnalysisSection
    sync: SyncSection
    captions: CaptionsSection
    audio: AudioSection
    qa: QaSection
    storyboard: StoryboardSection
    glossary: tuple[str, ...]
    ingest: IngestSection
    privacy: PrivacySection


PRESET_SIZES: Mapping[str, tuple[int, int]] = {"9:16": (1080, 1920), "16:9": (1920, 1080)}

SECTIONS = {
    "project",
    "output",
    "brand",
    "glossary",
    "transcribe",
    "analysis",
    "sync",
    "captions",
    "audio",
    "qa",
    "storyboard",
    "ingest",
    "privacy",
}
DEFAULT_FILLERS = ("eh", "ehh", "em", "emm", "mmm", "este", "o sea", "pues", "bueno", "entonces")
WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")
COMPUTE_TYPES = ("int8", "int8_float32", "float32")
SAFE_DEFAULTS = {"9:16": (250, 500), "16:9": (60, 120)}
