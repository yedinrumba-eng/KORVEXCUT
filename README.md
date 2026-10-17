# KORVEXCUT

Plugin de Claude Code para **editar video a partir de material crudo**: sueltas en una carpeta los videos, el audio y los recursos (logos, grabaciones de pantalla, b-roll). Claude los ve y los transcribe, te propone una estrategia de corte, arma el video con cortes, cambios de cámara, subtítulos, motion graphics, música y efectos, lo revisa solo y lo mejora contigo versión por versión.

> **Estado: pre-alpha. Todavía NO se puede instalar.**
> Lo que hay hoy es el **piloto 01**: un video real editado de punta a punta con scripts hechos a mano. Sirvió para probar el pipeline y medir cada paso. El plugin instalable (`kcut` + skill + agentes) se construye a partir de ahí; ver [Hoja de ruta](#hoja-de-ruta).

## Qué probó el piloto 01

Un reel de 9:16 y 49 s, a partir de dos iPhones grabando a la vez, una grabación de pantalla y un clip de cierre. Cifras medidas en un i7-1165G7 sin GPU dedicada:

| Pieza | Resultado medido |
|---|---|
| Sincronizar 2 cámaras por la onda de audio | offset 4.722 s, sin deriva; tras recortar, error −0.8 ms |
| Transcripción local (faster-whisper `medium`, CPU int8) | 0.73× tiempo real |
| Cortes con precisión de frame (todo en frames enteros, audio a 1600 muestras/frame) | diferencia A/V 0.0 ms en 1469 frames |
| HDR (HLG / Dolby Vision del iPhone) → SDR bt709 | ~5× tiempo real a 1440×2560 en CPU |
| Gráficos HTML deterministas (`seek(t)`) con fondo transparente | 1469 frames en 72–86 s |
| Mezcla final (voz + música con ducking + SFX sintetizados) | −14.4 LUFS, pico −1.4 dBFS |
| QA automático (re-transcribe el render y lo compara con el texto esperado) | detecta palabras tapadas y dudas de corte |

Detalle completo en [`docs/piloto/`](docs/piloto/README.md). Las lecciones pagadas están en [`PROGRESO.md`](PROGRESO.md).

## Cómo va a funcionar

1. `/korvexcut:nuevo <cliente> <nombre>` crea la carpeta del video. Sueltas el material en `crudo/`.
2. **Intake:** Claude pregunta si traes brief, guion o nada; plataforma; duración; tono; CTA; y quién sale en cámara (consentimiento).
3. `kcut ingest` hace inventario, sincroniza las cámaras, convierte el HDR y genera intermedios a fps constante.
4. `kcut transcribe` + `kcut pack`: transcripción por palabra, empaquetada por frases. Es lo que Claude "lee".
5. **Puerta 1:** Claude propone la estrategia (qué tomas, qué se bota, qué motion entra en qué palabra). Tú apruebas.
6. `kcut render` arma el video desde el EDL (en frames enteros) más la capa de gráficos y la mezcla.
7. `kcut qa` y un agente crítico revisan el render antes de enseñártelo.
8. **Puerta 2:** ves la v1, das notas en el chat ("0:12 corta antes") y se registran en `versiones.md`. Así hasta que apruebes.

## Hoja de ruta

| Fase | Qué entrega |
|---|---|
| **F1 — Núcleo** | `kcut doctor/ingest/transcribe/pack/view/render/qa`, EDL en frames, multicam por onda, plugin con intake + 2 puertas + versiones |
| F2 — Look | Plantillas de motion graphics, subtítulos de marca, reencuadre siguiendo la cara, b-roll, blur de privacidad, agente buscador de assets |
| F3 — Audio pro | Audio externo (grabadora/lav), limpieza de voz, música y ducking configurables |
| F4 — Ads sin voz | Montaje a BPM, puntuación de clips por visión |
| F5 — Entrega | Variantes 9:16 / 4:5 / 16:9, SRT, poster, preview liviano para WhatsApp |

## Requisitos (cuando haya versión instalable)

Windows 10/11 (también macOS/Linux), [Claude Code](https://claude.com/claude-code), ffmpeg ≥ 7 (build "full"), Python 3.12, `faster-whisper`, `numpy`, `scipy`, `opencv-python`, `Pillow`, `playwright` + Chromium. `kcut doctor` va a revisar todo y decir qué falta.

## Desarrollo

Para trabajar en el motor `kcut` desde este repo (sigue en pre-alpha: esto es para desarrollar, no para usarlo en videos reales):

```
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]" -c requirements.lock
.venv/Scripts/kcut doctor
```

- `requirements.lock` fija la versión exacta de cada dependencia: instala siempre con `-c requirements.lock`.
- `kcut doctor` revisa Python, ffmpeg/ffprobe, librerías, modelo de Whisper, Chromium, fuentes y disco, y dice qué falta.
- Corre el motor como `kcut ...` o como `.venv/Scripts/python.exe -I -X utf8 -m kcut ...`. **Nunca** `python -m kcut` a secas desde una carpeta de material crudo: sin `-I`, Python mete la carpeta actual en `sys.path` y un `cv2.py` plantado ahí se importaría y correría. El `-X utf8` va porque `-I` ignora `PYTHONUTF8`.

## Estructura

```
docs/research/   investigación de repos de referencia (video-use, HyperFrames, Remotion, catálogo de skills)
docs/piloto/     piloto 01: qué se hizo, cifras y ejemplos de estrategia y ficha de versiones
piloto/          scripts del piloto: referencia de implementación, amarrados a ese video, NO son el producto
```

## Licencia

[MIT](LICENSE). Las marcas que aparecen en los videos de ejemplo (Higgsfield, Claude, Ferrari…) son de sus dueños; este repo no incluye logos ni footage de terceros.
