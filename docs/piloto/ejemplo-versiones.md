# Versiones — Piloto KORVEXCUT 01: "Edita con Higgsfield"

## v1 — 2026-10-14

**Entrega:** `salida/v1.mp4` · 1080×1920 · 30 fps · 48.4 s (1452 frames)

### Qué se hizo
- Multicam: A1 (cerca) + A2 (abierto), sincronizados por onda de audio (A2 = A1 − 4.722 s, sin deriva; tras recortar, error −0.8 ms). La voz sale siempre de A1.
- Cortes: se botaron 53 s de detrás de cámaras al inicio, el final, el "entonces" de arranque, el "eeeh" después de "con" y todas las pausas mayores de 0.30 s. Se dejaron a propósito 0.6 s tras "Claude" y 0.5 s tras "hola".
- HDR (HLG / Dolby Vision del iPhone) → SDR bt709 con tone-mapping hable.
- Reencuadre por plano centrado en la cara (de 53 a 82 s Yedin estaba corrido a la izquierda del encuadre original).
- Gancho Ferrari + "ESTO LO HIZO LA IA" · título HIGGSFIELD · cutaway Ferrari en "Ferrari" · inserto de pantalla en "enséñale" (PASO 1 → 2 → 3 → RESULTADO) · "EDITADO 100% CON IA" · globo wireframe en "mundo" · HOLA tecleado letra por letra en "hola" · POR / SÍ / SOLA · cierre MAÑANA PARTE 2.
- Subtítulos karaoke (palabra activa en lima #E5FF1F, sacado del botón Generate de Higgsfield), corregidos: Higgsfield, Claude, IA, "en el video de hoy", "ven", "por su sintonía".
- Audio: voz con pasa-altos 80 Hz, reducción de ruido FFT, compresión 3:1; 20 SFX sintetizados (sin licencias); mezcla a −14 LUFS en dos pasadas; sin música (Yedin la pone en IG).

### QA v1 (`qa/v1/report.json`)
- 1452/1452 frames · audio y video 48.400 s (diferencia 0.0 ms) · −14.2 LUFS · pico −1.5 dBFS · sin frames negros ni congelados · 52.5 MB.
- Re-transcripción del render: las diferencias son palabras tapadas a propósito por gráficos grandes, más 3 dudas de oído:
  - 9.2 s: ¿"que tú quieras **hacer**, en el video de hoy"? (al subtítulo le puede faltar "hacer")
  - 34.0 s: ¿se oye completo "**aquí** te pongo"? (la re-transcripción oye "y te pongo")
  - 44.7 s: ¿"gracias por **su** sintonía" o "gracias por sintonía"? (2 de 3 transcripciones: sin "su")
- 0–14 s: A1 tiene a Yedin pegado al borde izquierdo desde la grabación original; recortar no lo arregla (decisión de Yedin: dejarlo o meter más A2).

### Pendiente conocido en v1
- **Logo de Claude:** falta el archivo oficial. El rastreo de la palma ya está hecho (tramo 92.0–93.3 s verificado a ojo); entra en v2 apenas el archivo esté en `videoi/`.

### Notas de Yedin para v2
- Dudas de oído resueltas: sí dijo "que tú quieres hacer"; "aquí te pongo" se oye completo; "por su sintonía" está bien.
- El inserto de Higgsfield necesita sonido: dejó de hablar y no puede quedar en silencio.
- Logo: la mascota pixelada de Claude Code (la mandó por el chat).
- El HOLA va con la cámara del frente, en un tablero tecnológico/holográfico que sale cuando abre las manos.
- Subtítulos: azul en vez de amarillo.

## v2 — 2026-10-15

**Entrega:** `salida/v2.mp4` · 1080×1920 · 30 fps · 48.97 s (1469 frames) · EDL `edit/edl-v2.json`

### Qué cambió
- Subtítulo "QUE TÚ QUIERES | HACER EN EL VIDEO | DE HOY". Se recuperó el "QUE", que tapaba el título HIGGSFIELD.
- Subtítulos con la palabra activa en **azul #2FA8FF**. Los títulos grandes siguen en lima.
- Inserto Higgsfield con beat sintetizado a 120 BPM (kick, hi-hat, pad), clicks por paso, tecleo en "Escribe tu prompt", riser y brillo en RESULTADO. Suena a −16.0 LUFS, 3.5 LU bajo la voz.
- Mascota de Claude Code (fondo quitado, ojos rellenos) materializándose a saltos sobre la palma rastreada, con haz de luz. Arpegio 8-bit. Vuela al globo en "mundo".
- Tramo "aquí te pongo… la palabra hola" ahora continuo (101.24–104.02) y todo en A1 (frente): se recuperó el gesto de abrir las manos (101.9 s) que en v1 se había cortado con la pausa.
- Tablero holográfico cian: nace entre las manos con parpadeo y rayos de luz, se expande al pecho, "LA PALABRA" + HOLA tecleado adentro (A en lima), se colapsa al final. Power-up + whoosh.
- Para evitar un salto sin disimular después del holograma: "y todo eso" pasa a A2, "y únicamente" va en A1 1.2×, "por sí sola" en A1 1.45×.

### QA v2 (`qa/v2/report.json`)
- 1469/1469 frames · A/V 48.966 s (diferencia 0 ms) · −14.3 LUFS · pico −1.4 dBFS · sin negros ni congelados · 53.5 MB.
- Re-transcripción: solo palabras tapadas a propósito por gráficos y variaciones de Whisper ya confirmadas de oído por Yedin.

### Pendiente
- 0–14 s: A1 con Yedin pegado al borde izquierdo desde la grabación original (falta su decisión: dejar o meter más A2).

## v3 — 2026-10-15

**Nota de Yedin:** usar la mascota 3D (mejor para animar) y darle vida con motion graphics.

- Mascota 3D de Claude Code (webp con alfa, en `recursos/claude-code-mascota-3d-original.webp`).
- Cae sobre la palma con squash & stretch, idle (flota, se balancea en 3D, parpadea 2 veces), destellos, brillo naranja en la palma. Se agacha, salta y vuela en arco con giro hasta el globo.
- SFX: "bop" grave al aterrizar y whoosh al saltar.

## v4 — 2026-10-15

**Nota de Yedin:** "una musiquita debajo de mi voz bajita y uno que otro efecto".
**Cambio de acuerdo:** en la Puerta 1 era "sin música, la pongo en IG". Yedin lo cambió aquí.

**Entrega:** `salida/v4.mp4` · 48.97 s · 1469 frames · 53.6 MB

- Música sintetizada sin licencia (`.kcut/build2/music.wav`): 120 BPM, Am–F–C–G, pad + bajo + arpegio + batería suave. La batería se calla en el inserto de Higgsfield, donde entra el beat del SFX alineado al mismo compás (drop).
- Ducking por sidechain: la música queda a −32.6 LUFS mientras habla (18 LU bajo la voz) y sube a −24 en pausas y en el gancho.
- Efectos extra: whooshes suaves en cada cambio A1↔A2 y riser antes de "EDITADO 100% CON IA".
- QA (`qa/v4/report.json`): 1469/1469 frames · A/V 0 ms · −14.4 LUFS · pico −1.4 dBFS · sin negros ni congelados. La re-transcripción con música (0.845) es igual que sin música (0.855): la música no tapa la voz.
