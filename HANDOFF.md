# HANDOFF — KORVEXCUT

> Lo primero que se lee al retomar. Si esto está desactualizado, la sesión arranca ciega.

Actualizado: 16/10/2026 · Por: Claude (coordinador) · Slice cerrado: S0.3 (piloto 01)

---

## Dónde vamos

El piloto 01 está terminado (v4 en revisión de Yedin) y probó el pipeline completo en Windows. **El plugin instalable todavía no existe**: los scripts del piloto están amarrados a ese video.

**Fase actual:** F1 — Núcleo
**Próximo paso:** escribir el spec `docs/specs/001-nucleo.md` con la evidencia del piloto → Yedin lo aprueba → S1.1 `kcut doctor`.

**Decisiones abiertas de Yedin:**
- ¿El agente buscador de assets va en F1 o en F2?
- Piloto 01, primeros 14 s: ¿se dejan así o se mete más del ángulo 2?

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

---

## Cómo levantarlo

No hay versión instalable todavía. Cuando exista F1:

```
/plugin marketplace add yedinrumba-eng/KORVEXCUT
/plugin install korvexcut@korvexcut
kcut doctor
```
