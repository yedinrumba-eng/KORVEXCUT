# HANDOFF — KORVEXCUT

> Lo primero que se lee al retomar. Si esto está desactualizado, la sesión arranca ciega.

Actualizado: 16/10/2026 · Por: Claude (coordinador) · Slice cerrado: S1.1

---

## Dónde vamos

`kcut` 0.1.0 es instalable en modo desarrollo y `kcut doctor` está verificado (11/11 ok). **El plugin instalable todavía no existe** (spec 002); los scripts del piloto siguen amarrados a ese video.

**Fase actual:** F1 — Núcleo (spec 001 Motor + spec 002 Experiencia)
**Próximo paso:** S1.2 — `kcut new` + `kcut ingest` (spec 001.2; incluye los ítems S1.2 del parche 001.1: traceback de `InternalError` al log, `doctor` leyendo `transcribe.model`, `-loglevel error` / `-map_metadata -1`, lista blanca en `probe.py`) → verificación según los criterios S1.2 del spec.

---

## Qué está construido y verificado

| Pieza | Qué hace | Verificado con | Fecha |
|---|---|---|---|
| Piloto 01 v4 | Reel 9:16 de 49 s: multicam, cortes, subtítulos, gráficos, música, SFX | `qa.py` → 1469/1469 frames, A/V 0 ms, −14.4 LUFS, pico −1.4 dBFS | 15/10 |
| S1.1 | Paquete kcut + `kcut doctor` | `kcut doctor --json` → 11/11 ok; `pytest -q -ra` → 154 passed, 1 skipped | 16/10 |

## Qué está escrito pero SIN verificar

| Archivo | Qué falta | Por qué |
|---|---|---|
| `piloto/*` | Correr en otra máquina | Son scripts de referencia con rutas y tiempos del piloto, no el producto |
| Test de symlink (`pytest -q -ra` → 1 skipped) | Correrlo con privilegio de administrador | Necesita privilegio de administrador en Windows; sin él se salta |

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

---

## Cómo levantarlo

Hoy (desarrollo, kcut 0.1.0):

```
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]" -c requirements.lock
.venv/Scripts/python.exe -I -X utf8 -m kcut doctor
```

Cuando exista el plugin (spec 002):

```
/plugin marketplace add yedinrumba-eng/KORVEXCUT
/plugin install korvexcut@korvexcut
kcut doctor
```
