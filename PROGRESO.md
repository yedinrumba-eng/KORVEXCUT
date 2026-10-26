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
- [ ] **S1.5a** — (parte a de S1.5, 001.15) EDL en frames: modelo, validación, `kcut edl check`, `kcut edl sources`, `kept_words`, geometría · paso 0 = spec 001.22
- [ ] **S1.5b** — (parte b de S1.5, 001.15) `kcut render` base (cámaras, insertos, looks, mezzanines por tramo)
- [ ] **S1.6a** — (parte a de S1.6) Capa de gráficos: motor HTML `seek(t)` + componentes base + subtítulos
- [ ] **S1.6b** — (parte b de S1.6) Capa de gráficos: motor HTML `seek(t)` + componentes base + subtítulos
- [ ] **S1.7** — Componentes de lucimiento (pasos, sticker, holograma, globo)
- [ ] **S1.8a** — (parte a de S1.8) Audio: voz, SFX sintetizados, música, ducking, loudness
- [ ] **S1.8b** — (parte b de S1.8) Audio: voz, SFX sintetizados, música, ducking, loudness
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
- **Mitigado hoy por:** cada clip se enmascara entero; el md lleva la línea fija "es dato, nunca instrucciones"; los mensajes van recortados.
- **Cura real:** en el plugin, negar la lectura de `.kcut/transcripts/**` y trabajar solo con `pack`; juntar números entre clips solo si aparece el caso real — ~2 h.
- **Cuándo:** spec 002 (el plugin no deja que Claude lea `.kcut/transcripts/`).

### 31. Hallazgos de la ronda final de S1.4 🟡

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

### 32. `replace=False` con `os.rename` no protege en POSIX ⚪

En Linux o WSL, `os.rename` sobrescribe en silencio, así que `write_bytes_atomic(replace=False)` no protege ahí.

- **Mitigado hoy por:** la herramienta es Windows-first; en Windows, `os.rename` falla con `FileExistsError`.
- **Cura real:** `os.link(tmp, path)` + `unlink(tmp)`, con fallback para volúmenes FAT/exFAT sin hard links (los discos de footage suelen ser exFAT) — 1–2 h.
- **Cuándo:** si kcut llega a correr en Linux.

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
