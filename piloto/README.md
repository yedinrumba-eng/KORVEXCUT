# piloto/ — scripts de referencia (NO son el producto)

Los scripts con que se editó a mano el piloto 01. Están **amarrados a ese video**: los cortes (`edl.py` ITEMS), las correcciones de texto (`cues.py` FIX_AT), las ventanas de la mano (`track.py` WINDOWS), los tiempos de los gráficos (`gfx/overlay.html`) y las rutas (`mezz.sh`). Sirven como referencia para implementar el motor `kcut` de F1; no se mantienen.

| Script | Qué hace | Pasa a |
|---|---|---|
| `sync.py` | Offset entre dos grabaciones por correlación de la envolvente (FFT) + refinado en audio crudo | `kcut ingest` |
| `mezz.sh` | Intermedios SDR/CFR en una línea de tiempo común (tone-map HLG→bt709) | `kcut ingest` |
| `transcribe.py` | faster-whisper por palabra, cronometrado | `kcut transcribe` |
| `view.py` | PNG con envolvente RMS, silencios por energía y palabras | `kcut view` |
| `edl.py` | Línea de tiempo en frames enteros (clips de voz, huecos, planos por cámara) | formato EDL + `kcut render` |
| `cues.py` | Mapea palabras de origen a tiempo de salida: cues, subtítulos, plan de SFX | `kcut render` |
| `audio.py` | Voz con precisión de muestra + SFX sintetizados (whoosh, boom, pop, kick, pad, 8-bit…) | `kcut render` |
| `music.py` | Música sintetizada sin licencia, 120 BPM | F3 |
| `compose.py` | Compositor frame a frame (encuadre, zoom, inserto de pantalla) con matrices bt709 explícitas | `kcut render` |
| `track.py` | Rastreo de la palma con flujo óptico LK | F2 |
| `capture.py` | Captura la capa de gráficos HTML a PNG con alfa (Playwright + CDP) | `kcut render` |
| `gfx/overlay.html` | Capa de gráficos determinista (`window.seek(t)`) | plantillas F2 |
| `qa.py` | Frames, A/V, loudness, negros/congelados, re-transcripción contra lo esperado, hoja de contacto | `kcut qa` |

Requisitos para correrlos: Python 3.12 con `numpy scipy opencv-python Pillow faster-whisper playwright`, y ffmpeg "full" en el PATH. En Windows, usar `python -I -X utf8`.
