"""The `kcut.toml` that `kcut new` writes for 9:16 and Spanish (text of the spec)."""

GOLDEN_9X16 = """\
# kcut.toml - configuracion de este video
[project]
name = "piloto-01"
language = "es"          # idioma principal (subtitulos, muletillas); Whisper detecta por clip
created = "2026-10-16"

[output]
preset = "9:16"          # "9:16" = 1080x1920 · "16:9" = 1920x1080
fps = 30                 # 24, 25, 30, 48, 50 o 60
safe_top_px = 250
safe_bottom_px = 500

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
fillers = ["eh", "ehh", "em", "emm", "mmm", "este", "o sea", "pues", "bueno", "entonces"]
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
