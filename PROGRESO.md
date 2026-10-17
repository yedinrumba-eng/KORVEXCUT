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
- [ ] **S1.2** — `kcut new` + `kcut ingest` (inventario, HDR/VFR, sincronía multicam, proxies)
- [ ] **S1.3** — `kcut transcribe` + `kcut pack`
- [ ] **S1.4** — `kcut view` + `kcut frames`
- [ ] **S1.5** — EDL en frames + `kcut edl check` + `kcut render` base (cámaras, insertos, looks, mezzanines por tramo)
- [ ] **S1.6** — Capa de gráficos: motor HTML `seek(t)` + componentes base + subtítulos
- [ ] **S1.7** — Componentes de lucimiento (pasos, sticker, holograma, globo)
- [ ] **S1.8** — Audio: voz, SFX sintetizados, música, ducking, loudness
- [ ] **S1.9** — `kcut qa` + `kcut build` + `kcut catalog` + e2e sintético
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
- **Cuándo:** S1.2.

### 3. Intermedio a 1440×2560 deja poco margen para reencuadrar 🟡

Con zoom 1.55 se escala un poco hacia arriba.

- **Cura real:** intermedio a 1800×3200, o recortar desde el 4K solo los planos con zoom — ~2 h.
- **Cuándo:** S1.2.

### 4. Muletillas en español sin medir 🟡

En el piloto casi no hubo "eh/este", así que no se pudo medir si Whisper las conserva.

- **Cura real:** probar con un crudo lleno de muletillas; plan B: huecos de energía o ElevenLabs Scribe con tope de gasto — ~2 h.
- **Cuándo:** S1.3.

### 5. No hay detector de caras 🟡

OpenCV 5 ya no trae `CascadeClassifier`. En el piloto el encuadre por cara se decidió mirando los frames.

- **Cura real:** YuNet (`cv2.FaceDetectorYN`, modelo de ~230 KB, requiere aprobar la descarga) o MediaPipe — ~3 h.
- **Cuándo:** F2.

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

### 19. Hallazgos de la ronda 3 de S1.2 (1 MEDIO, 6 BAJO) 🟡

- **MEDIO:** con audio casi periódico (música en loop), un clip de menos de 13.4 s y mucho desfase, la sincronía puede aceptar un desfase equivocado sin avisar (tonos del fixture, 12 s +4 s → −2800). Con voz real no pasa.
- **BAJO:** `kcut new` dentro del `crudo/` de otro proyecto; `run_ingest` inventa un log cuando la CLI dijo "sin log"; `doctor` deja logs vacíos; `append_log` puede lanzar `OSError` y dejar un ffmpeg huérfano (seguridad); avisos de sync deducidos de `refine_corr` en vez del motivo; falta `logfile.py` en el árbol del spec.
- **No se cambia:** que un archivo que no se pudo hashear reciba id nuevo después. Conservar la entrada vieja dejaría un `qhash` viejo y E04 no saltaría (razón en 001.7 punto 8).
- **Mitigado hoy por:** hace falta una carpeta de logs saboteada o un fallo de disco para el huérfano; el caso periódico necesita clips cortos con música en loop.
- **Cura real:** parche 001.7 (criterios S1.2-40 a 47 y S1.3-11) + agente en worktree aislado — ~3 h. Decisión de Yedin 17/10/2026: arreglar el MEDIO.
- **Cuándo:** ahora, después de mergear la rama de deuda de S1.1.

### 20. La suite completa tarda ~10 min ⚪

- **Mitigado hoy por:** los revisores corren subconjuntos con `-k`.
- **Cura real:** marcador `slow` para todo test de más de 2 s y suite rápida `pytest -m "not slow"` (001.7 punto 9) — 1 h.
- **Cuándo:** ahora, con la deuda 19.

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
