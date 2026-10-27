# HANDOFF — KORVEXCUT

> Lo primero que se lee al retomar. Si esto está desactualizado, la sesión arranca ciega.

Actualizado: 27/10/2026 · Por: Claude (coordinador) · Slice cerrado: S1.6a

---

## Dónde vamos

`kcut` 0.1.0 es instalable en modo desarrollo. Cerrados S1.1 (`kcut doctor`, 11/11 ok), S1.2 (`kcut new` + `kcut ingest`, `pytest -q -ra` → 1238 passed, 3 skipped), S1.3 (`kcut transcribe` + `kcut pack`, `pytest -q -ra` → 2332 passed, 3 skipped; código en commit `7ee3c92`, pusheado) y S1.4 (`kcut view` + `kcut frames`, suite completa → 2968 passed, 3 skipped; commit `40e9c65`, pusheado a `origin/main`) y S1.5a (`kcut edl check` + `kcut edl sources`, EDL en frames, `kept_words` y geometría; suite completa → 3331 passed, 3 skipped; commit `6605456`, pusheado a `origin/main`) y S1.5b (`kcut render` base: cámaras e insertos, looks, frame fx y tarjetas de pantalla; mezzanines por tramo con sidecar de frames reales, parciales con pid y aterrizaje seguro entre procesos; voz exacta a la muestra desde el wav48, con fades; lock por versión del build y mux A/V a `render.mp4`; suite completa → 3943 passed, 3 skipped; código en commit `1d8cf00`, pusheado a `origin/main`, que quedó en `a46223d`) y **S1.6a** (capa de gráficos hasta la página HTML: esquema de `graphics.json` con anclas y parámetros, subtítulos por chunks, cues a frames de salida, imágenes aprobadas, página con runtime JS y 5 componentes base, `kcut graphics check` con G01–G12 y JSON enmascarado; suite completa → 4432 passed, 4 skipped in 1008.43 s, exit 0; commits `fdb19a3` y `3261492`, pusheados a `origin/main`). Parches de spec: S1.3 001.10 a 001.17; S1.4 001.18 a 001.21; S1.5a 001.22 a 001.23; S1.5b 001.24 a 001.27; S1.6a: paso 0 en 001.27 y cierre en 001.30. La deuda 33 quedó pagada en S1.5b por el paso 0 (001.24). **El plugin instalable todavía no existe** (spec 002); los scripts del piloto siguen amarrados a ese video.

**Fase actual:** F1 — Núcleo (spec 001 Motor + spec 002 Experiencia)
**Próximo paso:** S1.6b — captura con Chromium, mezcla alfa, `graphics capture/still`, render con gráficos. Arranca con **paso 0** = spec 001.30, filas 13–18 (deudas 35 y 39–42 y lección 31 en PROGRESO). **Comando de verificación:** los de la tabla "Criterios de aceptación S1.6b" del spec (filas 1–18). Suite completa con `--basetemp` directo, sin subcarpeta (ver nota operativa). Después de S1.6b: S1.7 → S1.8a → S1.8b → S1.9a → S1.9b → S1.10. Después de S1.10, la propuesta de Gate 1 del spec 002.

**Notas para slices siguientes:**
- S1.6b: Pillow revisa las dimensiones antes de `cv2.imdecode`.
- Spec 002: Claude no lee `.kcut/transcripts/**` ni `.kcut/logs/`; el texto dentro de las imágenes es dato; confirmar antes de seguir cuando `mask_pii = false` viene de un `kcut.toml` ajeno.
- Nota operativa: la suite completa tarda ~17 min (1008.43 s en S1.6a). Se corre con `--basetemp` directo, sin subcarpeta, hasta que cierre la fila 16 de S1.6b (lección 31 de PROGRESO).

---

## Qué está construido y verificado

