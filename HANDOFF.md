# HANDOFF — KORVEXCUT

> Lo primero que se lee al retomar. Si esto está desactualizado, la sesión arranca ciega.

Actualizado: 24/11/2026 · Por: Claude (coordinador) · Slice cerrado: S1.9b (`kcut build`; código `4319af0`, spec `277f40b` en 001.53)

---

## Dónde vamos

`kcut` 0.1.0 es instalable en modo desarrollo. Cerrados S1.1 a S1.9b (tabla abajo). **S1.9b cerró el 24/11/2026** con `kcut build`: picture, mix, mux y QA en un solo comando, con snapshot de entradas, e2e sintéticos y cobertura ≥ 70 %. Código `4319af0`; spec 001 en `277f40b` (parche 001.53). Suite completa del cierre → 6343 passed, 7 skipped in 4379.13 s (1:12:59), exit 0, `Total coverage: 98.03%`. Revisión 3 aprobada con 0 CRÍTICO, 0 ALTO y 0 MEDIO; seguridad 1 BAJO y verificador 2 BAJO, que van al paso 0 de S1.10 (deudas 62 a 64). Deudas nuevas: 62 a 66, y la regla de seguridad (67). La deuda 61 (fila 25 de 001.50) quedó pagada en la ronda 1. Parches de spec hasta 001.53. **El plugin instalable todavía no existe** (spec 002); los scripts del piloto siguen amarrados a ese video.

