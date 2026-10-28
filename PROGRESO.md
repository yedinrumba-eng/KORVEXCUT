# PROGRESO — KORVEXCUT

> Bitácora. Se marca al cerrar cada slice, no antes.
> Leyenda: `[x]` cerrado y verificado · `[~]` en curso · `[ ]` pendiente · `[!]` bloqueado

---

## Fases

### F0 — Concepto + piloto

- [x] **S0.1** — Investigación de repos de referencia (video-use, HyperFrames, Remotion, awesome-claude-video-skills) → `docs/research/`
- [x] **S0.2** — Diseño aprobado por secciones: arquitectura (repo solo código, trabajo fuera de git), pipeline con 2 puertas, revisión por chat + ficha de versiones
- [x] **S0.3** — Piloto 01 editado de punta a punta (v1→v4)
      · verificado: `qa.py salida/v4.mp4` → 1469/1469 frames, A/V 0 ms, −14.4 LUFS, pico −1.4 dBFS

### F1a — Motor `kcut` (spec [`docs/specs/001-motor-kcut.md`](docs/specs/001-motor-kcut.md), aprobado 16/10/2026)

- [x] **S1.1** — Andamiaje del paquete + `kcut doctor`
      · verificado: `kcut doctor --json` → 11/11 ok · `pytest -q -ra` → 154 passed, 1 skipped
- [x] **S1.2** — `kcut new` + `kcut ingest` (inventario, HDR/VFR, sincronía multicam, proxies)
      · verificado: `pytest -q -ra` → 1238 passed, 3 skipped · suite rápida → 1108 passed en 70 s
- [x] **S1.3** — `kcut transcribe` + `kcut pack`
      · verificado: pytest -q -ra → 2332 passed, 3 skipped (5 rondas de revisión)
- [x] **S1.4** — `kcut view` + `kcut frames`
      · verificado: suite completa → 2968 passed, 3 skipped (456.59 s, exit 0) · ruff check, ruff format, mypy OK · 3 rondas + paso 0 de PII (001.18–001.21)
- [x] **S1.5a** — (parte a de S1.5, 001.15) EDL en frames: modelo, validación, `kcut edl check`, `kcut edl sources`, `kept_words`, geometría
      · verificado: suite completa → 3331 passed, 3 skipped (implementador 442.57 s; verificador 606.77 s; exit 0 en ambas) · ruff check, ruff format y mypy OK · 1 ronda de revisión + paso 0 (001.22–001.23)
- [x] **S1.5b** — (parte b de S1.5, 001.15) `kcut render` base (cámaras, insertos, looks, frame fx, tarjetas, mezzanines por tramo, voz exacta, lock, mux A/V) · paso 0 = spec 001.24
      · verificado: suite completa → 3943 passed, 3 skipped (3025.40 s; exit 0) · criterios S1.5b 1–59 exit 0 · ruff check, ruff format y mypy OK · 3 rondas de revisión (parches 001.25–001.27) + paso 0 (001.24)
- [x] **S1.6a** — (parte a de S1.6) Capa de gráficos: motor HTML `seek(t)` + componentes base + subtítulos · paso 0 = spec 001.27
      · verificado: suite completa → 4432 passed, 4 skipped in 1008.43 s (0:16:48), exit 0 (los 4 skips son de symlinks sin privilegio, WinError 1314, aceptados) · fila 17 (`-k workfiles_concurrent`) 3 corridas sueltas → 7 passed las 3 · ruff check, ruff format y mypy limpios · ningún .py pasa de 300 líneas · 2 rondas de revisión + paso 0 (001.27)
- [x] **S1.6b** — (parte b de S1.6) Capa de gráficos: motor HTML `seek(t)` + componentes base + subtítulos · paso 0 = spec 001.30
      · verificado: suite completa → 4918 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio, WinError 1314) · fila S1.6a-17 (`-k workfiles_concurrent`) 10 de 10 en ronda 2 y 3 de 3 en revisión 3 · ruff check, ruff format y mypy limpios · ningún .py pasa de 300 líneas · 3 rondas de revisión + paso 0 (001.30); parches 001.31 a 001.33
