# HANDOFF — KORVEXCUT

> Lo primero que se lee al retomar. Si esto está desactualizado, la sesión arranca ciega.

Actualizado: 16/10/2026 · Por: Claude (coordinador) · Slice cerrado: S0.3 (piloto 01)

---

## Dónde vamos

El piloto 01 está terminado (v4 en revisión de Yedin) y probó el pipeline completo en Windows. **El plugin instalable todavía no existe**: los scripts del piloto están amarrados a ese video.

**Fase actual:** F1 — Núcleo (spec 001 Motor + spec 002 Experiencia)
**Próximo paso:** spec `docs/specs/001-motor-kcut.md` (10 slices, plan aprobado en el Gate 1 el 16/10) → Gate 2 de Yedin → S1.1 `kcut doctor`.

---

## Qué está construido y verificado

| Pieza | Qué hace | Verificado con | Fecha |
|---|---|---|---|
| Piloto 01 v4 | Reel 9:16 de 49 s: multicam, cortes, subtítulos, gráficos, música, SFX | `qa.py` → 1469/1469 frames, A/V 0 ms, −14.4 LUFS, pico −1.4 dBFS | 15/10 |

## Qué está escrito pero SIN verificar

| Archivo | Qué falta | Por qué |
|---|---|---|
| `piloto/*` | Correr en otra máquina | Son scripts de referencia con rutas y tiempos del piloto, no el producto |

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

---

## Cómo levantarlo

No hay versión instalable todavía. Cuando exista F1:

```
/plugin marketplace add yedinrumba-eng/KORVEXCUT
/plugin install korvexcut@korvexcut
kcut doctor
```
