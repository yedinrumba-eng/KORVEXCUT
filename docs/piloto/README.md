# Piloto 01 — "Edita con Higgsfield" (14–15/10/2026)

Primer video editado de punta a punta para probar el pipeline de KORVEXCUT antes de escribir el producto. Lo editó Claude con scripts hechos a mano (`piloto/`), con dos puertas de aprobación y cuatro versiones.

## Material de entrada

| Fuente | Qué era | Trampa encontrada |
|---|---|---|
| Cámara A (frente) | iPhone, 4K vertical, HEVC 10-bit **HLG / Dolby Vision**, ~60 fps variable, 131 s | Tone-mapping obligatorio; persona pegada al borde del cuadro en la primera parte |
| Cámara B (abierta, de lado) | Otro iPhone, 4K vertical, 59.94 fps variable, audio a 48 kHz (A a 44.1) | Una mano tapa el lente en un momento |
| Grabación de pantalla | 1894×866, 30 fps, 22.5 s | Muy ancha para un 9:16; trae audio propio |
| Clip de cierre | 1080p, 24 fps, con canción comercial | La canción no se usa (riesgo de copyright) |

## Lo que se hizo y cómo se midió

1. **Sincronía multicam por correlación de la envolvente de audio:** pico 0.965 contra un ruido de 0.43 → offset 4.722 s, constante del segundo 10 al 100 (sin deriva). Tras recortar, −0.8 ms.
2. **Transcripción** con faster-whisper `medium` (CPU int8): 131 s en 96 s (0.73× tiempo real). Transcribir las **dos** cámaras sirve para desempatar las palabras dudosas.
3. **Silencios por energía** y no por timestamps de Whisper (ver lección 2 en `PROGRESO.md`). Pausas > 0.30 s recortadas a ~0.18 s, salvo las que tienen un gesto o le dan aire a un gráfico.
4. **EDL en frames enteros** → cada frame de salida se compone en Python desde un frame de origen calculado: diferencia A/V de 0.0 ms.
5. **Reencuadre** por plano según la posición de la cara, y cambio de zoom ≥15 % en cada corte del mismo ángulo para disimular el salto.
6. **Inserto de pantalla** con tarjeta animada y pasos ("PASO 1… RESULTADO") que entra en la palabra que lo pide ("enséñale").
7. **Capa de gráficos HTML** (`piloto/gfx/overlay.html`) con `seek(t)` determinista, capturada como PNG con alfa: gancho, títulos, mascota 3D rastreada sobre la palma (flujo óptico LK, verificado pintándolo sobre los frames), globo wireframe, holograma que nace entre las manos con el HOLA tecleado, subtítulos karaoke.
8. **Audio:** voz (pasa-altos, quita-ruido FFT, compresor) → música sintetizada sin licencia (120 BPM, Am–F–C–G) con ducking por sidechain (18 LU bajo la voz) → 56 SFX sintetizados → loudnorm de dos pasadas a −14 LUFS.
9. **QA:** frames, A/V, loudness, negros/congelados, re-transcripción del render contra el texto esperado y hoja de contacto.

## Tiempos de proceso (i7-1165G7, 16 GB, Iris Xe)

| Paso | Tiempo |
|---|---|
| Transcribir 131 s | 96 s |
| Tone-map de 68 s × 2 cámaras a 1440×2560 | ~11 min |
| Componer la base (1469 frames) | ~2 min |
| Capturar los gráficos (1469 PNG) | 72–86 s |
| Encode final (x264 `slow`, CRF 18) | ~1 min 45 s |

## Versiones

Ficha completa: [`ejemplo-versiones.md`](ejemplo-versiones.md). Estrategia aprobada en la Puerta 1: [`ejemplo-estrategia.md`](ejemplo-estrategia.md).

## Qué NO se pudo verificar

- **Cómo suena:** Claude no oye. El audio se verificó con mediciones y re-transcripción; el juicio final lo dio Yedin.
- **Muletillas en español:** casi no hubo en el crudo, así que no se midió si Whisper las conserva.