- [x] **S1.7** — Componentes de lucimiento (pasos, sticker, holograma, globo)
      · verificado: suite completa → 5082 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio) · A/B de screenshot contra `f8f728f`: 33.41 vs 33.30 ms/frame (1.003×, medido por el verificador) · primera revisión: verificador y seguridad aprobaron, 0 CRÍTICO y 0 ALTO · paso 0 = filas 9–18 · BLOQUEADOs B1 y B2 decididos en 001.34; cierre en 001.35
      · pendiente para Yedin (no bloquea): mirar los 4 stills de S1.7 en `C:\Users\Yedin\AppData\Local\Temp\kcut-showpieces\qa\showpieces\` (`still_000240.png` pasos, `still_000195.png` mascota/sticker, `still_000292.png` holo, `still_000297.png` mundo/globo)
- [x] **S1.8a** — (parte a de S1.8) Audio: SFX sintetizados, esquema de `sfx.json`, eventos, bus y ganancia
      · verificado: suite completa → 5380 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio) · verificador: 18 casos con `array_equal`, maxdiff 0 (13 efectos portados bit a bit de `piloto/audio.py`) · primera revisión: verificador y seguridad aprobaron, 0 CRÍTICO y 0 ALTO · paso 0 = filas 8–19 · cierre en 001.36 (punto 11: "pico ≤ 1" no es contrato por SFX suelto)
- [x] **S1.8b** — (parte b de S1.8) Audio: música, loudnorm, ducking, mezcla y `kcut mix`
      · verificado: suite completa → 5788 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio) · ducking 60/60 corridas idénticas (verificador) y 108/108 (seguridad) · diez corridas completas de `kcut mix` dieron los 8 archivos idénticos · fila 5 pasó 8/8 · diferencia 0 con la cuantización del piloto · revisión 1: seguridad aprobó, verificador con 1 CRÍTICO y 1 ALTO de la misma raíz → ronda 1 (001.37) · revisión 2: 0 CRÍTICO y 0 ALTO en ambos · paso 0 = filas 12–23 (001.36) · cierre en 001.38
- [ ] **S1.9a** — (parte a de S1.9) `kcut qa` + `kcut build` + `kcut catalog` + e2e sintético
- [ ] **S1.9b** — (parte b de S1.9) `kcut qa` + `kcut build` + `kcut catalog` + e2e sintético
- [ ] **S1.10** — `kcut storyboard` (Puerta 1 visual)

Cada slice se cierra con sus criterios del spec en ✅ y la salida real pegada.

### F1b — Experiencia (spec 002, por escribir)

Plugin de Claude Code, entrevista, menú de ideas (desde `kcut catalog`), agente buscador de assets, comandos `/korvexcut:*`, prueba de aceptación con un segundo video real.

---

## Bitácora

| Fecha | Slice | Qué se cerró | Verificado con |
|---|---|---|---|
| 13/10/2026 | S0.1 | Reporte de 4 repos + mapa de lo que hay en la máquina | lectura de código con `gh api` (no ejecución) |
| 14/10/2026 | S0.3 | Piloto v1 (48.4 s) | `qa.py` → 1452 frames, A/V 0 ms, −14.2 LUFS |
| 15/10/2026 | S0.3 | Piloto v2–v4: subtítulos azules, beat en el inserto, mascota 3D rastreada sobre la palma, holograma, música con ducking | `qa.py` → 1469 frames, A/V 0 ms, −14.4 LUFS |
| 16/10/2026 | S1.1 | Paquete kcut 0.1.0 + `kcut doctor`; 3 rondas de revisión (3 ALTO cerrados) | `kcut doctor --json` → exit 0; `pytest -q -ra` → 154 passed, 1 skipped |
| 16/10/2026 | S1.2 | kcut new + kcut ingest; 3 rondas de revisión (1 CRÍTICO, 2 ALTO cerrados); parches 001.4–001.6 | ronda 3: pytest → 987 passed, 3 skipped |
| 17/10/2026 | S1.2 | Merge de la deuda de S1.1 (001.3) y deuda de S1.2 pagada (001.7–001.9): sync ambiguo, logs, higiene de consola, topes de 48 h | pytest -q -ra → 1238 passed, 3 skipped |
| 17–26/10/2026 | S1.3 | kcut transcribe + pack; 5 rondas; PII enmascarada; endurecimiento ante inyección de prompt | pytest -q -ra → 2332 passed, 3 skipped |
| 26/10/2026 | S1.4 | kcut view + kcut frames (timeline PNG con cajas de palabras enmascaradas, filmstrip, frames y hoja ≤25 Mpx sin upscale, `FrameReader` con topes de 60 s y 64 MB, `PROXY_MISMATCH`, escritura fuera de `.kcut/` sin `--force`); PII: paso 0 + 3 rondas (001.18–001.21); revisión final aprobada (verificador y seguridad, 0 CRÍTICO, 0 ALTO); commit `40e9c65` pusheado a `origin/main` | suite completa → 2968 passed, 3 skipped (456.59 s, exit 0); suite rápida (implementador) → 2719 passed, 3 skipped, 249 deselected (87.20 s); ruff check, ruff format y mypy limpios; ningún archivo pasa de 300 líneas; criterios S1.4 1–41 exit 0 |
| 26/10/2026 | S1.5a | EDL en frames: modelo, validación, `kcut edl check` (`--json`) y `kcut edl sources`, `kept_words`, geometría; gate que cierra a `no` ante cualquier duda; paso 0 (001.22–001.23); BLOQUEADO del implementador por ejemplos del spec mal escritos (001.23, lección 21); 1 ronda de revisión (verificador y seguridad APROBADOS, 0 CRÍTICO, 0 ALTO); commit `6605456` pusheado a `origin/main` | suite completa → 3331 passed, 3 skipped (implementador 442.57 s; verificador 606.77 s; exit 0 en ambas) · ruff check, ruff format y mypy limpios · ningún archivo pasa de 300 líneas · criterios S1.5a 1–26 exit 0 |
| 27/10/2026 | S1.5b | `kcut render` base: cámaras e insertos, looks, frame fx y tarjetas de pantalla; mezzanines por tramo con sidecar de frames reales, parciales con pid y aterrizaje seguro entre procesos; pista de voz exacta a la muestra desde el wav48, con fades; lock por versión del build y mux A/V a `render.mp4`; guardas de destino y de enlaces en `.kcut/build/vN`; prefijo `\\?\` quitado en la guarda de caché; paso 0 de 001.24 (deuda 33) incluido; 3 rondas de revisión (ronda 1: 1 ALTO del verificador y 2 ALTO de seguridad; ronda 2: 2 ALTO del verificador, seguridad aprobó; ronda 3: 0 CRÍTICO y 0 ALTO, aprobaron los dos); los BAJO de la ronda 3 van al paso 0 de S1.6a (001.27, puntos 1–9); commit `1d8cf00` pusheado a `origin/main`, que quedó en `a46223d` (specs 001.24–001.27: `5076880`, `6ee21f8`, `7651209`, `a46223d`) | suite completa → 3943 passed, 3 skipped in 3025.40s (0:50:25), exit 0 (los 3 skipped son por falta de privilegio para symlinks en Windows); ruff check src tests → All checks passed!; ruff format --check src tests → 313 files already formatted; mypy → Success: no issues found in 124 source files; tope de 300 líneas → `[]`; criterios S1.5b 1–59 exit 0; repros de concurrencia: stagger_row39 8/8 y wav48_race 5/5 con `[0, 0]`; mezzanine corto 3/3 exit 0 |
| 27/10/2026 | S1.6a | Capa de gráficos hasta la página HTML: esquema de `graphics.json` con anclas y parámetros, subtítulos por chunks, resolución de cues a frames de salida, imágenes aprobadas, página con runtime JS y 5 componentes base, `kcut graphics check` (G01–G12, JSON enmascarado); paso 0 de 001.27 incluido (barrido de parciales huérfanos, `encoding=` obligatorio, chequeos de `build/vN`, `write_json_exclusive`, hard links marcados como stale); 2 rondas de revisión (ronda 1: verificador 1 CRÍTICO (los errores de `wavio` sacaban la ruta del wav48, con slug y teléfono), seguridad 2 MEDIO y 4 BAJO, implementador BLOQUEADO en fila 17; ronda 2: verificador y seguridad 0 CRÍTICO y 0 ALTO, segundo BLOQUEADO del implementador en fila 17); commits `fdb19a3` y `3261492` pusheados a `origin/main` | suite completa → 4432 passed, 4 skipped in 1008.43 s (0:16:48), exit 0 (los 4 skips son de symlinks sin privilegio, WinError 1314, aceptados); fila 17 `-k workfiles_concurrent` 3 corridas sueltas → 7 passed las 3; ruff check, ruff format y mypy limpios; ningún .py pasa de 300 líneas; verificación final del verificador |
| 27/10/2026 | S1.6b | Captura de gráficos con Chromium headless (sandbox encendido, sin red por `context.route` y CSP, WebRTC sin UDP directo); cada cuadro se dibuja en una PNG de capa en `.kcut/build/vN/gfx/` con `index.json` por hash de página; `kcut render` mezcla la capa sobre el corte; `kcut graphics capture` y `kcut graphics still` (máx. 60 cuadros por llamada, timeout de 30 s por cuadro); el chequeo de disco cuenta la capa; cada carpeta de caché debe resolver a sí misma y se revisa antes de cada escritura, borrado y lectura de la capa (un hard link no es capa válida); sidecar de work file y mezzanine aterrizan igual que el archivo; módulos neutros `build_folder`, `refuse_edl`, `proxy_of`, `fx_context`; paso 0 = spec 001.30 (filas 13–18); 3 rondas de revisión: ronda 1 (verificador 1 ALTO de antes de S1.6b: con dos renders a la vez, Windows rechazaba el sidecar del wav48 mientras el otro render lo leía, 2 fallos en 14 corridas de S1.6a-17; seguridad 0 ALTO, 5 MEDIO, 6 BAJO) → 001.31 (filas 19–31); ronda 2 (verificador 1 ALTO: `OSError` al arrancar Playwright con driver faltante daba exit 10 en vez de 7) → 001.32 (filas 32–40; además, URL de página comparada distinguiendo mayúsculas, que rompía un host UNC; dígitos de teléfono tras cualquier separador en un nombre de archivo; `809.555.1234` como nombre de archivo sin extensión real); ronda 3: 0 CRÍTICO y 0 ALTO en ambos revisores; código en commit `f8f728f` y spec `b564a45` (001.33) pusheados, `origin/main` en `b564a45` | suite completa → 4918 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio, WinError 1314); fila S1.6a-17 (`-k workfiles_concurrent`) 10 de 10 en ronda 2 y 3 de 3 en ronda 3; verificador: 11 mutaciones en memoria, cada una rompe el test de su fila; ruff check, ruff format y mypy limpios; ningún .py pasa de 300 líneas (`ingest/workfiles.py` queda en 300, S1.7 paso 0 lo parte) |
| 28/10/2026 | S1.7 | Componentes de lucimiento parametrizados: `steps`, `sticker`, `holo_board` y `globe`; cada uno reconstruye sus nodos en cada seek, así que un cuadro da los mismos píxeles sin importar qué se capturó antes (lección 36); `ParamSpec` gana `kind="object"` y `nullable` (`sticker.fly_to` y `holo_board.accent_index`); fixture `tests/fixtures/showpiece_stills.py` con 4 stills para revisión visual; paso 0 = filas 9–18, que cierra los hallazgos de la revisión de S1.6b (deuda 47); BLOQUEADOs B1 (timeout de screenshot con `page.screenshot`, 1.88× por cuadro: se mantuvo la captura CDP rápida y la amenaza la cierran las reglas de JS) y B2 (`fly_to` y `accent_index` no encajaban en `ParamSpec`) decididos por el coordinador en 001.34; código en commit `78a2b19` y spec 001.35 en `2a56b40`, pusheados (`origin/main` en `2a56b40`) | suite completa → 5082 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio); A/B de screenshot contra `f8f728f`: 33.41 vs 33.30 ms/frame (1.003×), medido por el verificador; primera revisión: verificador y seguridad aprobaron, 0 CRÍTICO y 0 ALTO |
| 28/10/2026 | S1.8a | SFX sintetizados (la mitad SFX del audio): 13 efectos portados bit a bit de `piloto/audio.py`, biblioteca con defaults y notas de catálogo, esquema `edit/sfx.json` con códigos A01–A08, eventos resueltos contra el EDL (anclas de palabra y de fuente, `align`, defaults), bus de SFX sin normalización global, ventanas de ganancia con rampas y fixture `write_sfx_plan`; paso 0 = filas 8–19, que cierra los hallazgos de la revisión de S1.7 (deuda 48); criterio "pico ≤ 1" aclarado en 001.36 (punto 11); código en commit `4e996cc` y spec 001.36 en `1a95ef5`, pusheados (`origin/main` en `1a95ef5`) | suite completa → 5380 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio); verificador: 18 casos con `array_equal`, maxdiff 0; primera revisión: verificador y seguridad aprobaron, 0 CRÍTICO y 0 ALTO |
| 28/10/2026 | S1.8b | Audio, la mitad música: acordes y síntesis portados de `piloto/music.py`, música de `recursos/` aprobada en el manifiesto con el gate M04, `edit/music.json` con códigos M01–M05, loudnorm de dos pasadas, grafo de mezcla con ducking, mezclador y `kcut mix`; paso 0 = filas 12–23 (cierra la deuda 51); revisión 1: seguridad aprobó, verificador con 1 CRÍTICO y 1 ALTO de la misma raíz (el grafo de ducking no era determinista: 5 salidas distintas en 100 corridas idénticas, y 61 perdieron hasta 0.49 s de la cola de la música) → ronda 1 (001.37: `apad` en las dos entradas del compresor, timeout en cada llamada a ffmpeg, chequeo de disco antes de mezclar, `MemoryError` da exit 3, `-protocol_whitelist file`, y los MEDIO/BAJO de seguridad); revisión 2: 0 CRÍTICO y 0 ALTO en ambos; código en commit `a0ffe90`, spec 001.36 en `1a95ef5` y 001.37–001.38 en `af7cb07`, pusheados (`origin/main` en `af7cb07`) | suite completa → 5788 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio); ducking 60/60 corridas idénticas (verificador) y 108/108 (seguridad); diez corridas completas de `kcut mix` dieron los 8 archivos idénticos; fila 5 pasó 8/8; diferencia 0 con la cuantización del piloto |

---

## Deuda técnica

Ordenada por lo que más duele.

### 1. Los scripts del piloto están amarrados a un solo video 🔴

Los cortes (`edl.py` ITEMS), las correcciones de texto (`cues.py` FIX_AT), las posiciones de la mano (`track.py` WINDOWS) y los tiempos de los gráficos se escribieron a mano para el piloto 01.

- **Mitigado hoy por:** nada; por eso todavía no hay versión instalable.
- **Cura real:** F1 completo: Claude escribe EDL/cues/gráficos por video y `kcut` los ejecuta — ~8-10 slices.
- **Cuándo:** ahora (F1).

### 2. Conversión HDR lenta (~5× tiempo real) 🟡

Tone-mapping `zscale` + `tonemap` en CPU a 1440×2560. La vía GPU (`libplacebo` en Vulkan) falla en Iris Xe.

- **Mitigado hoy por:** corre en segundo plano y solo sobre las ventanas útiles del crudo.
- **Cura real:** convertir solo los tramos del EDL aprobado; probar `tonemap_opencl` — ~3 h.
- **Cuándo:** S1.5 (mezzanines por tramo del EDL). S1.2 solo convierte los proxies, que son chicos.

### 3. Intermedio a 1440×2560 deja poco margen para reencuadrar 🟡

Con zoom 1.55 se escala un poco hacia arriba.

- **Cura real:** intermedio a 1800×3200, o recortar desde el 4K solo los planos con zoom — ~2 h.
- **Cuándo:** S1.5 (DS12 del spec: la resolución del mezzanine sale del zoom máximo usado).

### 4. Muletillas en español sin medir 🟡

En el piloto casi no hubo "eh/este", así que no se pudo medir si Whisper las conserva.

- **Cura real:** probar con un crudo lleno de muletillas; plan B: huecos de energía o ElevenLabs Scribe con tope de gasto — ~2 h.
- **Cuándo:** S1.3 implementó las marcas de muletilla con tests sintéticos; la medición con habla real queda para la prueba de aceptación del spec 002 (segundo video real).

### 5. No hay detector de caras ✅ descartado

OpenCV 5 ya no trae `CascadeClassifier`. En el piloto el encuadre por cara se decidió mirando los frames.

- **Cura real:** YuNet (`cv2.FaceDetectorYN`, modelo de ~230 KB, requiere aprobar la descarga) o MediaPipe — ~3 h.
- **Cuándo:** F2.
- **Descartado 26/10/2026** (D22): Yedin decidió que no se usa detección de caras ni rastreo de manos; quien sale en cámara es parte del video.

### 6. `proc._validate` acepta un `.cmd`/`.bat` absoluto ✅ pagada

cmd.exe re-interpreta los argumentos.

- **Mitigado hoy por:** ffmpeg/ffprobe pasan por `tool_path`, que rechaza scripts.
- **Cura real:** rechazar `.bat`/`.cmd` también en `_validate` + test — 0.5 h.
- **Cuándo:** antes de que S1.x lance otros programas.
- **Pagada 17/10/2026** (001.3, merge `0a33ee7`): `.bat`/`.cmd` rechazados en `_validate`. Suite tras el merge → `1012 passed, 3 skipped`.

### 7. El QA compara solo contra los subtítulos ⚪

Las palabras tapadas a propósito por un gráfico grande salen como "diferencias".

- **Cura real:** comparar contra todas las palabras conservadas del EDL — ~1 h.
- **Cuándo:** S1.7.

### 8. `proc._finalize` lee todo el stderr del hijo a memoria ✅ pagada

Con 100 MB de stderr, el pico llega a ~500 MB.

- **Mitigado hoy por:** `-loglevel error`.
- **Cura real:** leer solo los últimos N MB para la cola y volcar al log por trozos — 1 h.
- **Cuándo:** S1.5 (cuando el render corra ffmpeg sobre material real).
- **Pagada 17/10/2026** (001.3, merge `0a33ee7`): stderr por trozos con cola de 8 MB (`childlog.py`). Suite tras el merge → `1012 passed, 3 skipped`.

### 9. `scrub_media_metadata` solo entiende el formato `clave : valor` de ffmpeg ✅ pagada

No reconoce `TAG:k=v` ni el JSON de ffprobe. La regex ISO 6709 solo cubre grados decimales, y descarta líneas como "Unable to make progress: ..." por contener "make".

- **Mitigado hoy por:** el JSON crudo de ffprobe nunca sale (S1.2 hará lista blanca en `probe.py`).
- **Cura real:** comparar por palabra completa y ampliar formatos — 1 h.
- **Cuándo:** S1.2.
- **Pagada 17/10/2026** (001.3, merge `0a33ee7`): `MetadataScrubber`: claves por palabra entera, `TAG:`/JSON, ISO 6709 en DMS. Suite tras el merge → `1012 passed, 3 skipped`.

### 10. `requirements.lock` sin hashes y con dos pins muy recientes ⚪

Pins: `filelock==4.2.0` y `truststore==0.10.5`.

- **Mitigado hoy por:** OSV en vivo el 16/10/2026: 0 avisos para las 30 versiones del lock.
- **Cura real:** re-correr OSV en una semana; considerar `--require-hashes` — 0.5 h.
- **Cuándo:** 23/10/2026 (re-chequeo OSV).

### 11. Tests con `sleep` largo que lanzan `sys.executable` del venv pueden dejar huérfanos en Windows ✅ pagada

El `python.exe` del venv es un lanzador con hijo.

- **Mitigado hoy por:** solo afecta a tests; producción solo lanza `.exe` de ffmpeg/ffprobe, y los huérfanos terminan solos al acabar su `sleep`.
- **Cura real:** lanzar el intérprete base o matar el árbol en los tests — 0.5 h.
- **Cuándo:** S1.2 (al tocar los tests de `proc`).
- **Pagada 17/10/2026** (001.3, merge `0a33ee7`): tests con `sys._base_executable`. Suite tras el merge → `1012 passed, 3 skipped`.

### 12. Pista de `fonts` en `doctor/checks.py` dice "Pillow >= 10.1" ✅ pagada

El piso real es 12.3.

- **Mitigado hoy por:** es solo texto de ayuda; el piso real lo aplican `pyproject.toml` y `requirements.lock`.
- **Cura real:** actualizar la pista a Pillow >= 12.3 — 0.1 h.
- **Cuándo:** S1.2 (primer cambio a `doctor/checks.py`).
- **Pagada 17/10/2026** (001.3, merge `0a33ee7`): pista de `fonts` derivada de la metadata del paquete. Suite tras el merge → `1012 passed, 3 skipped`.

### 13. Captura de ffmpeg 7.x en `tests/unit/test_ffmpeg_caps.py` es de n7.0.1 (no 7.1) ✅ pagada

Las descripciones están reescritas.

- **Mitigado hoy por:** las columnas que se parsean son reales, y el verificador comprobó con 3 binarios reales: n7.0.1 16/16, n7.1 42/42, 8.1.1 576/576.
- **Cura real:** agregar captura real de un 7.1 — 0.5 h.
- **Cuándo:** S1.2.
- **Pagada 17/10/2026** (001.3, merge `0a33ee7`): capturas reales de ffmpeg n7.1 en `tests/data/`. Suite tras el merge → `1012 passed, 3 skipped`.

### 14. `run()` usa miembros privados de `ChildProcess` ⚪

- **Mitigado hoy por:** está en el mismo módulo; mypy strict y los tests cubren el uso.
- **Cura real:** hacer método público — 0.5 h.
- **Cuándo:** cuando S1.5 lo use.

### 15. README: indicar cómo correr `kcut` ✅ pagada

Nunca `python -m kcut` desde una carpeta de crudo: un `cv2.py` plantado se importaría.

- **Mitigado hoy por:** el ejecutable `kcut.exe` no pone la carpeta actual en `sys.path`, y HANDOFF y el spec usan `-I -X utf8`.
- **Cura real:** indicar que se corre `kcut ...` o `python -I -X utf8 -m kcut` — 0.2 h.
- **Cuándo:** S1.9 / spec 002.
- **Pagada 17/10/2026** (001.3, merge `0a33ee7`): sección "Desarrollo" en el README. Suite tras el merge → `1012 passed, 3 skipped`.

### 16. Los proxies SDR salen sin etiquetas `color_primaries` / `color_trc` ✅ pagada

ffmpeg 8.1.1 no escribe esas etiquetas desde las banderas de salida cuando el frame no las trae (solo `color_space` y `color_range`). Los proxies HDR sí salen completos porque `zscale` las fija. Afecta también al encode final de S1.5: un reproductor puede adivinar mal el color.

- **Mitigado hoy por:** los criterios actuales solo miran `color_space` y `color_range`, y el contenido sí es bt709.
- **Cura real:** `setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv` al final de la cadena SDR (o `-x264-params`), y criterios que exijan las 4 etiquetas — 1 h.
- **Cuándo:** ahora, en la ronda de revisión de S1.2 (regla de Yedin: deuda encontrada se arregla de una).
- **Pagada 16/10/2026** (parche 001.4, ronda 2): criterio S1.2-8, verificador ronda 3 → "4 passed; las 4 etiquetas bt709/tv en los 3 proxies".

### 17. Hallazgos de la revisión de S1.2 (1 CRÍTICO, 1 ALTO, 7 MEDIO, 6 BAJO) ✅ pagada

- **CRÍTICO:** `kcut new` sobre una carpeta sin `kcut.toml` sobrescribía `estrategia.md` (aprobada), `versiones.md` y `recursos.json`.
- **ALTO:** un `.kcut/inventory.json` envenenado (carpeta de proyecto hostil por zip/Drive) hacía escribir fuera del proyecto, o sacar archivos de `crudo/`, porque los destinos se validaban después de escribir.
- **MEDIO:** caracteres Unicode invisibles (U+2028/U+2029/U+0085) todavía colaban `aprobado: si`; log del comando truncado y mensaje corto sin limpiar; etiquetas de color SDR (#16); ids reutilizables entre ingests; fallo del wav16 que borraba la clase; score de sync injusto con solapes parciales; sin tope de duración ni de memoria (2.7 MB que dicen 20 h piden ~12 GB de RAM).
- **BAJO:** regex con `$` que acepta `
`, junctions en `crudo/` (hasta ×64), nombre >80, `proxy_size` 0, JSON corrupto que bloquea para siempre, orden de escritura de `kcut new`.

- **Mitigado hoy por:** nada de esto está en commit todavía (S1.2 sin cerrar); hoy no hay proyectos reales con `kcut`.
- **Cura real:** parche de spec 001.4 + ronda 2 del implementador — ~4 h.
- **Cuándo:** ahora (regla de Yedin: lo encontrado se arregla de una).
- **Pagada 16/10/2026** (001.4 + 001.5, ronda 2): ronda 3 de seguridad repitió cada variante del ALTO → `inventory_invalid`, `crudo/` byte-idéntico, `evilout/` intacto.

### 18. Hallazgos de la ronda 2 de S1.2 (1 ALTO, 4 MEDIO, 7 BAJO) ✅ pagada

- **ALTO (causado por el parche 001.5):** con el piso de solape del 75 %, en clips de menos de 13.4 s con poco solape la sincronía aceptaba un desfase equivocado sin avisar (7 de 150 casos). La correlación fina separa los casos: 0.99 en el bueno contra 0.01–0.02 en los malos.
- **MEDIO:** un junction interno (`.kcut` → `crudo/`) pasaba los controles y kcut escribía en `crudo/`; el log se podía escribir a través de un hard link plantado; un archivo bloqueado (`OSError` en `qhash`) tumbaba el ingest; los ids se renumeraban al borrar `.kcut/`, y un EDL viejo cortaría el video equivocado.
- **BAJO:** `_copy` borraba la fuente si fuente y destino eran el mismo archivo con otra grafía; el tope de duración se fiaba de la duración declarada; `kcut new` no revisaba junctions y su aviso mandaba a mover los archivos de la Puerta 1 a `crudo/`; `ID_HIGH_MAX` chocaba con el validador; el ruido del fixture no tenía semilla; el árbol del spec estaba incompleto; el glosario y los textos que S1.3 manda a Claude aceptan caracteres de control.

- **Mitigado hoy por:** S1.2 sigue sin commit.
- **Cura real:** parche 001.6 + ronda 3 (la última). Decisiones de Yedin del 16/10: umbral de correlación fina 0.1 configurable; el EDL guarda el `qhash` de cada fuente y `edl check` se niega si no coincide (S1.5) — ~3 h.
- **Cuándo:** ahora.
- **Pagada 17/10/2026** (001.6, ronda 3): verificador → lote de 150 clips cortos con semilla, "0 offsets malos aceptados"; 120 hard links plantados, sha256 de `crudo/pantalla.mp4` igual antes y después; archivo bloqueado → exit 0 con `probe_failed`. El `qhash` en el EDL queda para S1.5 (criterio S1.5-16).

### 19. Hallazgos de la ronda 3 de S1.2 (1 MEDIO, 6 BAJO) ✅ pagada

- **MEDIO:** con audio casi periódico (música en loop), un clip de menos de 13.4 s y mucho desfase, la sincronía puede aceptar un desfase equivocado sin avisar (tonos del fixture, 12 s +4 s → −2800). Con voz real no pasa.
- **BAJO:** `kcut new` dentro del `crudo/` de otro proyecto; `run_ingest` inventa un log cuando la CLI dijo "sin log"; `doctor` deja logs vacíos; `append_log` puede lanzar `OSError` y dejar un ffmpeg huérfano (seguridad); avisos de sync deducidos de `refine_corr` en vez del motivo; falta `logfile.py` en el árbol del spec.
- **No se cambia:** que un archivo que no se pudo hashear reciba id nuevo después. Conservar la entrada vieja dejaría un `qhash` viejo y E04 no saltaría (razón en 001.7 punto 8).
- **Mitigado hoy por:** hace falta una carpeta de logs saboteada o un fallo de disco para el huérfano; el caso periódico necesita clips cortos con música en loop.
- **Cura real:** parche 001.7 (criterios S1.2-40 a 47 y S1.3-11) + agente en worktree aislado — ~3 h. Decisión de Yedin 17/10/2026: arreglar el MEDIO.
- **Cuándo:** ahora, después de mergear la rama de deuda de S1.1.
- **Pagada 17/10/2026** (001.7, 2 rondas; sumó los hallazgos de esa revisión, puntos 11–17): verificador → `1149 passed, 3 skipped`; un inventario real de 001.6 con los tonos aceptados en −2800 queda `sync_ambiguous` en un ingest normal; seguridad repitió sus 4 repros → cerradas.

### 20. La suite completa tarda ~10 min ✅ pagada

- **Mitigado hoy por:** los revisores corren subconjuntos con `-k`.
- **Cura real:** marcador `slow` para todo test de más de 2 s y suite rápida `pytest -m "not slow"` (001.7 punto 9) — 1 h.
- **Cuándo:** ahora, con la deuda 19.
- **Pagada 17/10/2026** (001.7 punto 9): `pytest -m "not slow" -q` → `1023 passed, 3 skipped, 126 deselected in 73.64s`; el test más lento sin `slow`, 1.45 s.

### 21. Muchos tests lanzan `python -m kcut` como subproceso (~1 s cada uno) ⚪

Son la mayor parte del costo de la suite completa.

- **Mitigado hoy por:** la suite rápida `pytest -m "not slow"` (deuda 20).
- **Cura real:** pasar a `cli.main` en proceso los tests que no prueban el arranque real. Se quedan como subproceso los que verifican `-I -X utf8`, códigos de salida del ejecutable y huérfanos — 2 h.
- **Cuándo:** cuando la suite rápida pase de 2 min.

### 22. Carrera teórica `lstat` → `unlink` al borrar un log vacío ⚪

Entre comprobar que el log vacío es el mismo archivo y borrarlo, alguien con acceso a `.kcut/logs/` podría cambiarlo.

- **Mitigado hoy por:** solo se borra un archivo de 0 bytes, regular, con `st_nlink == 1` y el mismo `st_ino` que se creó; quien puede escribir en `.kcut/logs/` ya puede borrar lo que quiera ahí.
- **Cura real:** borrar por handle (`FILE_FLAG_DELETE_ON_CLOSE` / `SetFileInformationByHandle`) en Windows — 2 h. No vale la pena hoy.
- **Cuándo:** solo si kcut llega a correr en una carpeta compartida con otros usuarios.

### 23. Hallazgos de la revisión de 001.7 (higiene de consola, rangos) ✅ pagada

- Seguridad: secuencias de escape del inventario llegaban a la terminal; texto libre del inventario en `--json` (inyección de prompt); rangos faltantes.
- **Pagada 17/10/2026** (001.8, commit `7119577`): pytest → 1211 passed, 3 skipped.

### 24. Deuda vista al implementar 001.8 ✅ pagada

- Float gigante tumbaba el cargador; fallback del log a stderr sin limpiar; tope de 12 h inconsistente con `max_duration_h` de 48 h.
- **Pagada 17/10/2026** (001.9, commit `f59f68e`): pytest → 1238 passed, 3 skipped; seguridad → APROBADO, 0 hallazgos en el diff.

### 25. Notas de seguridad fuera del diff de 001.8/001.9 ✅ pagada

- Prosa del atacante en el aviso `inventory_invalid` del `--json` (MEDIO); `sync.manual` sin rango; entero gigante en `kcut.toml` da error interno; selectores de variación sin escapar.
- **Mitigado hoy por:** todavía no hay proyectos reales con kcut.
- **Cura real:** spec 001.10, paso 0 de S1.3 — 1.5 h.
- **Cuándo:** ahora, primer paso de S1.3.
- **Pagada 26/10/2026** (001.10, paso 0 de S1.3).

### 26. `faster-whisper 1.2.1` no funciona con `av 19.0.1` al decodificar archivos ⚪

`faster-whisper` llama `av.open(..., metadata_errors=...)`, que PyAV 19 ya no acepta.

- **Mitigado hoy por:** kcut no usa ese camino: lee el wav16 con su propio lector y le pasa a Whisper el array (001.11 punto 3).
- **Cura real:** al subir `faster-whisper` o `av` en el lock, comprobar que `faster_whisper.decode_audio` funciona; o poner un tope a `av` en el lock tras verificar en qué versión cambió — 0.5 h.
- **Cuándo:** la próxima vez que se toque `requirements.lock`.

### 27. Las transcripciones reemplazadas se quedan en `.kcut/transcripts/` ⚪

- **Mitigado hoy por:** `.kcut/` es regenerable y se puede borrar entero.
- **Cura real:** borrar los `<key>.json` que ya no estén en `index.json` al terminar `transcribe` — 0.5 h.
- **Cuándo:** S1.9 (`kcut build` / limpieza).

### 28. `transcribe` carga el wav16 entero en memoria (~2.7 GB para 12 h) ⚪

- **Mitigado hoy por:** el tope por defecto es `max_duration_h = 12` y la máquina tiene 16 GB; faster-whisper también decodifica entero.
- **Cura real:** transcribir por ventanas con solape — 3 h.
- **Cuándo:** solo si aparecen crudos de varias horas.

### 29. PII residual de la ronda 5 de S1.3 ✅ pagada

- **Qué falta:** apartes y muletillas fuera de lista, reinicio a mitad del número, teléfonos con guiones en nombres de archivo, correos con dominio de varias palabras.
- **Mitigado hoy por:** el barrido de seguridad de la ronda 5 (129 casos de habla normal EN/ES) no encontró fugas con muletillas del idioma del proyecto; lo que queda necesita apartes fuera de lista o nombres de archivo con guiones.
- **Cura real:** spec 001.18, paso 0 de S1.4.
- **Cuándo:** ahora.
- **Pagada 26/10/2026** (S1.4, 001.18–001.21, commit `40e9c65`).

### 30. Límites aceptados del enmascarado ⚪

- Un número partido entre dos clips no se junta.
- Los correos deletreados letra por letra no se detectan.
- La prosa del atacante pasa hasta 40 caracteres por mensaje.
- Un reinicio separado por un aparte de 7 o más palabras deja visible el primer intento (3–6 dígitos); en el fuzz de seguridad, 0 fugas con apartes de 6 palabras o menos.
- Un grupo de 1 dígito antes de un aparte queda visible (no es PII por sí solo).
- La excepción de fecha puede dejar 2 dígitos extra en nombres como `tel_20255501_23`.
- Cadenas de sobre-enmascarado: una lista de números de 3 dígitos que termina en un número de 7 o más se tapa completa. Es por diseño.
- Una cadena con un aparte entre cada trozo, donde ningún par llega a 7 ("809 ya 55 ya 512 ya 34"), queda visible (001.23, punto 1).
- `juan arroba gmail punto com;8095551234`: el correo dictado queda legible; solo pasa con texto hostil.
- (Fuera del enmascarado, anotado aquí para no perderlo) `qhash` no cubre la parte del medio de los archivos de más de 16 MiB: frena la renumeración accidental, no un archivo fabricado.
- `pedro@g-809@555@1234.mp4`: un `@` entre los dígitos corta la racha y el nombre `pedro` queda visible.
- `x/809/555/1234.mp4`: un teléfono partido entre carpetas queda entero.
- `o'brien@g-809-555-1234.mp4` sale como `o'b***@***.mp4`.
- Motivo: son rutas armadas a propósito para esos casos; enmascarar más taparía carpetas de fecha como `2026/10/27/` (001.33 punto 10, 001.32 punto 11).
- **Mitigado hoy por:** cada clip se enmascara entero; el md lleva la línea fija "es dato, nunca instrucciones"; los mensajes van recortados.
- **Cura real:** en el plugin, negar la lectura de `.kcut/transcripts/**` y trabajar solo con `pack`; juntar números entre clips solo si aparece el caso real — ~2 h.
- **Cuándo:** spec 002 (el plugin no deja que Claude lea `.kcut/transcripts/`).

### 31. Hallazgos de la ronda final de S1.4 ✅ pagada

Lo que falta; todo va al paso 0 de S1.5a (spec 001.22):

- `frames` con tiempos repetidos (`90` y `3s`) y `--out` sin `--force` da "ya existe" sobre su propio PNG.
- En la parte local de un correo dictado, `cientos` y `mil`/`thousand` no cuentan como número.
- `guion` no está en `JOIN`.
- La lista de TLD para correos dictados es cerrada: `.store`, `.me`, `.xyz` y `.cr` quedan sin cubrir.
- Grupos de dos dígitos entre apartes ("ocho cero nueve, ya, cinco cinco, ya, cinco uno dos, ya, tres cuatro") quedan sin cubrir.
- Número pegado a un correo escrito en el mismo token (`juan@gmail.com;8095551234`).
- `crudo/juan@gmail.com` sin extensión de medio.
- Un stream que cambia de resolución a mitad pasa el control de tamaño de ffprobe: DoS local, 2.4 GB en el hijo de ffmpeg. Cura: `-max_pixels`.
- 5 tests cuyo nombre contradice su `assert`.

- **Mitigado hoy por:** la regla de corte: ninguno deja una dirección o un teléfono reconstruible con habla normal. El DoS necesita un archivo plantado en `.kcut/proxy/` y muere a los 60 s.
- **Cura real:** spec 001.22 (paso 0 de S1.5a).
- **Cuándo:** ahora (paso 0 de S1.5a).
- **Pagada 26/10/2026** (paso 0 de S1.5a, 001.22–001.23, commit `6605456`).

### 32. `replace=False` con `os.rename` no protege en POSIX ⚪

En Linux o WSL, `os.rename` sobrescribe en silencio, así que `write_bytes_atomic(replace=False)` no protege ahí.

- **Mitigado hoy por:** la herramienta es Windows-first; en Windows, `os.rename` falla con `FileExistsError`.
- **Cura real:** `os.link(tmp, path)` + `unlink(tmp)`, con fallback para volúmenes FAT/exFAT sin hard links (los discos de footage suelen ser exFAT) — 1–2 h.
- **Cuándo:** si kcut llega a correr en Linux.

### 33. Hallazgos de la revisión de S1.5a ✅ pagada

Lo que falta; todo va al paso 0 de S1.5b (spec 001.24):

- Números entre dos correos escritos, pegados en una sola palabra, quedan crudos: por ejemplo, una tarjeta de 16 dígitos.
- La segunda dirección de correo dentro de una parte de ruta queda legible.
- El gate aprueba `❌ sí` y `[ ] sí`, porque quita todo lo que no sea `[a-z0-9]`.
- La validación es cuadrática: 30 000 spans tardaron 370 s.
- La salida de `edl check` no tiene tope, y dos enteros enormes terminan en exit 10.
- Hasta 37 caracteres de texto del atacante aparecen en los errores.
- Sin bloque `sources`, da E01 en vez de E04.
- `edl.kept` importa `commands.pack`.
- Un test de E06 no ejercita su guarda.
- Un EDL vacío pasa.
- El texto crudo llega al `repr` de `KeptWord`.
- `display_w = 0` divide entre cero.
- `guion guion` corta la parte local.

- **Mitigado hoy por:** nada llega todavía al video final: `render` (S1.5b) no existe, así que nada consume el gate. El DoS y la inundación de la salida necesitan un EDL plantado.
- **Cura real:** spec 001.24 (paso 0 de S1.5b).
- **Cuándo:** ahora (paso 0 de S1.5b).
- **Pagada 27/10/2026** (paso 0 de S1.5b, 001.24, commit `1d8cf00`).

### 34. La consola de kcut muestra nombres crudos 🟡

`kcut ingest` imprime los nombres de `crudo/` tal cual (por ejemplo `crudo/<nombre con un teléfono>.mp4`), y varios mensajes llevan slugs con dígitos. El plugin de spec 002 va a leer esa salida.

Casos de S1.6a que siguen con la ruta o el nombre con slug:

- `transcribe/cache.py`: `wav16_length_ms` y `file_sha256`;
- `jsonio.read_json` (`no pude leer {path}: {exc}`);
- `resolve_in_project` con un symlink en `crudo/` (el mensaje nombra el archivo crudo);
- `cli._internal`, que enmascara los dígitos y deja el nombre;
- un slug sin `@` en lo que imprime `kcut ingest`.

Para el Gate 1 de spec 002:

- (a) Claude no lee `.kcut/build/vN/gfx/` salvo `gfx/stills/`, porque `page.html` y las PNG de la capa llevan texto crudo para el MP4.
- (b) Decidir si los precios con punto como separador de miles quedan visibles. Hoy `1.500.000` sale enmascarado como `*.***.*00` en la transcripción y en el texto plano; un test lo fija.
- (c) `graphics check --json` muestra `params.image` con los dígitos enmascarados y la palabra visible (`recursos/Maria-********34.png`). Decidir en el Gate 1 si el nombre también se enmascara.
- (d) El log de `kcut mix` (`.kcut/logs/`) guarda la línea de comando con el nombre del archivo de música sin enmascarar, como todo `proc.run`; el nombre de una canción puede ser el de una persona.

- **Mitigado hoy por:** nada; el plugin todavía no existe.
- **Cura real:** decidir el enmascarado de la consola en el Gate 1 de spec 002, con Yedin (spec 001.27 punto 13) — ~2-4 h.
- **Cuándo:** Gate 1 de spec 002.

### 35. `require_disk_space` no cuenta los mezzanines ni el video ⚪

`require_disk_space` cuenta la pista de voz, 1 GiB y, desde 001.31, la capa de gráficos (`GFX_FRAME_BYTES` = 192 KiB por cuadro activo). Desde 001.30 las cifras van antes de la ruta. Siguen fuera del cálculo los mezzanines y el video.

- **Mitigado hoy por:** si el disco se llena durante los mezzanines o el video, el render sale con `ToolError` y borra su parcial: es una falla segura.
- **Cura real:** contar también los mezzanines y el video — ~1 h.
- **Cuándo:** S1.9b (`kcut build`).

### 36. `frame_count` duplicado ⚪

`render/mezz_files.frame_count` repite la lógica de `ff/reader.proxy_frame_count`.

- **Mitigado hoy por:** los dos tienen test y dan lo mismo.
- **Cura real:** una sola función en `ff/reader.py` que usen los dos — ~0.5 h.
- **Cuándo:** la próxima vez que se toque `ff/reader.py` o `mezz_files.py`.

### 37. `VoiceIndex.overlapping` lento ante un EDL hostil ⚪

`VoiceIndex.overlapping` recorre todos los tramos de voz por cada consulta.

- **Mitigado hoy por:** los topes de 10 000 clips y 10 000 spans, que dan E01 (spec 001.24 punto 4). Un reel real tiene menos de 500.
- **Cura real:** índice ordenado con `bisect` — ~1 h.
- **Cuándo:** S1.9b (`kcut build`), si el render de un EDL grande se mide lento.

### 38. `voice_blocks` es O(bloques × clips) ⚪

- **Mitigado hoy por:** los mismos topes de la 37.
- **Cura real:** barrido con los clips ordenados — ~1 h.
- **Cuándo:** S1.9b (`kcut build`), si el render de un EDL grande se mide lento.

### 39. `captions.hide` sin tope y `graphics check --json` sin tope de errores ✅ pagada

`captions.hide` no tiene tope, y `graphics check --json` no tiene tope de errores. Abierta al cerrar S1.6a.

- **Riesgo:** un `graphics.json` de menos de 1 MiB con unas 36 000 ventanas cuelga `graphics check` unos 107 s, y uno con 350 000 enteros da 350 000 errores en lo que lee Claude.
- **Mitigado hoy por:** el tope de 1 MiB de la lectura (001.28). Acota los bytes, no los elementos.
- **Cura real:** S1.6b paso 0, fila 13 (`MAX_HIDE = 500`, y 50 errores con totales como en `edl check`) — ~1 h.
- **Cuándo:** pagada 27/10/2026 (S1.6b paso 0, fila 13, commit `f8f728f`).

### 40. `assert_in_cache` nombra la ruta ✅ pagada

`assert_in_cache` nombra la ruta. Abierta al cerrar S1.6a.

- **Riesgo:** con un junction plantado en un work file, el mensaje de `kcut render` lleva el slug con el teléfono.
- **Mitigado hoy por:** hace falta plantar el enlace dentro de `.kcut/`. El chequeo falla cerrado y no escribe nada fuera.
- **Cura real:** S1.6b paso 0, fila 14 (`label` con `work_label`) — ~30 min.
- **Cuándo:** pagada 27/10/2026 (S1.6b paso 0, fila 14, commit `f8f728f`).

### 41. WebP reserva memoria antes del chequeo de píxeles ✅ pagada

Un WebP reserva memoria antes del chequeo de píxeles. Abierta al cerrar S1.6a.

- **Riesgo:** un archivo de 32 bytes que declara 16384 × 16384 pide unos 2 GB de memoria comprometida antes del chequeo.
- **Mitigado hoy por:** no se alcanza. Ningún componente base tiene un parámetro `path` hasta S1.7, y toda imagen pide aprobación humana en el manifiesto.
- **Cura real:** S1.6b paso 0, fila 15 (leer ancho y alto de la cabecera RIFF antes de `Image.open`) — ~1 h.
- **Cuándo:** pagada 27/10/2026 (S1.6b paso 0, fila 15, commit `f8f728f`).

### 42. Etiqueta de una letra con teléfono en `mask_bare_domains` ✅ pagada

Hay una etiqueta de una letra con teléfono en `mask_bare_domains`. Abierta al cerrar S1.6a.

- **Riesgo:** `pedro@g-8095551234.mp4` deja ver `pedro`. El teléfono sí sale tapado.
- **Mitigado hoy por:** el enmascarado de dígitos tapa el teléfono. Es un nombre de archivo poco realista.
- **Cura real:** S1.6b paso 0, fila 17 (tapar la etiqueta que lleva 7 dígitos seguidos o más) — ~30 min.
- **Cuándo:** pagada 27/10/2026 (S1.6b paso 0, fila 17, commit `f8f728f`).

### 43. Cada PNG de la capa se decodifica dos veces ⚪

Una vez en `_max_alpha` al capturar y otra en el overlay al renderizar.

- **Riesgo:** CPU de más en captura y render; no afecta el resultado.
- **Mitigado hoy por:** nada; no hace falta, el costo es tiempo.
- **Cura real:** guardar el alfa máximo en el índice o decodificar una vez — ~1 h.
- **Cuándo:** cuando se mida rendimiento en S1.9b.

### 44. Dos tests importan el privado `kcut.commands.pack._energy` ⚪

Son `tests/unit/test_wavio.py` y `tests/unit/wavio_cases.py`. `tests/unit/test_layers.py` solo mira `src/kcut/`.

- **Riesgo:** cambiar `commands/pack.py` rompe tests de otra cosa.
- **Mitigado hoy por:** la suite lo detecta enseguida.
- **Cura real:** probar la función pública de `analysis/energy.py` — ~30 min.
- **Cuándo:** la próxima vez que se toque `commands/pack.py`.

### 45. Un `seek` que encuentra la página ya bloqueada no vuelve 🟡

Pasa con una tarea del JS que la página dejó para después del frame anterior. `cdp.send` no tiene timeout, así que el lock `build-vN` queda tomado y Chromium al 100 %.

- **Mitigado hoy por:** el JS de kcut prohíbe las APIs que dejan tareas diferidas (`setTimeout`, `setInterval`, `requestAnimationFrame`, `requestIdleCallback`, `MessageChannel`, `postMessage`, `Worker`); S1.8a paso 0 fila 9 agrega observers y promesas en componentes. La captura CDP no lleva timeout, por decisión 001.34 (`page.screenshot` costó 1.88×).
- **Cura real:** un vigilante que mate el árbol de procesos de Chromium por pid al pasar el tope — ~2 h.
- **Cuándo:** si un componente empieza a usar temporizadores.

### 46. Ventanas de microsegundos entre mirar y usar en la caché ⚪

Aceptadas en spec 001.32 punto 8.

- **Riesgo:** un proceso local con escritura en `.kcut/` que acierte esa ventana.
- **Mitigado hoy por:** cada escritura, borrado y lectura se mira justo antes.
- **Cura real:** operar sobre handles en vez de rutas — ~4 h.
- **Cuándo:** solo si kcut llega a correr donde otros escriben en `.kcut/`.

### 47. Hallazgos de la revisión de S1.6b que van al paso 0 de S1.7 ✅ pagada

Lo que falta; todo va al paso 0 de S1.7:

- La foto de Chromium sin tope;
- los stills leídos de disco;
- los work files sin mirar después del ffmpeg (obliga a partir `workfiles.py`);
- WebRTC por TURN sobre TCP;
- la carpeta `gfx/` cambiada durante el render;
- el traceback de asyncio cuando falta el driver;
- dos regex de extensión sin amarrar;
- el tope total de imágenes de la página;
- un comentario viejo.

- **Mitigado hoy por:** ninguno se alcanza con el JS de kcut ni sin acceso local de escritura a `.kcut/`.
- **Cura real:** filas 9-18 de S1.7, ~6-8 h en total.
- **Cuándo:** pagada 28/10/2026 (S1.7 paso 0, commit `78a2b19`). La foto de Chromium no lleva timeout: el tope con `page.screenshot` (fila 9) costó 1.88× por cuadro (B1, 001.34); se mantuvo la captura CDP rápida y la amenaza la cierran las reglas de JS.

### 48. Hallazgos de la revisión de S1.7 que van al paso 0 de S1.8a ✅ pagada

Lo que falta; todo va al paso 0 de S1.8a:

- la ruta de la imagen que se repite en los mensajes G10/G09 (PII), y ningún `max_len` en `image`;
- observers, promesas y callbacks de eventos sin prohibir en el JS de la página;
- `.kcut` en sí como junction que pasa `assert_in_cache`;
- `sticker.path` sin tope;
- entra un PNG o WebP animado;
- el guardia del overlay cuesta 2.7 ms por cuadro;
- los componentes base (`title`, `label`, `kinetic`, `endcard`) dependen del orden de captura (solo un still suelto difiere del cuadro del MP4, por antialiasing de bordes);
- un chequeo débil de acento en un test;
- tiempos de componente que caen después del fin del cue, sin aviso;
- `holo_board.w_px` demasiado angosto por debajo de unos 300;
- el componente falso `picture` que queda en dos tests.

- **Mitigado hoy por:** la ruta de la imagen es texto que Claude mismo escribe en `graphics.json`; lo demás necesita acceso local de escritura a `.kcut/` o un cambio futuro en el JS, o no sale en el MP4.
- **Cura real:** filas 8–19 de S1.8a, ~6-8 h.
- **Cuándo:** pagada 28/10/2026 (S1.8a paso 0, commit `4e996cc`).

### 49. `resolve_cues._use_images` no baja a los parámetros `object` ⚪

- **Riesgo:** un componente futuro con una imagen dentro de un objeto no la embebería; la página pediría una ruta `file://` que el bloqueo de rutas impide, y la captura pararía con un ToolError.
- **Mitigado hoy por:** ningún componente pone una imagen dentro de un objeto.
- **Cura real:** recorrer también los parámetros `object`, ~30 min.
- **Cuándo:** cuando un componente ponga una imagen dentro de un objeto.

### 50. El parámetro `out_dir` de `capture_stills` ya no se usa ⚪

- **Riesgo:** solo confusión.
- **Mitigado hoy por:** nada lo lee.
- **Cura real:** quitarlo y actualizar unas 30 llamadas en tests, ~1 h.
- **Cuándo:** la próxima vez que se toque `gfx/capture.py`.

### 51. Hallazgos de la revisión de S1.8a que van al paso 0 de S1.8b ✅ pagada

Lo que falta; todo va al paso 0 de S1.8b:

- `sfx.json` no tiene topes de eventos, ventanas ni bytes, y las anclas de palabra se buscan en una lista (O(N·M));
- la síntesis no tiene presupuesto: `dur_f` llega hasta la duración del video, así que un `pad` de 20 minutos pide unos 2.5 GB;
- un número enorme sale entero en un mensaje de A03;
- el recorrido de los chunks de la imagen no tiene tope, y los rechazos no se guardan en caché;
- una ruta de más de 32 000 caracteres da exit 10 (un `ValueError` de `Path.resolve`);
- las APIs de animación con reloj propio (`KeyframeEffect`, `document.timeline`) no están en las reglas de JS;
- ningún test comprueba que `kcut render` pase `watch=`;
- `st_ino` puede ser 0 en FAT;
- un `recursos.json` roto no dice dónde falla;
- un tercer test sigue usando el `picture` falso;
- faltan acentos en los textos del catálogo.

- **Mitigado hoy por:** ningún comando lee `sfx.json` todavía; la puerta se abre con `kcut mix` en S1.8b.
- **Cura real:** filas 12–23 de S1.8b, ~6-8 h.
- **Cuándo:** pagada 28/10/2026 (S1.8b paso 0, commit `a0ffe90`).

### 52. `title`, `label`, `endcard` y los subtítulos siguen reutilizando nodos entre `seek`s ⚪

- **Riesgo:** si un estilo futuro vuelve a reutilizar capas, vuelve la dependencia del orden de captura.
- **Mitigado hoy por:** pasan `test_showpiece_order_independent` ahora que `will-change` ya no está.
- **Cura real:** reconstruirlos en cada `seek`, como `kinetic`, ~2 h.
- **Cuándo:** la próxima vez que se toquen esos componentes.

### 53. `lowpass` es un bucle de Python ⚪

- **Riesgo:** unos 0.1 s por cada segundo de audio sintetizado.
- **Mitigado hoy por:** los topes de S1.8b (30 s por efecto, 1200 s en total) acotan la síntesis de `kcut mix`: el peor caso medido es de unos 95 s de CPU.
- **Cura real:** vectorizarlo manteniendo la salida bit a bit con el piloto, o aceptar una tolerancia documentada, ~2 h.
- **Cuándo:** si la síntesis de SFX sale lenta en `kcut mix`.

### 54. Hallazgos de la revisión de S1.8b que van al paso 0 de S1.9a 🟡

Lo que falta; todo va al paso 0 de S1.9a:

- una mezcla de más de 0 LUFS tumba `kcut mix` con el mensaje crudo de ffmpeg;
- el cambio de carpeta entre ffmpeg y `atomic_replace` (`os.replace` y `discard_partial` siguen el enlace, y un `FileNotFoundError` da exit 10);
- `prepare_partial` con la ruta antes del motivo;
- constantes de timeout repetidas;
- `apad` fuera de `REQUIRED_FILTERS`;
- `params._shown` importado como privado.

- **Mitigado hoy por:** la mezcla fuerte solo pasa con ganancias extremas, y el cambio de carpeta pide un proceso local con timing de microsegundos.
- **Cura real:** filas 11–17 de S1.9a, ~4-5 h.
- **Cuándo:** en curso, S1.9a paso 0.

### 55. La mezcla tiene el audio entero en memoria 🟡

- **Riesgo:** unos 6 GB de RAM para la música de un video de 1 hora; un `MemoryError` hoy sale como exit 3 claro.
- **Mitigado hoy por:** los reels son cortos; el `MemoryError` se convierte en ProjectError.
- **Cura real:** sintetizar y mezclar por bloques, ~4 h.
- **Cuándo:** antes del primer video largo (más de 10 minutos).

### 56. La aprobación del manifiesto no guarda un hash del archivo ⚪

- **Riesgo:** un archivo cambiado después de aprobarse (DS9) sigue pasando.
- **Mitigado hoy por:** la aprobación la da una persona, y el archivo vive en `recursos/` del proyecto.
- **Cura real:** guardar el sha256 al aprobar y compararlo al usar, ~2 h.
- **Cuándo:** Gate 1 de spec 002, con el flujo de aprobación del plugin.

---

## Lecciones ya pagadas

### 1. Segundos con decimales rompen la rejilla de frames
- **Síntoma:** un `assert` de frame exacto saltó: 2.1667 s × 30 = 65.001.
- **Por qué engañaba:** redondear a 4 decimales "parece" exacto.
- **Causa real:** coma flotante.
- **Fix:** todo el EDL en **frames enteros**; los segundos solo para mostrar (`piloto/edl.py`).

### 2. Whisper estira las palabras por encima de las pausas
- **Síntoma:** "con" duraba 1.68 s, "hola" 2.2 s; un corte por timestamp habría dejado pausas muertas.
- **Por qué engañaba:** con `vad_filter=False` los timestamps lucen continuos.
- **Causa real:** el alineamiento de palabras de Whisper rellena los huecos.
- **Fix:** silencios por **energía** (RMS a 10 ms, umbral −42 dBFS) cruzados con las palabras (`piloto/view.py`).

### 3. Correcciones de texto globales se comen otras frases
- **Síntoma:** "seguir → en el video" también cambió "vamos a seguir".
- **Causa real:** reemplazo por texto, no por posición.
- **Fix:** correcciones atadas al **tiempo** de la palabra (`FIX_AT` en `piloto/cues.py`).

### 4. Una palabra con inicio "temprano" se pierde en los subtítulos
- **Síntoma:** faltaban TE, POR, O, MAÑANA, GRACIAS.
- **Causa real:** Whisper pone el inicio antes del corte y el filtro exigía `inicio >= corte`.
- **Fix:** se incluye la palabra si su **final** cae dentro del tramo, y se recorta el inicio al tramo.

### 5. ffmpeg y OpenCV convierten color con bt601 por defecto
- **Síntoma:** riesgo de corrimiento de tono (el lima se ve distinto) al pasar YUV↔RGB.
- **Fix:** `scale=in_color_matrix=bt709` al leer, `out_color_matrix=bt709` al escribir, también al superponer los PNG de gráficos.

### 6. `python -I` ignora `PYTHONUTF8`
- **Síntoma:** `UnicodeEncodeError` en cp1252 al imprimir acentos o emojis, aun con `PYTHONUTF8=1`.
- **Causa real:** `-I` ignora todas las variables `PYTHON*`.
- **Fix:** `python -I -X utf8`.

### 7. El fondo transparente del webp se lee como negro
- **Síntoma:** el recorte del logo daba la imagen completa.
- **Causa real:** `cv2.IMREAD_COLOR` tira el canal alfa.
- **Fix:** `cv2.IMREAD_UNCHANGED` y recortar por alfa.

### 8. Un gesto clave puede vivir dentro de una pausa "inútil"
- **Síntoma:** el holograma no tenía dónde nacer en v1.
- **Causa real:** la pausa de 0.66 s que se cortó era justo donde Yedin abría las manos.
- **Fix:** antes de cortar una pausa, mirar los frames. Se mantuvo el tramo continuo.

### 9. El rastreador de manos se resbala
- **Síntoma:** en el segundo tramo el punto terminó en la mesa.
- **Causa real:** esa mano bajó y subió la otra.
- **Fix:** verificar **siempre** el rastreo pintándolo sobre los frames; usar solo la parte buena y animar el resto (el logo vuela al globo).

### 10. El normalizador de SFX aplasta lo que se quiere subir
- **Síntoma:** subir el beat del inserto dio solo +1.7 dB.
- **Causa real:** los booms del gancho marcan el pico y la normalización global baja todo.
- **Fix:** subir el volumen en la mezcla solo en la ventana (`volume=1.8:enable='between(t,..)'`).

### 11. `asplit` con una salida sin conectar revienta ffmpeg
- **Fix:** mandar la salida sobrante a `anullsink`.

### 12. `shutil.which` en Windows busca primero en la carpeta actual
- **Síntoma:** un `ffmpeg.exe` plantado en una carpeta de footage se ejecutaba.
- **Por qué engañaba:** en la terminal de Claude Code la variable `NoDefaultCurrentDirectoryInExePath=1` ya estaba puesta y los tests pasaban.
- **Fix:** `toolpath.py` pone esa variable, exige ruta absoluta resuelta y solo `.exe`/`.com`.

### 13. En Windows, dos procesos hijos que heredan el mismo handle de log se pisan (no hay `O_APPEND`)
- **Síntoma:** de 402 líneas quedaban 220.
- **Fix:** stderr de cada hijo a su propio temporal, agregado al log bajo un lock.

### 14. La expresión de filtros de ffmpeg cambió entre la 7 y la 8 (tercera bandera)
- **Síntoma:** con ffmpeg 7.1 se leían 10 de 42 filtros.
- **Por qué engañaba:** los tests solo tenían líneas del formato 8.
- **Fix:** `[T.][S.][C.]?` + capturas reales de las dos versiones.

### 15. Un piso de dependencia "de memoria" puede quedarse corto
- **Síntoma:** se recomendó `Pillow>=10.3` y OSV en vivo mostró avisos hasta 12.2.
- **Fix:** consultar OSV en vivo antes de fijar pisos.

### 16. `Path.write_text` trunca el archivo antes de fallar al codificar
- **Síntoma:** un script de edición del spec metió un surrogate suelto (`\ud800`) en el texto; `write_text` lanzó `UnicodeEncodeError` y el spec quedó en 0 bytes (17/10/2026). Se recuperó con `git show HEAD:...` y re-aplicando los cambios.
- **Por qué engaña:** el archivo se abre en modo `w` (vacío) **antes** de codificar; el error llega tarde y parece que "no se escribió nada".
- **Fix:** codificar primero (`data = s.encode("utf-8")`), escribir a `<archivo>.tmp` y `os.replace`. Es la misma regla que ya sigue `jsonio` para `inventory.json`.

### 17. En Windows, dentro de un venv, `sys.executable` es un lanzador
- **Síntoma:** `kill()` mataba al lanzador y el intérprete real seguía vivo, con los pipes agarrados.
- **Por qué engaña:** `kill()` vuelve sin error y el proceso que mataste sí murió; el que sigue vivo es otro, el que lanzó el lanzador.
- **Fix:** en tests que matan al hijo, usar `sys._base_executable` (no ve los paquetes del venv).

### 18. Las herramientas de escritura pueden convertir escapes `\uXXXX` en caracteres crudos
- **Síntoma:** al escribir tests de higiene, escapes como U+2028 o U+202E quedaron como caracteres invisibles dentro del `.py`.
- **Por qué engaña:** el archivo se ve igual en el editor.
- **Fix:** después de editar tests con caracteres raros, escanear los `.py` tocados buscando Cc/Cf/Zl/Zp/Cs crudos.

### 19. La PII sobre habla es una heurística: cada ronda de fuzz encuentra un borde nuevo
- **Síntoma:** S1.3 necesitó 5 rondas porque cada revisión inventaba un patrón nuevo de dictado.
- **Por qué engañaba:** cada ronda cerraba lo que se encontró y parecía que la siguiente sería la última, pero el espacio de formas de dictar un número es abierto.
- **Causa real:** detectar PII en habla transcrita no tiene una solución exacta; sin una barra de "habla normal" acordada, los revisores siempre encuentran un borde adversario nuevo.
- **Fix:** una regla de corte (cerrar salvo crítico o fuga con habla normal) y llevar los bordes al paso 0 del slice siguiente.

### 20. Una regla de PII que depende del orden de lectura deja asimetrías
- **Síntoma:** una pasada de izquierda a derecha enmascaró distinto "555 like 0198 like 305" que "305 like 555 like 0198", y un reinicio antes del número se quedó visible.
- **Por qué engañaba:** los tests se escribieron en el orden en que la gente dicta, y la asimetría parecía un límite de la heurística.
- **Causa real:** una sola pasada de izquierda a derecha; el resultado dependía de qué número venía primero.
- **Fix:** una pasada de derecha a izquierda, repetida hasta que nada cambie. Cada caso se prueba junto con su espejo y contra fuerza bruta frente a una clausura independiente del orden.

### 21. Un ejemplo del spec que el mecanismo no puede cumplir es un error del spec, no del código
- **Síntoma:** el implementador quedó BLOQUEADO en la fila 19 de los criterios de S1.5a: los ejemplos (trozos 3+2+3+2, con un aparte entre cada uno) no tenían ningún par que llegara a 7.
- **Por qué engañaba:** la regla se leía como si fuera por cada trozo, cuando es por pares.
- **Causa real:** el coordinador escribió ejemplos para `MIN_SIDE = 2` que ningún par de grupos podía alcanzar, sin comprobarlos contra el mecanismo.
- **Fix:** 001.23 se quedó con el mecanismo de pares. Una regla de cadena cubriría listas de precios sin número largo, así que el caso de cadena queda como límite aceptado (deuda 30) con un test que lo fija. Antes de escribir un ejemplo, correrlo en la cabeza contra el mecanismo real (o en el scratchpad contra el código actual). El BLOQUEADO hizo su trabajo: paró en vez de inventar una regla de cadena.

### 22. El mezzanine corto daba un falso positivo
- **Síntoma:** en la ronda 2, el render de un mezzanine corto fallaba: un clip de teléfono cuyo video termina ~50 ms antes que el audio pedía frames que el EDL ni lee.
- **Por qué engañaba:** la suite estaba verde porque los clips sintéticos tenían el video y el audio del mismo largo.
- **Causa real:** la comparación era contra el rango CON margen (`end_f`), no contra el último frame que el EDL lee de verdad.
- **Fix:** 001.26: comparar contra `need_end_f` (último frame que el EDL lee + 1); el sidecar guarda los frames reales.

### 23. En Windows, `os.replace` choca con un archivo que otro proceso lee
- **Síntoma:** dos renders a la vez chocaban 3 de cada 8 veces con `PermissionError`.
- **Por qué engañaba:** los tests corrían un render a la vez, así que nunca había otro proceso con el archivo abierto. Además, el mensaje de error culpaba a "el reproductor", que no existía: parecía un problema del usuario y era una carrera entre dos procesos.
- **Causa real:** ffmpeg abre los archivos sin `FILE_SHARE_DELETE`, así que `os.replace` sobre un archivo que otro proceso está leyendo falla.
- **Fix:** parcial con pid por proceso; si el destino ya está fresco, gana ese.

### 24. El prefijo `\\?\` de `ntpath.realpath` daba falsa alarma
- **Síntoma:** con un archivo a mitad de reemplazo, la guarda "está dentro de `.kcut/`" daba falsa alarma.
- **Por qué engañaba:** el parche de la ronda 2 fue un reintento, que tapaba el síntoma.
- **Causa real:** con un archivo a mitad de reemplazo, `ntpath.realpath` deja el prefijo `\\?\`.
- **Fix:** 001.26: quitar el prefijo en `ingest/cache_guard.py` y borrar el reintento.

### 25. pytest-xdist no acelera la suite de kcut
- **Síntoma:** midió 770.86 s con xdist contra 766.53 s sin xdist (ninguna ganancia) y dio 20 fallos.
- **Por qué engañaba:** paralelizar la suite parecía una ganancia segura. Pero la CPU ya estaba saturada por ffmpeg/x264 en los tests de integración, y los 20 fallos parecían bugs reales cuando eran del entorno.
- **Causa real:** ffmpeg/x264 ya saturan la CPU; los fallos por tiempos y por cp1252 vienen de que los workers arrancan sin `-X utf8`.
- **Fix:** se quitó de `pyproject.toml` y se desinstaló.

### 26. Tests que nunca corrían tras partir un módulo
- **Síntoma:** los 3 tests de la fila S1.5b-36 no corrieron en ninguna suite, y la suite seguía verde.
- **Por qué engañaba:** la suite seguía verde; nada fallaba, porque esos tests nunca se ejecutaban.
- **Causa real:** al partir el módulo en `*_cases.py` con `import *`, la clase no estaba en `__all__`, así que no se traía ni la recogía pytest.
- **Fix:** se agregaron al `__all__`. Al partir un módulo, comparar el número de tests recogidos antes y después.

### 27. El prefijo `\\?\` de Windows volvió por otro lado
- **Síntoma:** 001.26 lo arregló solo en `cache_guard`, y la fila 17 se cayó después en `paths.resolve_in_project` con un "sale del proyecto" falso.
- **Por qué engañaba:** pasa solo a veces.
- **Causa real:** `ntpath.realpath` de CPython 3.12 deja el prefijo cuando otro proceso crea el archivo o su carpeta entre sus dos llamadas internas.
- **Fix:** arreglarlo en el centro. `plain_path` vive en `paths.py`, y `is_inside`, `same_path`, `resolve_in_project` y `to_rel` lo aplican a los dos lados.

### 28. Un test que parchea la función que se está arreglando pasa aunque el camino real siga roto
- **Síntoma:** el test de la fila 20 parcheaba `read_wav_range` para que levantara un `OSError` que la función real nunca deja salir.
- **Por qué engañaba:** el test pasaba aunque el camino real siguiera roto.
- **Causa real:** `open_wav`, `check_wav_extent` y `_unreadable` ya convierten todo `OSError` en `ProjectError` con la ruta. El `except OSError` nuevo de `voice_track._read` era código muerto, y el test lo cubría simulando un error que no existe.
- **Fix:** probar con fallos de E/S reales (archivo borrado, bloqueado con share 0, una carpeta en su lugar).

### 29. Un heredoc escribió el carácter 0x08 en vez de `\b` en una regex
- **Síntoma:** el test de reglas JS (`innerText`, `document.write`) nunca encontraba nada.
- **Por qué engañaba:** el test pasaba en verde, y el carácter 0x08 no se ve en el editor. Una regex que nunca encuentra nada parece igual a un código que cumple la regla.
- **Causa real:** un heredoc escribió el carácter 0x08 en vez de `\b` en una regex.
- **Fix:** un test de contraste, y `tests/unit/test_source_bytes.py`, que falla si hay caracteres `Cc` en el código. Es la tercera vez que pasa.

### 30. Dos renders que aterrizan el mismo archivo a la vez
- **Síntoma:** dos renders que aterrizan el mismo archivo a la vez; Windows rechaza el `os.replace` del segundo.
- **Por qué engañaba:** quedaba escondido detrás del bug del prefijo `\\?\`, que daba el mismo exit 3 en la misma fila 17. Al arreglar el prefijo, la fila siguió fallando 1 de cada 3 veces, con otro mensaje.
- **Causa real:** entre el `os.replace` de uno y su sidecar hay unos milisegundos; si el otro intenta su `os.replace` en ese hueco, Windows lo rechaza.
- **Fix:** espera acotada de 10 s (`ingest/sidecar.wait_to_land`). No es el reintento que se quitó en 001.26: aquel tapaba un bug, este espera a otro proceso.

### 31. El resultado de la suite dependía del largo del `--basetemp`
- **Síntoma:** el resultado de la suite dependía del largo del `--basetemp`.
- **Por qué engañaba:** el test de disco lleno pasaba solo y fallaba dentro de la suite completa. Parecía intermitente, pero era la ruta de la subcarpeta, 5 caracteres más larga.
- **Causa real:** el mensaje de disco lleno pone la ruta antes de la cifra, y `cli` la recorta a 300 caracteres.
- **Fix:** pagada en S1.6b fila 16: el mensaje lleva las cifras antes de la ruta.

### 32. "3 de 3" no prueba que un fallo intermitente se fue
- **Síntoma:** S1.6a cerró con la fila 17 en 3 de 3, y en S1.6b el verificador la vio fallar 2 de 14.
- **Por qué engañaba:** con un fallo de 1 en 7, tres corridas verdes salen el 63 % de las veces.
- **Causa real:** el reemplazo del sidecar lo rechazaba Windows mientras el otro render lo leía para ver si estaba fresco.
- **Fix:** `ingest/sidecar.land_sidecar` (espera y acepta el sidecar bueno del otro). Ahora la fila pide 10 corridas seguidas; con el mismo fallo, 10 verdes salen solo el 21 % de las veces.

### 33. Un test que levanta la misma excepción que el `except` atrapa no prueba el `except`
- **Síntoma:** la fila 29 pasaba y el arranque de Chromium igual daba exit 10.
- **Por qué engañaba:** el test levantaba `playwright.sync_api.Error`, justo lo que el `except` atrapaba.
- **Causa real:** cuando falta el driver, lo que sale es `FileNotFoundError`.
- **Fix:** `except (Error, OSError)`, y el test usa la falla real: el driver apuntado a un exe que no existe. Va con la lección 28.

### 34. Una basetemp con la ruta comida cayó dentro del repo
- **Síntoma:** una corrida de la suite dio `54 failed, 547 errors`, con "los proyectos de video no van dentro del repo de kcut", y apareció en la raíz una carpeta de 916 MB con 12 junctions.
- **Por qué engañaba:** parecía una regresión enorme y era el entorno.
- **Causa real:** el shell se comió las barras invertidas de `--basetemp`.
- **Fix:** pasar la basetemp con `/` o entre comillas, mirar que `git status` no crezca, y borrar primero los enlaces (comprobando hacia dónde apuntan) y después la carpeta, siempre antes de cualquier `git add`.

### 35. Un slice entero sin commit no deja línea base
- **Síntoma:** un implementador dejó en 0 bytes un archivo de tests sin rastrear, con un script, y lo reescribió de memoria.
- **Por qué engañaba:** la cuenta de tests cuadraba, pero no hay forma de probar que no se perdió otro test.
- **Causa real:** S1.6b estuvo sin commit durante 3 rondas, así que git no tenía copia.
- **Fix:** el verificador comprobó con mutaciones que los tests de sus filas muerden. De ahora en adelante, antes de cada ronda de arreglos el coordinador copia al scratchpad los archivos sin rastrear del slice.

### 36. "El mismo frame dos veces" no ve que el resultado depende del orden
- **Síntoma:** `steps`, `sticker` y `holo_board` daban hasta 28 000 píxeles distintos para el mismo cuadro según qué cuadros había capturado Chromium antes, y `test_showpiece_deterministic` pasaba.
- **Por qué engañaba:** capturar el mismo cuadro dos veces seguidas da píxeles idénticos; la dependencia solo aparece cuando entran otros cuadros en medio.
- **Causa real:** Chromium guarda capas entre seeks, así que algunas sombras suaves se redibujan solo donde algo cambió (`will-change` es el sospechoso).
- **Fix:** reconstruir los nodos del componente en cada seek, y un test que captura en dos Chromium, ascendente y descendente, con igualdad exacta (`test_showpiece_order_independent`). Los componentes base de S1.6 tienen el mismo defecto y van a S1.8a paso 0 fila 14.

### 37. Medir antes de comprar una protección
- **Síntoma:** el timeout de screenshot de S1.7 fila 9 casi duplicó el costo de cada cuadro (1.88×).
- **Por qué engañaba:** un timeout parecía el arreglo obvio, y solo cubría la mitad del riesgo: una tarea diferida que bloquea la página después de la captura igual colgaba el siguiente seek.
- **Causa real:** `page.screenshot` no expone `optimizeForSpeed`, y lo que cuesta es la compresión PNG.
- **Fix:** quedarse con la captura CDP rápida y cerrar la amenaza en su origen con las reglas de JS, después de medir A/B contra el commit anterior.

### 38. Un criterio que choca con otro del mismo spec
- **Síntoma:** la fila 1 de S1.8a pedía "pico ≤ 1" y, a la vez, "las mismas fórmulas del piloto"; los picos crudos del piloto llegan a 1.46.
- **Por qué engañaba:** el test pasaba midiendo el pico después de la ganancia por defecto de cada efecto, una lectura que el texto no decía y que solo se cumplía para los parámetros probados (`typing` con otras semillas da 1.068).
- **Causa real:** el spec escribió una propiedad de la mezcla final (no hay clipping) como propiedad de cada SFX suelto.
- **Fix:** el implementador mantuvo las fórmulas y lo marcó (R2); el coordinador corrigió la lectura en 001.36, punto 11: según DS4, el audio queda en f32 sin clipping hasta loudnorm, que es el que pone el tope.

### 39. Un grafo de ffmpeg con dos entradas que terminan a destiempo no es determinista
- **Síntoma:** el mismo `kcut mix` daba un `mix.wav` distinto de corrida en corrida, a veces sin la cola de la música; un test que comparaba con tolerancia fallaba 1 de cada 8 veces.
- **Por qué engañaba:** el largo total y la loudness siempre daban bien, así que los criterios pasaban; el defecto solo se veía comparando dos corridas.
- **Causa real:** `sidechaincompress` cierra al ver el EOF de una de sus entradas y bota lo que tiene en su FIFO, y los hilos de ffmpeg deciden cuál llega primero.
- **Fix:** `apad` en las dos entradas del compresor, para que `amix` (que cierra con la voz) decida el largo. El test compara las dos corridas byte a byte.

### 40. Un arreglo empírico con un número mágico no es una cota
- **Síntoma:** rellenar las entradas con 16 384 muestras todavía fallaba 1 de 14 veces; con 65 536 pasaba.
- **Por qué engañaba:** 30 de 30 corridas verdes parecían prueba suficiente.
- **Causa real:** el corte podía llegar a 23 616 muestras, y nada garantizaba que 65 536 alcanzara siempre.
- **Fix:** buscar el arreglo que quita la causa (`apad`), no el que agranda el margen.

---

## Descartado y por qué

| Qué | Por qué | Fecha |
|---|---|---|
| Remotion como motor | Ya descartado en Korvex Motion ("Remotion en cualquier forma… solo ideas"): licencia con umbral de tamaño de equipo, y renderizar en Chrome es lento para piezas largas | 13/10/2026 |
| HyperFrames como dependencia | Release diario (piso inestable), telemetría activada por defecto, bugs abiertos en Windows; el motor HTML propio hace lo mismo. Se usan sus ideas (intermedios con audio PCM) | 13/10/2026 |
| ElevenLabs Scribe por defecto | Servicio de pago y el crudo sale de la máquina. Local primero; Scribe solo como plan B con tope de gasto | 13/10/2026 |
| Tone-map por GPU con `libplacebo`/Vulkan en Iris Xe | Falla al configurar la salida en dos intentos | 14/10/2026 |
| `cv2.CascadeClassifier` | Eliminado en OpenCV 5 | 14/10/2026 |
| Descargar assets sin aprobación | Toda descarga necesita OK explícito; logos de marcas ajenas solo del kit oficial | 15/10/2026 |
| Rastreo de manos y detección de caras (F2: `piloto/track.py`, YuNet/MediaPipe, blur automático de caras) | Yedin, 26/10/2026: "no lo usaremos, todo el que vaya a pertenecer será parte del video, tenemos que hacer muchos procesos básicos y ya". Quien sale en cámara forma parte del video (consentimiento en la entrevista); los componentes van sin rastreo y se posicionan a mano | 26/10/2026 |
| pytest-xdist para paralelizar la suite | Midió 770.86 s contra 766.53 s sin xdist: ninguna ganancia, porque ffmpeg/x264 ya saturan la CPU. Además dio 20 fallos, por tiempos y por cp1252 (los workers arrancan sin `-X utf8`). Se quitó de `pyproject.toml` y se desinstaló | 27/10/2026 |
| Tope de la foto con `page.screenshot(timeout=...)` (S1.7 fila 9 de 001.33) | Costaba 1.88 × por frame (37.0 contra 69.6 ms, A/B de 5 rondas): `page.screenshot` no expone `optimizeForSpeed`. Además solo cubría la mitad del riesgo; la amenaza se cierra en su origen con las reglas JS (spec 001.34 punto 1, lección 37) | 27/10/2026 |
