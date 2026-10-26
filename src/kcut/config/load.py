"""Strict `kcut.toml` loader: unknown keys and out-of-range values fail naming their path."""

import re
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

from kcut.config.fields import check_clean, hex_or_empty, string_list, valid_date
from kcut.config.model import (
    COMPUTE_TYPES,
    DEFAULT_FILLERS,
    PRESET_SIZES,
    SAFE_DEFAULTS,
    SECTIONS,
    WHISPER_MODELS,
    AnalysisSection,
    AudioSection,
    BrandSection,
    CaptionsSection,
    IngestSection,
    OutputSection,
    PrivacySection,
    ProjectConfig,
    ProjectSection,
    QaSection,
    StoryboardSection,
    TranscribeSection,
    VoiceChain,
)
from kcut.config.names import NAME_MAX, clean_default_name, has_forbidden_chars
from kcut.config.sync_section import build_sync
from kcut.errors import ProjectError
from kcut.jsonio import MAX_TOML_BYTES, read_capped
from kcut.schema_util import (
    SchemaError,
    describe_value,
    hex_color,
    join_path,
    obj,
    one_of,
    only_keys,
    opt_bool,
    opt_float,
    opt_int,
    opt_str,
    project_error,
)
from kcut.timebase import ALLOWED_FPS, MAX_TIME_MS

_LANG = re.compile(r"[a-z]{2}")
_MAX_HOURS = MAX_TIME_MS / 3_600_000  # 48.0: the same cap the inventory puts on stored times
MAX_FILLER_WORDS = 5  # words of one `transcribe.fillers` entry (001.18, point 6)