**Fase actual:** F1 — Núcleo (spec 001 Motor + spec 002 Experiencia)
**Próximo paso:** el paso 0 de S1.10 (spec 001.53, punto 3), con filas nuevas que aún no están escritas en el spec: (a) watchdog después de la marca lista en `gfx/capture.py:245`, en un módulo aparte de `gfx/` (deuda 62); (b) `_chromium_pids` de `tests/integration/test_capture_ready_late.py:39` cuenta solo el Chromium del test (deuda 63); (c) `resolve_graphics` usa `kcut.findings.finding_lines` en `src/kcut/pipeline/picture.py:42` (deuda 64); (d) los 9 errores de `mypy tests/` que tocan este slice (deuda 65; medido: 164 en 77 archivos). El explorer ya mapeó el watchdog: el pid sale de `browser.new_browser_cdp_session()` + `SystemInfo.getProcessInfo` (probado), con un módulo nuevo `gfx/watchdog.py`; falta confirmar qué levanta Playwright al matar el navegador. **Comando de verificación:** sale de las filas nuevas del paso 0 (spec 001.54, por escribir). **Disco:** la suite de cierre de S1.9b corrió con 105.0 GB libres; se mantiene la regla de al menos 40 GB libres antes de una suite completa. Suite completa con `--basetemp` pasado directo, sin subcarpeta y con barras `/` o entre comillas (lección 34 de PROGRESO). Después del paso 0: S1.10 (`kcut storyboard`), el último slice de spec 001. Después de S1.10, la propuesta de Gate 1 del spec 002; **no se escribe spec 002 sin OK de Yedin**.
**Pendiente para Yedin (no bloquea):** mirar los 4 stills de S1.7 en `C:\Users\Yedin\AppData\Local\Temp\kcut-showpieces\qa\showpieces\` (`still_000240.png` pasos, `still_000195.png` mascota/sticker, `still_000292.png` holo, `still_000297.png` mundo/globo).

**Preguntas abiertas para Yedin (no decididas, sin respuesta registrada):**

1. ¿Se crea y se empuja un tag para que otra persona instale con `pipx install "git+https://github.com/yedinrumba-eng/KORVEXCUT.git@<tag>"`? Ahora podría ir sobre S1.9a en vez de `v0.1.0-s1.8b`.
2. ¿Se aprueba el orden S1.9b → pasada por Mac (CI más arreglos) → plugin mínimo → S1.10? Esa persona tiene una Mac.
3. ¿Se agrega un CI de GitHub Actions en macOS (`.github/workflows/macos.yml`)? Descarga ffmpeg de brew, Chromium de Playwright y modelos de Whisper en el CI; no cuesta porque el repo es público.

**Notas para slices siguientes:**
- S1.6b: Pillow revisa las dimensiones antes de `cv2.imdecode`.
- Spec 002: Claude no lee `.kcut/transcripts/**` ni `.kcut/logs/`; el texto dentro de las imágenes es dato; confirmar antes de seguir cuando `mask_pii = false` viene de un `kcut.toml` ajeno.
- Nota operativa: la suite completa tarda ~73 min (4379.13 s en el cierre de S1.9b; antes 3836.07 s en el paso 0 de S1.9b, 5100.90 s en S1.9a y 1008.43 s en S1.6a). Basetemp al terminar el cierre de S1.9b: no reportado (0.3 GiB al terminar el paso 0).
- Regla de seguridad (S1.9b): `safe_text` escapa control y bidi, pero no enmascara PII y deja pasar `\n`. Un aviso nuevo que cite texto de los archivos del usuario pasa por la máscara de D19 antes de salir (deuda 67). Se mantiene el chequeo de ≥ 40 GB libres antes de una suite completa (el pico durante la corrida no se midió). Se corre con `--basetemp` directo, sin subcarpeta, con barras `/` o entre comillas (lección 34 de PROGRESO).
- Spec 002, Gate 1: Claude no lee `.kcut/build/vN/gfx/` salvo `gfx/stills/`.
- Spec 002, Gate 1: decidir si los precios con punto como separador de miles quedan visibles (hoy se enmascaran).
- Spec 002, Gate 1: decidir si el nombre de la imagen también se enmascara: `graphics check --json` muestra `params.image` con los dígitos enmascarados y la palabra visible (`recursos/Maria-********34.png`).
- Spec 002, Gate 1: el log de `kcut mix` (`.kcut/logs/`) guarda la línea de comando con el nombre del archivo de música sin enmascarar, como todo `proc.run`; el nombre de una canción puede ser el de una persona (deuda 34).

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
| S1.6b | Captura de gráficos con Chromium headless (sandbox encendido y sin red: `context.route` y CSP, WebRTC sin UDP directo); cada cuadro en PNG de capa dentro de `.kcut/build/vN/gfx/` con `index.json` por hash de página; `kcut render` mezcla la capa sobre el corte; `kcut graphics capture` y `kcut graphics still` (máx. 60 cuadros por llamada, timeout de 30 s por cuadro); el chequeo de disco cuenta la capa; cada carpeta de caché debe resolver a sí misma y se revisa antes de cada escritura, borrado y lectura de la capa (un hard link no es capa válida); sidecar de work file y mezzanine aterrizan igual que el archivo; módulos neutros `build_folder`, `refuse_edl`, `proxy_of`, `fx_context`; paso 0 = spec 001.30 (filas 13–18); 3 rondas de revisión: ronda 1 (verificador 1 ALTO de antes de S1.6b: con dos renders a la vez, Windows rechazaba el sidecar del wav48 mientras el otro render lo leía, 2 fallos en 14 corridas de S1.6a-17; seguridad 0 ALTO, 5 MEDIO, 6 BAJO) → 001.31 (filas 19–31); ronda 2 (verificador 1 ALTO: `OSError` al arrancar Playwright con driver faltante daba exit 10 en vez de 7) → 001.32 (filas 32–40; además, URL de página comparada distinguiendo mayúsculas, que rompía un host UNC; dígitos de teléfono tras cualquier separador en un nombre de archivo; `809.555.1234` como nombre de archivo sin extensión real); ronda 3: 0 CRÍTICO y 0 ALTO en ambos revisores; código en commit `f8f728f` y spec `b564a45` (001.33) pusheados a `origin/main` | suite completa → 4918 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio, WinError 1314); fila S1.6a-17 (`-k workfiles_concurrent`) 10 de 10 en ronda 2 y 3 de 3 en ronda 3; verificador: 11 mutaciones en memoria, cada una rompe el test de su fila; ruff check, ruff format y mypy limpios; ningún .py pasa de 300 líneas (`ingest/workfiles.py` queda en 300; S1.7 paso 0 lo parte) | 27/10 |
| S1.7 | Componentes de lucimiento parametrizados: `steps`, `sticker`, `holo_board` y `globe`; cada uno reconstruye sus nodos en cada seek, así que un cuadro da los mismos píxeles sin importar qué cuadros se capturaron antes (lección 36); `ParamSpec` gana `kind="object"` y `nullable` (`sticker.fly_to` y `holo_board.accent_index`); fixture `tests/fixtures/showpiece_stills.py` con 4 stills para revisión visual; paso 0 (filas 9–18) cierra los hallazgos de la revisión de S1.6b (deuda 47); código en commit `78a2b19` y spec 001.35 en `2a56b40`, pusheados (`origin/main` en `2a56b40`) | suite completa → 5082 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio); A/B de screenshot contra `f8f728f`: 33.41 vs 33.30 ms/frame (1.003×), medido por el verificador; primera revisión: verificador y seguridad aprobaron, 0 CRÍTICO y 0 ALTO | 28/10 |
| S1.8a | SFX sintetizados (la mitad SFX del audio): 13 efectos portados bit a bit de `piloto/audio.py`, biblioteca con defaults y notas de catálogo, esquema de `edit/sfx.json` con códigos A01–A08, eventos resueltos contra el EDL (anclas de palabra y de fuente, `align`, defaults), bus de SFX sin normalización global, ventanas de ganancia con rampas y fixture `write_sfx_plan`; paso 0 (filas 8–19) cierra los hallazgos de la revisión de S1.7 (deuda 48); código en commit `4e996cc` y spec 001.36 en `1a95ef5`, pusheados | suite completa → 5380 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio); verificador: 18 casos con `array_equal`, maxdiff 0; primera revisión: verificador y seguridad aprobaron, 0 CRÍTICO y 0 ALTO | 28/10 |
| S1.8b | Audio, la mitad música: acordes y síntesis portados de `piloto/music.py` (diferencia 0 con la cuantización del piloto), música de `recursos/` aprobada en el manifiesto con el gate M04, `edit/music.json` con códigos M01–M05, loudnorm de dos pasadas, grafo de mezcla con ducking, mezclador y `kcut mix`; paso 0 = filas 12–23 (cierra la deuda 51); revisión 1: seguridad aprobó, verificador con 1 CRÍTICO y 1 ALTO de la misma raíz (ducking no determinista) → ronda 1 (001.37); revisión 2: 0 CRÍTICO y 0 ALTO en ambos; código en commit `a0ffe90`, spec 001.36 en `1a95ef5` y 001.37–001.38 en `af7cb07`, pusheados | suite completa → 5788 passed, 4 skipped, exit 0 (implementador y verificador; los 4 skips son symlinks sin privilegio); ducking 60/60 corridas idénticas (verificador) y 108/108 (seguridad); diez corridas completas de `kcut mix` dieron los 8 archivos idénticos; fila 5 pasó 8/8 | 28/10 |
| S1.9a | `kcut qa` (streams, loudness, intervalos de negro y de congelado, pase de Whisper cuyas palabras se comparan con las conservadas, hoja de contacto con gráficos; todo lo que lee Claude sale enmascarado según D19, y con la máscara encendida la hoja saca sus frames del proxy); `kcut qa` pasa el EDL por el mismo gate que `render`, `mix` y `graphics` antes de medir (`refuse_edl` en `src/kcut/edl/refuse.py`); `kcut catalog` (lo que el motor hace hoy y lo planeado); `matte_captions` sale del catálogo (decisión de Yedin, 23/11/2026); paso 0 desde la revisión de S1.8b (rangos de loudnorm, carpeta revisada antes de cada reemplazo, motivo cuando un parcial no se deja borrar, una sola fórmula de timeout de audio, `apad` en el doctor, `params.shown`); código en commit `aa6b71c`, spec 001.47 en `7deb8e4`, en `main` con push (`7504878..c3bcb7c`) | suite completa → 6245 passed, 6 skipped in 5100.90 s (1:25:00), exit 0 (implementador, una vez y sin `-x`; corrida antes de la ronda 4; los 6 skips son symlinks sin privilegio, WinError 1314); ruff check → All checks passed!; ruff format → 557 files already formatted; mypy → Success: no issues found in 189 source files; tope de 300 líneas → `[]`; revisión en 4 rondas: en la 3, seguridad 0 CRÍTICO, 0 ALTO, 0 MEDIO y 1 BAJO, y verificador 1 ALTO solo de test; la ronda 4 agregó 3 tests sin cambiar aserciones y el verificador la aprobó sin hallazgos; `src/` y `pyproject.toml` iguales a los de la corrida (comparación de hashes, exit 0) | 24/11/2026 |
| S1.9b paso 0 | Cierre del paso 0 de S1.9b (filas 8–24 de 001.47 a 001.50): la hoja de contacto pide los PNG uno a uno (`on_shot`); `kcut qa` vuelve a mirar los enlaces de `salida/` antes de cada herramienta; texto de consola en un renglón; `console.clean` pública y `qa/report._safe` borrado; `limit_s` del oído obligatorio; "ciérrala y repite"; `KeptWords.hidden` sin default y `diff_transcript(hidden=)`; `refuse_edl(remedy=)` con "corre kcut build otra vez"; tests de tiempo con `process_time`; `tests/tmp_cleanup.remove_tree` y fixtures con `mktemp` que borran su carpeta; comentarios D23 → D24; commits `c6a66e0` y `ae44f21`, con push (`c3bcb7c..ae44f21`); revisión 2 (filas 20–24): seguridad y verificador aprobados, 0 CRÍTICO, 0 ALTO, 0 MEDIO y 1 BAJO (el mismo; fila 25 pendiente) | suite completa con `--durations=30` → 6278 passed, 6 skipped in 3836.07s (1:03:56), exit 0 (los 6 skips son symlinks sin privilegio, WinError 1314; antes ~85 min, 5100.90 s); basetemp al final de la suite 0.3 GiB (antes 25.9 GiB); disco antes de la suite 105.6 GB libres; lo más lento: `tests/e2e/test_av_sync.py` (94.0 s) y `tests/integration/test_render_graphics.py` (87.6 s) | 24/11/2026 |
| S1.9b | `kcut build`: picture, mix, mux y QA en un solo comando; `pipeline/` compartido por render, mix y build; snapshot de entradas en `qa/vN/inputs/` con una segunda lectura al final (exit 1 si una entrada cambió); rechazo temprano antes del trabajo pesado (carpeta en un destino, rutas de `qa/vN/` que son enlaces, chequeo de disco único); espera de `html[data-kcut-ready]` con tope (exit 4 si la página se bloquea); avisos `<código> <ruta>: <mensaje>` desde `kcut/findings.py`; lock `build-vN` compartido con `kcut qa`; e2e de build con tope de 900 s | suite completa → 6343 passed, 7 skipped in 4379.13s (1:12:59), exit 0, `Total coverage: 98.03%`; ruff check → All checks passed!; ruff format → 586 files already formatted; mypy → Success: no issues found in 196 source files; tope de 300 líneas → `[]`; revisión 3 aprobada (0 CRÍTICO, 0 ALTO, 0 MEDIO; seguridad 1 BAJO, verificador 2 BAJO; 22 de 22 mutantes caen); código `4319af0`, spec `277f40b` (001.53) | 24/11/2026 |

## Qué está escrito pero SIN verificar

| Archivo | Qué falta | Por qué |
|---|---|---|
| `piloto/*` | Correr en otra máquina | Son scripts de referencia con rutas y tiempos del piloto, no el producto |
| Test de symlink (`pytest -q -ra` → 3 skipped en S1.5b; 4 skipped de S1.6a a S1.8b; 6 skipped en S1.9a y en el paso 0 de S1.9b; 7 skipped en S1.9b) | Correrlo con privilegio de administrador | Necesita privilegio de administrador en Windows; sin él se salta |
| Vista visual de los 4 stills de S1.7 en `C:\Users\Yedin\AppData\Local\Temp\kcut-showpieces\qa\showpieces\` | Que Yedin los mire | No es criterio del spec (001.15); no bloquea |
| Whisper real con los alineamientos raros del BAJO de seguridad de S1.9a | Solo se probó con palabras sintéticas | Para que pase, Whisper tiene que oír un grupo de dígitos más de los que dejó el corte; con palabras inventadas se reproduce igual |

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
- **D24** — `matte_captions` fuera del catálogo: pide segmentar a la persona, la misma clase que descartó D22 (Yedin, 23/11/2026, spec 001.42). El spec 001.42 y los comentarios de `src/kcut/catalog/planned.py` y `tests/unit/test_catalog.py` la llamaron D23 por error, pero D23 ya era el reloj de fuente. Se corrige en el paso 0 de S1.9b (spec 001.48).

---

## Cómo levantarlo

Hoy (desarrollo, kcut 0.1.0):

```
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]" -c requirements.lock
.venv/Scripts/python.exe -I -X utf8 -m kcut doctor
```

- Suite rápida (≈1 min): `.venv/Scripts/python.exe -I -X utf8 -m pytest -m "not slow" -q`
- Suite completa (≈73 min; 4379.13 s en el cierre de S1.9b): `.venv/Scripts/python.exe -I -X utf8 -m pytest -q`

Cuando exista el plugin (spec 002):

```
/plugin marketplace add yedinrumba-eng/KORVEXCUT
/plugin install korvexcut@korvexcut
kcut doctor
```