| Pieza | Qué hace | Verificado con | Fecha |
|---|---|---|---|
| Piloto 01 v4 | Reel 9:16 de 49 s: multicam, cortes, subtítulos, gráficos, música, SFX | `qa.py` → 1469/1469 frames, A/V 0 ms, −14.4 LUFS, pico −1.4 dBFS | 15/10 |
| S1.1 | Paquete kcut + `kcut doctor` | `kcut doctor --json` → 11/11 ok; `pytest -q -ra` → 154 passed, 1 skipped | 16/10 |
| S1.2 | kcut new + kcut ingest (layout del proyecto y `kcut.toml`, inventario con ids estables, probe HDR/VFR, proxies bt709, sincronía de audio multicam con piso de solape, guardas de refinado débil y de ambigüedad, `SYNC_VERSION`, logs seguros por corrida, validación de caché no confiable, scrub de metadatos, consola limpia) | pytest -q -ra → 1238 passed, 3 skipped; suite rápida 1108 passed en 70 s | 17/10 |
| S1.3 | kcut transcribe + kcut pack (transcripción local con faster-whisper y caché validada, silencios por energía, frases y marcadores, votación de dos cámaras, `transcripcion.md` / `palabras.tsv`, endurecimiento ante inyección de prompt y PII enmascarada en todo lo que lee Claude) | pytest -q -ra → 2332 passed, 3 skipped | 26/10 |
| S1.4 | kcut view + kcut frames (timeline PNG con cajas de palabras enmascaradas, filmstrip, frames y hoja ≤25 Mpx sin upscale, `FrameReader` con topes de 60 s y 64 MB, `PROXY_MISMATCH`, escritura fuera de `.kcut/` sin `--force`; PII: paso 0 + 3 rondas, 001.18–001.21) | suite completa → 2968 passed, 3 skipped (456.59 s, exit 0); ruff check, ruff format y mypy limpios; criterios S1.4 1–41 exit 0 | 26/10 |
| S1.5a | EDL en frames: modelo, parseo, validación (E01–E09, E11–E15, E17, E18; W01–W05; E10 y E16 reservados), aritmética de frames con `Fraction`, gate que cierra a `no` ante cualquier duda, `kcut edl check` (`--json`) y `kcut edl sources`, `kept_words` (`words` crudo y `shown` enmascarado, con `cover` entre cámaras), geometría (cover, crops, easings, `upscale_factor`); paso 0 (001.22–001.23) incluido | suite completa → 3331 passed, 3 skipped (implementador 442.57 s, verificador 606.77 s; exit 0 en ambas); ruff check, ruff format y mypy limpios; chequeo de 300 líneas → `[]`; criterios S1.5a 1–26 exit 0; `kcut edl check` → `"ok": true`, `frames: 345`, un W01 en `spans[3]` | 26/10 |
| S1.5b | `kcut render` base: cámaras e insertos, looks, frame fx y tarjetas de pantalla; mezzanines por tramo con sidecar de frames reales, parciales con pid y aterrizaje seguro entre procesos (si otro proceso ya dejó el archivo fresco, gana ese); pista de voz exacta a la muestra desde el wav48, con fades; lock por versión del build y mux A/V a `render.mp4`; guardas de destino y de enlaces en `.kcut/build/vN`; paso 0 de 001.24 (deuda 33) incluido | suite completa → 3943 passed, 3 skipped in 3025.40s (0:50:25), exit 0 (los 3 skipped son por falta de privilegio para symlinks en Windows); ruff check src tests → All checks passed!; ruff format --check src tests → 313 files already formatted; mypy → Success: no issues found in 124 source files; tope de 300 líneas → `[]`; criterios S1.5b 1–59 exit 0; repros de concurrencia: stagger_row39 8/8 y wav48_race 5/5 con `[0, 0]`; mezzanine corto 3/3 exit 0; revisión en 3 rondas, ronda 3 con 0 CRÍTICO y 0 ALTO | 27/10 |
| S1.6a | Capa de gráficos hasta la página HTML: esquema de `graphics.json` con anclas y parámetros, subtítulos por chunks, resolución de cues a frames de salida, imágenes aprobadas, página con runtime JS y 5 componentes base, `kcut graphics check` (G01–G12, JSON enmascarado); paso 0 de 001.27 incluido (barrido de parciales huérfanos, `encoding=` obligatorio, chequeos de `build/vN`, `write_json_exclusive`, hard links marcados como stale); 2 rondas de revisión (ronda 1: verificador 1 CRÍTICO (los errores de `wavio` sacaban la ruta del wav48, con slug y teléfono), seguridad 2 MEDIO y 4 BAJO, implementador BLOQUEADO en fila 17; ronda 2: verificador y seguridad 0 CRÍTICO y 0 ALTO, segundo BLOQUEADO del implementador en fila 17); commits `fdb19a3` y `3261492` pusheados a `origin/main` | suite completa → 4432 passed, 4 skipped in 1008.43s (0:16:48), exit 0 (los 4 skips son de symlinks sin privilegio, WinError 1314, aceptados); fila 17 `-k workfiles_concurrent` 3 corridas sueltas → 7 passed las 3; ruff check, ruff format y mypy limpios; ningún .py pasa de 300 líneas | 27/10 |

## Qué está escrito pero SIN verificar

| Archivo | Qué falta | Por qué |
|---|---|---|
| `piloto/*` | Correr en otra máquina | Son scripts de referencia con rutas y tiempos del piloto, no el producto |
| Test de symlink (`pytest -q -ra` → 3 skipped en S1.5b; 4 skipped en S1.6a) | Correrlo con privilegio de administrador | Necesita privilegio de administrador en Windows; sin él se salta |