def load_config(path: Path) -> ProjectConfig:
    """Load and validate `kcut.toml`; every failure is a ProjectError (exit 3)."""
    try:
        text = read_capped(path, MAX_TOML_BYTES).decode("utf-8")
    except FileNotFoundError:
        raise ProjectError(f"no existe {path}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ProjectError(f"no pude leer {path}: {exc}") from None
    return parse_config(text, default_name=path.resolve().parent.name, source=path.name)


def parse_config(text: str, *, default_name: str, source: str = "kcut.toml") -> ProjectConfig:
    """Validate the text of a `kcut.toml`. `default_name` fills `project.name` when absent."""
    try:
        return _build(tomllib.loads(text), default_name)
    except tomllib.TOMLDecodeError as exc:
        raise ProjectError(f"{source}: TOML mal formado: {exc}") from None
    except SchemaError as exc:
        raise project_error(source, exc) from None
    except ValueError as exc:  # an integer of thousands of digits: Python caps `int()` at 4300
        raise ProjectError(
            f"{source}: número con demasiados dígitos o valor no válido ({exc})"
        ) from None


def _build(data: dict[str, Any], default_name: str) -> ProjectConfig:
    only_keys(data, SECTIONS, "")
    output = _output(_section(data, "output"))
    return ProjectConfig(
        project=_project(_section(data, "project"), default_name),
        output=output,
        brand=_brand(_section(data, "brand")),
        transcribe=_transcribe(_section(data, "transcribe")),
        analysis=_analysis(_section(data, "analysis")),
        sync=build_sync(_section(data, "sync")),
        captions=_captions(_section(data, "captions")),
        audio=_audio(_section(data, "audio")),
        qa=_qa(_section(data, "qa")),
        storyboard=StoryboardSection(
            min_beat_ms=_storyboard_beat(_section(data, "storyboard")),
        ),
        glossary=_glossary(_section(data, "glossary")),
        ingest=_ingest(_section(data, "ingest")),
        privacy=_privacy(_section(data, "privacy")),
    )


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    return obj(data.get(name, {}), name)


def _project(d: dict[str, Any], default_name: str) -> ProjectSection:
    only_keys(d, {"name", "language", "created"}, "project")
    name = opt_str(d, "name", "project", clean_default_name(default_name), NAME_MAX, 1)
    if has_forbidden_chars(name):
        raise SchemaError(
            "project.name",
            "no puede llevar saltos de línea, separadores ni caracteres de control o de formato",
        )
    language = opt_str(d, "language", "project", "es")
    if _LANG.fullmatch(language) is None:
        raise SchemaError(
            "project.language", f"debe ser un código de 2 letras (vino {describe_value(language)})"
        )
    created = opt_str(d, "created", "project", date.today().isoformat())
    if not valid_date(created):
        raise SchemaError(
            "project.created", f"debe ser una fecha AAAA-MM-DD (vino {describe_value(created)})"
        )
    return ProjectSection(name=name, language=language, created=created)


def _output(d: dict[str, Any]) -> OutputSection:
    only_keys(d, {"preset", "fps", "safe_top_px", "safe_bottom_px"}, "output")
    preset = one_of(opt_str(d, "preset", "output", "9:16"), PRESET_SIZES, "output.preset")
    fps = opt_int(d, "fps", "output", 30)
    if fps not in ALLOWED_FPS:
        allowed = ", ".join(str(f) for f in sorted(ALLOWED_FPS))
        raise SchemaError("output.fps", f"debe ser uno de: {allowed} (vino {fps})")
    top, bottom = SAFE_DEFAULTS[preset]
    w, h = PRESET_SIZES[preset]
    return OutputSection(
        preset=preset,
        fps=fps,
        w=w,
        h=h,
        safe_top_px=opt_int(d, "safe_top_px", "output", top, 0, 600),
        safe_bottom_px=opt_int(d, "safe_bottom_px", "output", bottom, 0, 600),
    )


def _brand(d: dict[str, Any]) -> BrandSection:
    only_keys(d, {"accent", "accent2", "dark", "light"}, "brand")
    defaults = {"accent": "#E5FF1F", "accent2": "#2FA8FF", "dark": "#0B0B0E", "light": "#FFFFFF"}
    colors = {k: hex_color(d.get(k, v), join_path("brand", k)) for k, v in defaults.items()}
    return BrandSection(**colors)


def _glossary(d: dict[str, Any]) -> tuple[str, ...]:
    only_keys(d, {"terms"}, "glossary")
    return string_list(d, "terms", "glossary", max_items=200, max_len=40, clean=True)


def _transcribe(d: dict[str, Any]) -> TranscribeSection:
    keys = {"model", "compute_type", "beam_size", "cpu_threads", "fillers", "prompt_extra"}
    only_keys(d, keys, "transcribe")
    prompt_extra = opt_str(d, "prompt_extra", "transcribe", "", max_len=400)
    check_clean(prompt_extra, "transcribe.prompt_extra")
    return TranscribeSection(
        model=one_of(
            opt_str(d, "model", "transcribe", "medium"), WHISPER_MODELS, "transcribe.model"
        ),
        compute_type=one_of(
            opt_str(d, "compute_type", "transcribe", "int8"),
            COMPUTE_TYPES,
            "transcribe.compute_type",
        ),
        beam_size=opt_int(d, "beam_size", "transcribe", 5, 1, 10),
        cpu_threads=opt_int(d, "cpu_threads", "transcribe", 0, 0, 64),
        fillers=string_list(  # the same bounds as glossary.terms (001.12, point 11)
            d,
            "fillers",
            "transcribe",
            max_items=200,
            max_len=40,
            max_words=MAX_FILLER_WORDS,
            default=DEFAULT_FILLERS,
            clean=True,
        ),
        prompt_extra=prompt_extra,
    )


def _analysis(d: dict[str, Any]) -> AnalysisSection:
    keys = {"silence_db", "min_silence_ms", "phrase_pause_ms", "long_pause_ms", "low_prob"}
    only_keys(d, keys, "analysis")
    phrase = opt_int(d, "phrase_pause_ms", "analysis", 300, 100, 3000)
    long_pause = opt_int(d, "long_pause_ms", "analysis", 700, hi=10000)
    if long_pause < phrase:
        raise SchemaError(
            "analysis.long_pause_ms",
            f"debe ser como mínimo phrase_pause_ms ({phrase}) (vino {long_pause})",
        )
    return AnalysisSection(
        silence_db=opt_float(d, "silence_db", "analysis", -42.0, -70.0, -20.0),
        min_silence_ms=opt_int(d, "min_silence_ms", "analysis", 250, 50, 2000),
        phrase_pause_ms=phrase,
        long_pause_ms=long_pause,
        low_prob=opt_float(d, "low_prob", "analysis", 0.5, 0.0, 1.0),
    )


def _captions(d: dict[str, Any]) -> CaptionsSection:
    keys = {"enabled", "uppercase", "max_words", "max_chars", "y", "font_px"}
    only_keys(d, keys | {"color", "active_color", "stroke_color"}, "captions")
    return CaptionsSection(
        enabled=opt_bool(d, "enabled", "captions", True),
        uppercase=opt_bool(d, "uppercase", "captions", True),
        max_words=opt_int(d, "max_words", "captions", 3, 1, 6),
        max_chars=opt_int(d, "max_chars", "captions", 18, 6, 40),
        y=opt_float(d, "y", "captions", 0.617, 0.0, 1.0),
        font_px=opt_int(d, "font_px", "captions", 76, 24, 200),
        color=hex_color(d.get("color", "#FFFFFF"), "captions.color"),
        active_color=hex_or_empty(d, "active_color", "captions"),
        stroke_color=hex_or_empty(d, "stroke_color", "captions"),
    )


def _audio(d: dict[str, Any]) -> AudioSection:
    only_keys(d, {"voice_lufs", "target_lufs", "target_tp", "voice"}, "audio")
    voice = obj(d.get("voice", {}), "audio.voice")
    only_keys(
        voice,
        {"highpass_hz", "denoise_nr", "denoise_nf", "comp_threshold_db", "comp_ratio"},
        "audio.voice",
    )
    path = "audio.voice"
    return AudioSection(
        voice_lufs=opt_float(d, "voice_lufs", "audio", -16.0, -30.0, -10.0),
        target_lufs=opt_float(d, "target_lufs", "audio", -14.0, -24.0, -9.0),
        target_tp=opt_float(d, "target_tp", "audio", -1.5, -3.0, -0.5),
        voice=VoiceChain(
            highpass_hz=opt_int(voice, "highpass_hz", path, 80, 20, 300),
            denoise_nr=opt_float(voice, "denoise_nr", path, 10.0, 0.0, 40.0),
            denoise_nf=opt_float(voice, "denoise_nf", path, -40.0, -80.0, -20.0),
            comp_threshold_db=opt_float(voice, "comp_threshold_db", path, -18.0, -40.0, 0.0),
            comp_ratio=opt_float(voice, "comp_ratio", path, 3.0, 1.0, 20.0),
        ),
    )


def _qa(d: dict[str, Any]) -> QaSection:
    keys = {"min_transcript_match", "lufs_tolerance", "max_tp", "max_av_delta_ms"}
    only_keys(d, keys, "qa")
    return QaSection(
        min_transcript_match=opt_float(d, "min_transcript_match", "qa", 0.80, 0.0, 1.0),
        lufs_tolerance=opt_float(d, "lufs_tolerance", "qa", 1.0, 0.1, 3.0),
        max_tp=opt_float(d, "max_tp", "qa", -1.0, -6.0, 0.0),
        max_av_delta_ms=opt_int(d, "max_av_delta_ms", "qa", 25, 0, 200),
    )


def _privacy(d: dict[str, Any]) -> PrivacySection:
    only_keys(d, {"mask_pii"}, "privacy")
    return PrivacySection(mask_pii=opt_bool(d, "mask_pii", "privacy", True))


def _ingest(d: dict[str, Any]) -> IngestSection:
    only_keys(d, {"warn_duration_h", "max_duration_h"}, "ingest")
    warn = opt_float(d, "warn_duration_h", "ingest", 3.0, 0.1, _MAX_HOURS)
    longest = opt_float(d, "max_duration_h", "ingest", 12.0, 0.1, _MAX_HOURS)
    if longest < warn:
        raise SchemaError(
            "ingest.max_duration_h",
            f"debe ser como mínimo warn_duration_h ({warn}) (vino {longest})",
        )
    return IngestSection(warn_duration_h=warn, max_duration_h=longest)


def _storyboard_beat(d: dict[str, Any]) -> int:
    only_keys(d, {"min_beat_ms"}, "storyboard")
    return opt_int(d, "min_beat_ms", "storyboard", 500, 0, 5000)
