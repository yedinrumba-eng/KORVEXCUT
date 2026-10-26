"""Text of the `kcut.toml` that `kcut new` writes (comments in Spanish, spec S1.2)."""

import json

from kcut.config.model import DEFAULT_FILLERS, SAFE_DEFAULTS

ENGLISH_FILLERS = ("uh", "um", "uhm", "er", "hmm")


def render_template(name: str, preset: str, fps: int, language: str, created: str) -> str:
    """Return the exact `kcut.toml` text. Strings go through `json.dumps` (valid TOML escapes)."""
    top, bottom = SAFE_DEFAULTS.get(preset, SAFE_DEFAULTS["9:16"])
    fillers = ENGLISH_FILLERS if language == "en" else DEFAULT_FILLERS
    return _TEMPLATE.format(
        name=_q(name),
        language=_q(language),
        created=_q(created),
        preset=_q(preset),
        fps=fps,
        top=top,
        bottom=bottom,
        fillers="[" + ", ".join(_q(f) for f in fillers) + "]",
    )


def _q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


_TEMPLATE = """\
# kcut.toml - configuracion de este video
[project]
name = {name}
language = {language}          # idioma principal (subtitulos, muletillas); Whisper detecta por clip
created = {created}

[output]
preset = {preset}          # "9:16" = 1080x1920 · "16:9" = 1920x1080
fps = {fps}                 # 24, 25, 30, 48, 50 o 60
safe_top_px = {top}
safe_bottom_px = {bottom}

[brand]
accent = "#E5FF1F"
accent2 = "#2FA8FF"      # palabra activa de los subtitulos
dark = "#0B0B0E"
light = "#FFFFFF"

[glossary]
terms = []

[transcribe]
model = "medium"
compute_type = "int8"
beam_size = 5
cpu_threads = 0
fillers = {fillers}
prompt_extra = ""

[analysis]
silence_db = -42.0
min_silence_ms = 250
phrase_pause_ms = 300
long_pause_ms = 700
low_prob = 0.5

[sync]
master = ""
min_score = 0.35
min_ratio = 1.5
max_drift_ms = 20
min_refine_corr = 0.1

[sync.manual]

[captions]
enabled = true
uppercase = true
max_words = 3
max_chars = 18
y = 0.617
font_px = 76
color = "#FFFFFF"
active_color = ""
stroke_color = ""

[audio]
voice_lufs = -16.0
target_lufs = -14.0
target_tp = -1.5

[audio.voice]
highpass_hz = 80
denoise_nr = 10.0
denoise_nf = -40.0
comp_threshold_db = -18.0
comp_ratio = 3.0

[qa]
min_transcript_match = 0.80
lufs_tolerance = 1.0
max_tp = -1.0
max_av_delta_ms = 25

[storyboard]
min_beat_ms = 500

[privacy]
mask_pii = true          # tapa telefonos, cedulas, tarjetas y correos en lo que lee Claude

[ingest]
warn_duration_h = 3
max_duration_h = 12
"""