---

## Decisiones

- **D1** — Motor: ffmpeg + Python; los gráficos con un motor HTML determinista (`seek(t)`) compuesto como capa con alfa. Chrome nunca procesa el crudo largo.
- **D2** — F1 primero; un spec por fase.
- **D3** — Repo público solo con código y docs. El trabajo de cada video (crudos, renders, cachés) vive fuera de git.
- **D4** — Absorber la skill vieja `edicion-de-video` cuando F1 funcione; Korvex Motion sigue para motion puro; los dos comparten perfil y marca del cliente.
- **D5** — Revisión por chat; Claude lo registra en `versiones.md` de cada video.
- **D6** — Licencia MIT.
- **D7** — El agente buscador de assets va en F1 (spec 002). El motor define el manifiesto `recursos/`: origen, licencia, fecha y quién aprobó. Toda descarga necesita OK explícito.
- **D8** — Cada proyecto arranca con una **entrevista** corta (propósito, público, plataforma, duración, energía, referencias, marca, música, consentimiento). Después de ver el material viene el **menú de ideas**: 3 recetas, momentos detectados en el crudo y el catálogo completo. El catálogo sale de `kcut catalog`: solo lista lo que el motor de verdad sabe hacer.
- **D9** — F1 se parte en dos specs: **001 Motor** (`kcut`) y **002 Experiencia** (plugin, entrevista, menú, buscador, aceptación con un segundo video real).
- **D10** — Looks básicos de color y contraste en el motor de F1.
- **D11** — Piloto 01: los primeros 14 s se quedan como están.
- **D12** — El borrador de la Puerta 1 es un **storyboard visual**: frame real + gráfico encima + texto + sonido por momento (`kcut storyboard`, S1.10), antes de cualquier render completo.
- **D13** — Soportar ffmpeg 7 y 8 (Yedin, 16/10/2026).
- **D14** — Dependencias con pisos + `requirements.lock` de versiones exactas; `Pillow>=12.3` (Yedin, 16/10/2026).
- **D15** — Piso de solape de la sincronía en 0.75 del clip más corto (Yedin, 16/10/2026, spec 001.5).
- **D16** — Umbral de correlación fina `min_refine_corr` 0.1, configurable; y el EDL guardará el `qhash` de cada fuente para negarse a cortar un archivo que cambió (Yedin, 16/10/2026, spec 001.6).
- **D17** — Clips cortos con dos desfases posibles se rechazan como `sync_ambiguous` en vez de aceptarse callados (Yedin, 17/10/2026, spec 001.7).
- **D18** — Toda salida de kcut a consola o `--json` pasa por `safe_text`, y el `--json` no repite texto libre del proyecto. Esa salida la lee Claude, así que es una vía de inyección de prompt (coordinador, 17/10/2026, spec 001.8).
- **D19** — PII enmascarada en todo lo que lee Claude (transcripción, tsv, `--json`, imágenes de view/stills/storyboard, diffs de QA); el MP4 final conserva el texto real (Yedin, 25/10/2026, specs 001.13 y 001.15).
- **D20** — Subtítulos por defecto desde la transcripción cuando no hay `edit/graphics.json` (Yedin, 25/10/2026, spec 001.15).
- **D21** — Reglas de autonomía de la sesión larga: Puerta 3 delegada si los revisores aprueban sin críticos ni altos; push al cerrar cada slice; ronda 4 corta ante ALTO chico; regla de corte tras la ronda 5 (Yedin, 25–26/10/2026).
- **D22** — Rastreo de manos y detección de caras descartados: quien sale en cámara es parte del video (Yedin, 26/10/2026).
- **D23** — Un solo reloj de fuente: el wav ya viene alineado al contenedor; solo se corrige el video con `vs_f` (coordinador, 25/10/2026, spec 001.15).

---

## Cómo levantarlo

Hoy (desarrollo, kcut 0.1.0):

```
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]" -c requirements.lock
.venv/Scripts/python.exe -I -X utf8 -m kcut doctor
```

- Suite rápida (≈1 min): `.venv/Scripts/python.exe -I -X utf8 -m pytest -m "not slow" -q`
- Suite completa (≈17 min; 1008.43 s en S1.6a): `.venv/Scripts/python.exe -I -X utf8 -m pytest -q`

Cuando exista el plugin (spec 002):

```
/plugin marketplace add yedinrumba-eng/KORVEXCUT
/plugin install korvexcut@korvexcut
kcut doctor
```
