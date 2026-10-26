# HANDOFF — KORVEXCUT

> Lo primero que se lee al retomar. Si esto está desactualizado, la sesión arranca ciega.

Actualizado: 26/10/2026 · Por: Claude (coordinador) · Slice cerrado: S1.3

---

## Dónde vamos

`kcut` 0.1.0 es instalable en modo desarrollo. Cerrados S1.1 (`kcut doctor`, 11/11 ok), S1.2 (`kcut new` + `kcut ingest`, `pytest -q -ra` → 1238 passed, 3 skipped) y S1.3 (`kcut transcribe` + `kcut pack`, `pytest -q -ra` → 2332 passed, 3 skipped; código en commit `7ee3c92`, pusheado). Parches de spec de S1.3: 001.10 a 001.17, 001.15 (pre-vuelo de S1.4–S1.10) y 001.18 (paso 0 de S1.4). **El plugin instalable todavía no existe** (spec 002); los scripts del piloto siguen amarrados a ese video.

**Fase actual:** F1 — Núcleo (spec 001 Motor + spec 002 Experiencia)
**Próximo paso:** S1.4 — `kcut view` + `kcut frames`. Arranca con **paso 0** = spec 001.18 (restos de PII de S1.3). Se verifica corriendo los comandos de los criterios S1.4 1–21 del spec, más la suite completa (`.venv/Scripts/python.exe -I -X utf8 -m pytest -q -ra -p no:cacheprovider`). Después: S1.5a → S1.5b → S1.6a → S1.6b → S1.7 → S1.8a → S1.8b → S1.9a → S1.9b → S1.10. Luego, el explorador deja lista la propuesta de Gate 1 del spec 002 (plugin).

---

## Qué está construido y verificado

| Pieza | Qué hace | Verificado con | Fecha |
|---|---|---|---|
| Piloto 01 v4 | Reel 9:16 de 49 s: multicam, cortes, subtítulos, gráficos, música, SFX | `qa.py` → 1469/1469 frames, A/V 0 ms, −14.4 LUFS, pico −1.4 dBFS | 15/10 |
| S1.1 | Paquete kcut + `kcut doctor` | `kcut doctor --json` → 11/11 ok; `pytest -q -ra` → 154 passed, 1 skipped | 16/10 |
| S1.2 | kcut new + kcut ingest (layout del proyecto y `kcut.toml`, inventario con ids estables, probe HDR/VFR, proxies bt709, sincronía de audio multicam con piso de solape, guardas de refinado débil y de ambigüedad, `SYNC_VERSION`, logs seguros por corrida, validación de caché no confiable, scrub de metadatos, consola limpia) | pytest -q -ra → 1238 passed, 3 skipped; suite rápida 1108 passed en 70 s | 17/10 |
| S1.3 | kcut transcribe + kcut pack (transcripción local con faster-whisper y caché validada, silencios por energía, frases y marcadores, votación de dos cámaras, `transcripcion.md` / `palabras.tsv`, endurecimiento ante inyección de prompt y PII enmascarada en todo lo que lee Claude) | pytest -q -ra → 2332 passed, 3 skipped | 26/10 |

## Qué está escrito pero SIN verificar

| Archivo | Qué falta | Por qué |
|---|---|---|
| `piloto/*` | Correr en otra máquina | Son scripts de referencia con rutas y tiempos del piloto, no el producto |
| Test de symlink (`pytest -q -ra` → 3 skipped) | Correrlo con privilegio de administrador | Necesita privilegio de administrador en Windows; sin él se salta |

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
- Suite completa (≈6–10 min): `.venv/Scripts/python.exe -I -X utf8 -m pytest -q`

Cuando exista el plugin (spec 002):

```
/plugin marketplace add yedinrumba-eng/KORVEXCUT
/plugin install korvexcut@korvexcut
kcut doctor
```
