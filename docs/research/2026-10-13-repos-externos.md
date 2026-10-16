# Investigación externa: edición de video con IA para un plugin de Claude Code (Windows)

Fecha: 2026-10-13. Fuentes: `gh api` sobre cada repo (README, SKILL.md, código fuente, issues, commits, releases).
Todo lo marcado **[no verificado]** no lo comprobé ni corriendo código ni leyendo fuente.
Nada de esto se ejecutó en la máquina de Yedin: es lectura de código y docs, no prueba en vivo (R1).

---

## 1. browser-use/video-use (PRIORIDAD MÁXIMA)

**Madurez:** ★28.8k, 3.4k forks, creado 2026-04-12, último push 2026-10-08. 148 issues abiertos, 100+ PRs abiertos
(sin mergear: señal de mantenimiento lento). Licencia **MIT**. Python. Versión 0.1.0. Hay un "cloud video-use" en lista de espera.

### Qué es
Un **skill de Claude Code** (SKILL.md + `helpers/*.py`), no una app. Lo clonas en `~/.claude/skills/video-use`, abres
Claude en la carpeta de los crudos, dices "edita esto en un video de lanzamiento" y sale `edit/final.mp4`.

### Pipeline real (leído del código)
1. **Inventario:** `ffprobe` a cada fuente.
2. **Transcripción** (`transcribe.py`, `transcribe_batch.py` con 4 workers): ffmpeg extrae WAV mono 16 kHz →
   POST a **ElevenLabs Scribe** (`model_id=scribe_v1`, `diarize=true`, `tag_audio_events=true`,
   `timestamps_granularity=word`). Guarda el JSON crudo en `edit/transcripts/<stem>.json` (cache inmutable: nunca re-transcribe).
   Detalles finos: elige pista de audio (`--audio-track`, para OBS), y **se niega a subir audio en silencio**
   (pico < -60 dBFS) para no pagar por nada.
3. **Pack** (`pack_transcripts.py`): agrupa palabras en frases cortando en silencio ≥0.5 s o cambio de hablante →
   `takes_packed.md` (~12 KB por una tanda de tomas). Formato: `[002.52-005.36] S0 texto...`. **Esta es la vista
   principal del LLM.** El LLM no ve el video: lo lee.
4. **Visión bajo demanda** (`timeline_view.py <video> <start> <end>`): PNG compuesto = tira de N fotogramas (10 por
   defecto, 320 px) + envolvente RMS de audio + etiquetas de palabras + bandas sombreadas de silencios ≥400 ms + regla
   de tiempo. Solo en puntos de decisión (pausas ambiguas, comparar tomas), no como escaneo.
5. **Razonamiento → EDL:** un sub-agente "editor" lee `takes_packed.md` con un brief estructurado (arquetipos:
   HOOK→PROBLEM→SOLUTION…, verbal slips a evitar, runtime objetivo) y devuelve JSON:
   `{"sources":{...}, "ranges":[{source,start,end,beat,quote,reason}], "grade", "overlays":[{file,start_in_output,duration}], "subtitles"}`.
   Reglas: cortes en límites de palabra, padding 30–200 ms (Scribe deriva 50–100 ms), preferir silencios ≥400 ms.
6. **Render** (`render.py`): extracción por segmento (`-ss` antes de `-i`, libx264, grade + tone-map HDR→Rec.709 +
   fades de audio de 30 ms horneados) → concat demuxer `-c copy` → un solo filtergraph final con overlays
   desplazados por PTS (`setpts=PTS-STARTPTS+T/TB`) y **subtítulos al final** → loudnorm de dos pasadas
   (-14 LUFS / -1 dBTP / LRA 11). Modos `--draft` (720p ultrafast), `--preview`, final. Respeta fps de la fuente,
   rotación/portrait, `--fps` forzado.
7. **Subtítulos:** `--build-subtitles` arma `master.srt` en tiempo de salida
   (`word.start - seg_start + seg_offset`), chunks de 2 palabras (crece a 3 si duraría <0.35 s), MAYÚSCULAS,
   `MarginV=90` (zona segura de Reels/TikTok).
8. **Color** (`grade.py`): presets (`subtle`, `neutral_punch`, `warm_cinematic`) o `auto` = `signalstats` sobre
   frames muestreados → corrección `eq=` acotada a ±8%. Filtro crudo de ffmpeg permitido.
9. **Animaciones:** cada overlay es un sub-agente en paralelo dentro de `edit/animations/slot_<id>/`, motor a
   elección: HyperFrames, Remotion, Manim (skill vendorizado) o PIL→PNG→ffmpeg.
10. **Auto-evaluación antes de enseñar nada:** `timeline_view` sobre el **render** en cada corte (±1.5 s),
    primeros/últimos 2 s, `ffprobe` de duración, `ebur128` por sección. Máximo 3 pasadas. Para piezas publicables,
    un sub-agente **crítico** que "roastea" con timecodes.
11. **Memoria:** `edit/project.md` con una sección por sesión (estrategia, decisiones, pendientes).

### Técnicas que vale la pena robar
- **Texto primero, imágenes a demanda:** transcripción a nivel palabra empaquetada en frases (12 KB) + PNG
  filmstrip/waveform solo donde hay duda. "30.000 frames × 1.500 tokens = 45M tokens de ruido" vs 12 KB.
- **EDL JSON con `reason` y `quote` por rango:** auditable, re-renderizable sin re-transcribir.
- **12 reglas duras** de corrección (subtítulos al final, fades 30 ms, PTS shift, offsets de SRT, nunca cortar dentro de
  palabra, cache de transcripciones, confirmar estrategia antes de cortar, outputs solo en `edit/`).
- **Gate de estrategia:** el agente propone 4–8 frases y espera OK antes de tocar el corte.
- **Auto-QA sobre el render, no sobre la fuente**, y medir audio en vez de "creer que suena bien".
- Rechazar audio en silencio antes de pagar transcripción.

### Dependencias
Python ≥3.10 (`requests librosa matplotlib pillow numpy`), ffmpeg/ffprobe (con libass para subtítulos),
**API key de ElevenLabs (pago por uso)**, opcional yt-dlp, Node 22+ si usas HyperFrames/Remotion, Manim opcional.
El SKILL.md desaconseja explícitamente Whisper local ("lento y normaliza fillers").

### Windows — funciona con parches
Bugs abiertos y confirmados en issues:
- **#125** — los helpers imprimen `→ — …`; con stdout redirigido en Windows (cp1252) `print` lanza
  `UnicodeEncodeError` y `render.py` muere en la primera línea. **Mitigación: `PYTHONUTF8=1`** (o `PYTHONIOENCODING=utf-8`).
- **#193** — `read_text()/write_text()` y `subprocess(text=True)` sin `encoding="utf-8"`; el path del SRT se mete
  absoluto (`C\:...`) dentro del filtergraph `subtitles='...'` y falla en Windows. Fix propuesto: correr ffmpeg con
  `cwd=edit_dir` y pasar `master.srt` relativo. Para español esto importa: `master.srt` se escribe con la codificación
  del sistema → riesgo de mojibake en Ñ/acentos al leerlo libass como UTF-8 **[deducido del código, no probado]**.
- `grade.py` mete `metadata=print:file=C:\...` en un `-vf` → mismo problema de `:` en filtergraph **[deducido, no probado]**.
- `timeline_view.py` solo busca fuentes de macOS/Linux → en Windows cae a la fuente bitmap por defecto (fea, pequeña).
- `install.md` usa `ln -sfn` (symlink): en Windows requiere modo desarrollador; mejor clonar directo en `~/.claude/skills/`.

### Licencia
MIT, sin restricciones comerciales.

### Debilidades / huecos
- **Click de audio en cada corte (#162):** cada segmento se codifica a AAC por separado y el concat `-c copy`
  desalinea el priming de AAC (~100 ms después del empalme). Los fades de 30 ms no lo tapan. Fix: re-codificar solo el
  audio en el concat, o (mejor) intermedios PCM como hace HyperFrames.
- Subtítulos con libass rotos en builds de ffmpeg sin `--enable-libass` (#118) y "tofu" para scripts no latinos.
- Depende 100% de un servicio de pago (Scribe) para el corazón del pipeline; sin modo offline.
- Visual pobre para material sin voz (b-roll, montajes): todo se guía por audio; el filmstrip es a demanda.
- Sin export a NLE (FCPXML/OTIO/EDL CMX): el EDL es JSON propio.
- Sin sincronizar audio externo (grabadora/lav) contra cámara.
- Colisión de transcripciones para videos con el mismo stem en carpetas distintas (#206); loudnorm revienta con
  edición en silencio digital (#188).
- `timeline_view --edl` (vista de proyecto completo) "not implemented".

---

## 2. heygen-com/hyperframes

**Madurez:** ★62.0k, 5.5k forks, creado 2026-03-10, push 2026-10-13, **release diario** (v0.8.151 el 2026-10-13 —
pre-1.0, mucho churn). 243 issues abiertos. Licencia **Apache-2.0**. TypeScript monorepo (cli, core, engine,
producer, studio, player, shader-transitions, aws-lambda).

### Qué es
Framework "escribe HTML, renderiza video". Una composición es un `index.html` con atributos `data-*` de tiempo
(`data-start`, `data-duration`, `data-track-index`, `data-media-start`), animación "seekable" (GSAP timeline
pausado registrado en `window.__timelines[id]`, o CSS/Lottie/Three/WAAPI/Anime.js). El renderer abre Chrome
headless, hace seek frame a frame y codifica con FFmpeg → determinista (mismo input, mismos frames).

### Cómo se autora / renderiza
- `npx hyperframes init` → `preview` (Studio con live reload) → `lint`/`check` (lint + runtime + layout + motion +
  contraste) → `snapshot --at <t>` (PNG de frames) → `render` (MP4; `--format webm` con alfa) → `cloud render` /
  `lambda` opcionales.
- Edición "tipo NLE" en HTML: varios `<video>` del mismo archivo con `data-media-start` distinto = cortes, trims,
  splices, J/L cuts (con `<audio>` aparte), freeze, crossfade (`creator-editing-recipes.md`). `hyperframes timeline --json`
  lista pistas/clips.
- Plugin de Claude Code: `claude plugin marketplace add heygen-com/hyperframes` / `claude plugin install hyperframes@hyperframes`.
  21 skills. Los relevantes para crudos:
  - **`/talking-head-recut`**: overlays diseñados (lower-thirds, callouts, quotes, PiP) sincronizados al transcript.
    **El clip se reproduce intacto: NO corta.**
  - **`/embedded-captions`**: subtítulos sobre talking-head con **matting local del sujeto** para que palabras
    "hero" queden detrás de la persona; catálogo de 35 estilos; gates de timing/oclusión/overflow. Tampoco edita el clip.
  - **`/media-use`**: "media OS" — `transcript-cut.mjs` (el único cortador real), transcripción, reframe, grade,
    background removal, ducking, BGM/SFX (BGM/SFX del catálogo **requiere el CLI de HeyGen**).
  - **`/hyperframes-audio`**: mezcla dentro de la composición (carve de voz sobre música, EQ/compresor/limitador,
    automatización, buses).

### Técnicas que vale la pena robar
- **`transcript-cut.mjs` como "compilador":** transcript de palabras + decisiones (`--remove "a-b"`,
  `--remove-words`, `--remove-fillers "um,uh"`, `--cut-silence 0.8` con padding 150 ms, `--keep`) → segmentos
  guardados; `--plan` imprime el JSON antes de codificar.
- **Intermedios con audio PCM en `.mov`** → el audio se codifica a AAC **una sola vez** en el concat. Esto mata el
  bug de priming AAC que tiene video-use (#162). También: `.mov` no `.mkv` (Matroska redondea timestamps a ms y
  saca frames de la rejilla), `-fps_mode cfr`, keyframe forzado cada segundo, `seekTime` con 6 decimales (3 decimales
  hace caer un frame en el empalme), fades de 30 ms escalados si el segmento es corto, rename atómico del output,
  y aviso de drift si usas `--copy` (corte a keyframe).
- **Re-codificar crudos con GOP denso** (`-g fps -keyint_min fps`) antes de meterlos en un renderer de navegador:
  GOP disperso = frame congelado al hacer seek.
- **Clamp de la última palabra de Whisper a la duración real** (si no, cola negra).
- `lint` que atrapa bugs silenciosos (audio sin `id` = render mudo; fuente CSS sin `@font-face` local; etc.).
- Decision gate del captioner: rechazar clips con subtítulos quemados, sin cara, o casi mudos (Whisper alucina
  "Thank you." sobre silencio).
- QA por contact sheet: `ffmpeg -vf "fps=1,scale=160:-1,tile=10x5"`.

### Dependencias
Node.js **22+**, FFmpeg, Chrome headless (lo baja), opcional Bun para desarrollo. Transcripción local:
**whisper.cpp** (default `small.en`; se cambia a multilingüe si pasas idioma ≠ en) o **Parakeet TDT 0.6B v3 vía
sherpa-onnx** (`npx hyperframes models install parakeet`, ~640 MB, 25 idiomas europeos incluido español). Sin API key
para lo básico. Matting/captions bajan modelos al primer uso. BGM/SFX/TTS/avatar: CLI de HeyGen (OAuth con
cuota gratis o API key de pago).

### Windows
- Hay un **workflow de CI que renderiza en `windows-latest`** (sin Docker ni WSL) y tests en Windows → soporte real.
- whisper.cpp en Windows: no hay binario precompilado; el CLI intenta clonar + `cmake` (requiere compilador C) y busca
  `build/bin/whisper-cli` **sin `.exe`** → probablemente no lo encuentra tras compilar con MSVC **[deducido del código,
  no probado]**. Salida práctica: `HYPERFRAMES_WHISPER_PATH=<whisper-cli.exe precompilado>` o usar Parakeet.
- Issues abiertos de Windows: **#4060** el gate de espacio en disco estima ~16 GB por ~1 min de 1080p y rechaza renders
  normales; **#4845** Smart App Control de Windows 11 bloquea la DLL sin firmar de `sharp` (snapshot); **#4058**
  spawn EBUSY sin reintento; **#3476** consolas que parpadean.
- Los skills usan scripts bash (`prepare.sh`) → necesitan Git Bash.
- No hay app de escritorio para Windows (Mac/Linux sí).

### Licencia
Apache-2.0, "sin cuotas por render ni umbrales de uso comercial". **Telemetría activada por defecto** en el CLI
(se apaga con `HYPERFRAMES_NO_TELEMETRY=1`); hasta `transcript-cut.mjs` llama a `track()`.

### Debilidades
- No es un editor de crudos: corta poco (un script), su fuerte son overlays/motion/captions sobre video que no toca.
- Render por captura de navegador frame a frame: lento para material largo. En el test end-to-end del catálogo
  awesome, el flujo hyperframes fue el más lento (23.5 min para un brief de 15 s — tiempo total del agente, no solo render).
- Superficie enorme y cambiante (21 skills, releases diarios) → fijar versión.
- Partes "premium" empujan al ecosistema HeyGen.

---

## 3. remotion-dev/remotion (foco: footage real)

**Madurez:** ★63.7k, desde 2020, push 2026-10-13, v4.0.535 (2026-10-12), 179 issues abiertos. Muy maduro.
Remotion 5.0 en preparación (PR #3750 abierto).

### Lo relevante para editar crudos
- **`<Video>` de `@remotion/media`** (recomendado ahora, basado en Mediabunny) y **`<OffthreadVideo>`** (extrae el
  frame exacto con FFmpeg fuera del navegador y lo pinta como `<Img>` → frame-accurate). Cortes vía
  `trimBefore` + `durationInFrames` (trimAfter/startFrom/endAt deprecados) dentro de `<Sequence>`/`<Series>`.
- **`@remotion/captions`:** tipo `Caption {text,startMs,endMs,timestampMs,confidence}`, `createTikTokStyleCaptions()`
  (`combineTokensWithinMilliseconds` controla palabra-a-palabra vs páginas; exige el espacio **antes** de cada
  palabra en `text`), `parseSrt`/`serializeSrt`.
- **Transcripción, 5 caminos con conversor a `Caption`:** `@remotion/install-whisper-cpp` (Node, local; **en Windows
  baja el binario precompilado `whisper-bin-x64.zip`** — soporte Windows explícito en el código), `@remotion/whisper-webgpu`
  (local en GPU; es el que recomienda el skill oficial `remotion-captions`), `@remotion/whisper-web` (WASM, lento),
  `@remotion/openai-whisper` (API), **`@remotion/elevenlabs`** (`elevenLabsTranscriptToCaptions()` — convierte justo
  la salida de Scribe que usa video-use).
- **`@remotion/video-matting`** (separar sujeto/fondo, WebGPU, requiere GPU).
- **Render:** `npx remotion render <id> out.mp4 --props=...`, `renderMedia()` en Node, Lambda/Cloud Run. Compositor
  nativo para `win32-x64-msvc` → Windows soportado.
- Plantillas: `template-tiktok` (`node sub.mjs` subtitula todo `public/` con whisper.cpp), Remotion Recorder
  (talking-head, ★54, repo sin licencia SPDX).
- **Plugin oficial de Claude Code + skills** (`remotion-best-practices`, `remotion-captions`, `remotion-render`, …).
  **Yedin ya los tiene instalados** en esta máquina (aparecen en la lista de skills).

### Técnicas que vale la pena robar
- El tipo `Caption` como formato canónico de palabras con conversores desde cualquier ASR.
- `createTikTokStyleCaptions` para paginar.
- `OffthreadVideo`: frame exacto vía FFmpeg en vez de confiar en `<video>` del navegador.
- Instalador de whisper.cpp que sí resuelve Windows (binario precompilado).

### Dependencias
Node, React, Chrome Headless Shell (lo baja), FFmpeg embebido en el compositor. GPU opcional (WebGPU para
whisper-webgpu/matting).

### Licencia (ojo)
**Source-available "Remotion License", no OSI.** Gratis para: individuos, empresas con **≤3 personas** (aunque estén
incorporadas), sin fines de lucro, evaluación. Gratis incluye uso comercial, automatizaciones y SaaS. Por encima de
3 personas → **Company License** (remotion.pro; precio no verificado — la página de pricing se renderiza con un
componente). Prohibido vender/relicenciar un derivado de Remotion. **En 5.0 los contratistas cuentan para el tamaño
del equipo** y la licencia de empresa queda atada a nuevos T&C. Para Yedin solo: gratis hoy; si Korvex crece a >3
personas (incluyendo contratistas en 5.0), toca pagar.

### Debilidades
- Render frame a frame en Chrome: más lento que ffmpeg puro para piezas largas.
- Pensado para componer, no para decidir cortes: no trae corte por transcript ni silence-removal.
- Licencia con umbral (riesgo de negocio para Korvex a futuro).

---

## 4. zhuyansen/awesome-claude-video-skills (catálogo)

**Madurez:** ★579, creado 2026-09-27 (2 semanas), push 2026-10-12. Licencia NOASSERTION. README dice 283 repos
(la descripción dice 180 — inconsistente). Clasificación y "security grade" hechos **por un modelo leyendo READMEs**,
no a mano; sirve de embudo a agentskillshub.top. Test end-to-end del 2026-10-11: 16 skills hicieron un promo de 15 s;
todos pasaron 4 checks básicos, y **Claude Code sin skill también** (4.4 min). Conclusión del propio catálogo: un
skill se gana el puesto por un look, un workflow o **footage que editar**.
**Hueco notable: video-use no aparece en el catálogo** (grep de "browser-use" = 0).

### Los más relevantes para editar crudos

| Necesidad | Repo | Por qué es bueno (1 línea) | ★ / licencia / Windows |
|---|---|---|---|
| Corte talking-head end-to-end | [hassancs91/claude-youtube-editor](https://github.com/hassancs91/claude-youtube-editor) | Claude escribe `cuts.json` leyendo el transcript; **re-transcribe el render y lo diff-ea contra los tokens esperados** (detecta "ghost speech" y palabras cortadas), keyterms para sesgar el ASR, editor web local para auditoría humana, gate A/V de duración, RNNoise local, thumbnails, upload | ★330, MIT; instrucciones Windows (venv/Scripts); AssemblyAI + ElevenLabs/Gemini opcionales |
| Silencios / fillers | [louisedesadeleer/cut-video](https://github.com/louisedesadeleer/cut-video) | Whisper solo para texto + **Montreal Forced Aligner** (~10–20 ms) para los tiempos, re-transcripción en ventanas aisladas para atrapar retakes que Whisper colapsa, preserva risas/pausas cómicas por amplitud, `trim+concat` (no `select`), presets de tono | ★108, MIT; macOS (quitar flags videotoolbox para Windows); solo inglés en MFA por defecto |
| Silencios (herramienta) | [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) | CLI maduro de silence-cut por umbral de audio (lo recomienda HyperFrames); no es skill | ★5.5k, Unlicense, multiplataforma |
| Mejor toma + estilo | [kurbaitaev/ghost-editor](https://github.com/kurbaitaev/ghost-editor) | Elige la mejor toma de cada frase, captions que evitan cara y botones de la app, **clona el estilo de un reel de referencia** (Gemini lo mira), auto-chequeo | ★69, MIT; Mac (Linux "debería") |
| Long→short + reframe 9:16 | [AgriciDaniel/claude-shorts](https://github.com/AgriciDaniel/claude-shorts) | Scoring de segmentos en 5 dimensiones, snap a palabra/frase/silencio, **crop con seguimiento de cara (MediaPipe)** y de cursor para screencasts, captions Remotion | ★222, MIT; **Windows solo vía WSL2**; NVIDIA recomendada |
| Montaje sin voz (b-roll, viajes) | [Fagan1024/smart-video-editor](https://github.com/Fagan1024/smart-video-editor) | Frames con timestamp en el nombre (`clip1__t3.5.jpg`) → modelo de visión puntúa usabilidad 1–5 (blur, sobreexpuesto, repetido) → corta y reordena por narrativa; 9 presets de color | ★9, MIT; madurez baja |
| Vlog desde carpeta de clips | [znyupup/ai-video-editing-skill](https://github.com/znyupup/ai-video-editing-skill) | Whisper + API de visión (GLM-4.6V-Flash gratis) por clip, preview en navegador antes de render, 24 lecciones de errores | ★154, MIT; docs en chino; último push 2026-04 |
| Corte a ritmo de música | [ZiadAbdelkarim/beat-synced-edit](https://github.com/ZiadAbdelkarim/beat-synced-edit) | Determinista: librosa (beats/energía) + PySceneDetect (clips por movimiento/brillo) → matcher EDL → ffmpeg; `vertical_style.py` para 9:16 | ★13, MIT |
| B-roll/overlays desde SRT | [erduo1998-cell/erduo-broll-loop-engineering](https://github.com/erduo1998-cell/erduo-broll-loop-engineering) | SRT manda; rutea por plano a HyperFrames o Remotion; 152 "shot cards" | ★211, MIT; docs en chino |
| Auto-QA viendo el video | [YeJe-cpu/SeeCut](https://github.com/YeJe-cpu/SeeCut) | Gemini mira el video entero (no frames), **juez por comparación pareada** (A vs B) porque las notas absolutas no son fiables; máx 3 versiones; exporta a 剪映 (CapCut CN) | ★278, NOASSERTION; solo macOS probado |
| Criterio de editor (color, audio, thumbnails) | [kmilo93sd/agent-video-editor](https://github.com/kmilo93sd/agent-video-editor) | Reglas con números y fuentes (pacing por tipo, J/L cuts, niveles, color, thumbnails), librería CC0 de SFX/música, plantillas que fallan si rompes una regla | ★6, MIT; madurez muy baja |
| Editor con timeline + MCP | [0xsline/OpenChatCut](https://github.com/0xsline/OpenChatCut) | Timeline multipista real + transcript editing + **export FCPXML**, agentes vía MCP, builds Windows | ★2.3k, **AGPL-3.0** |
| Sistema completo | [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) | 12 pipelines (Talking Head, Clip Factory, Hybrid, Podcast…), Remotion+HyperFrames, instrucciones PowerShell | ★67.7k, **AGPL-3.0** (no copiar código a un plugin cerrado) |

Descartables para uso comercial: [AKMessi/vex](https://github.com/AKMessi/vex) es **source-available no comercial**
aunque técnicamente es interesante (auto color grade por planos, zooms guiados por subtítulos).

---

## BEST-OF SYNTHESIS — pipeline más fuerte para Claude Code en Windows

**Columna vertebral: el patrón de video-use** (es el único de los cuatro que de verdad decide cortes sobre crudos).
Lo que se combina:

1. **Ingesta / proxies** (HyperFrames + cut-video): `ffprobe` a todo; si es HEVC/4K/HDR o GOP disperso, proxy 1080p
   H.264 con `-g fps -keyint_min fps`; tone-map HDR→709 (video-use). En Windows: ffmpeg build "full" de gyan.dev
   (verificar `ffmpeg -filters | findstr subtitles`).
2. **Transcripción** (video-use + Remotion + claude-youtube-editor): ElevenLabs Scribe verbatim (fillers + eventos +
   diarización) como opción de calidad; **fallback local** whisper.cpp vía `@remotion/install-whisper-cpp` (único con
   binario Windows resuelto) o Parakeet (español, sherpa-onnx). Keyterms para nombres propios (claude-youtube-editor).
   Rechazar pistas en silencio antes de pagar (video-use). Normalizar todo al tipo `Caption` de Remotion.
3. **Vista del LLM** (video-use): `takes_packed.md` + `timeline_view` PNG a demanda; para material sin voz, añadir la
   capa de visión de smart-video-editor (frames con timestamp en el nombre → puntaje de usabilidad) — Claude lee PNG
   nativamente, no hace falta API externa.
4. **Decisión → EDL JSON** (video-use) con `reason`/`quote`, gate de estrategia antes de cortar, sub-agente editor.
5. **Render de corte** con la técnica de **HyperFrames `transcript-cut`**: intermedios `.mov` con audio PCM, CFR,
   seek de 6 decimales, fades 30 ms solo en empalmes internos, AAC una sola vez → elimina el click #162 de video-use.
   Grade por segmento (video-use) usando filtros sin paths absolutos.
6. **Overlays / captions animados**: Remotion (Yedin ya tiene los skills; `OffthreadVideo`, `createTikTokStyleCaptions`)
   o HyperFrames para motion HTML/GSAP con alfa — **solo como capas** renderizadas aparte y compuestas con ffmpeg, nunca
   pasando el video largo completo por Chrome. Subtítulos LAST (video-use).
7. **Reframe 9:16**: crop con seguimiento de cara MediaPipe (claude-shorts), suavizado.
8. **Audio**: denoise local (RNNoise/arnndn, como claude-youtube-editor), ducking de música bajo voz, loudnorm de dos
   pasadas a -14 LUFS / -1 dBTP (video-use) y medición por sección con `ebur128`.
9. **QA antes de enseñar**: `timeline_view` en cada corte del render (video-use) + **re-transcribir el render y diff contra
   los tokens esperados** (claude-youtube-editor) + gate de duración A/V + juez pareado A vs B entre versiones (SeeCut)
   + crítico en contexto limpio. Máximo 3 vueltas.
10. **Memoria e iteración**: `edit/project.md` por sesión (video-use); EDL versionado para que "cambia X" sea editar
    JSON y re-render, no re-transcribir.
11. **Windows-first**: `PYTHONUTF8=1`, `encoding="utf-8"` en todo I/O, ffmpeg con `cwd=edit_dir` y SRT relativo, lista de
    argumentos (nunca string por shell), fuentes de Windows (Segoe/Arial o self-hosted) explícitas, nada de symlinks.

### Lo que ninguno resuelve bien
- **Sincronizar audio externo** (grabadora/lav/segundo celular) con la cámara por correlación cruzada — ninguno de los
  cuatro lo hace (video-use solo elige pista). Es justo el caso "dejo footage + audio en una carpeta".
- **Multicámara** (cambiar de ángulo por hablante) — no encontrado en los cuatro.
- **Español verbatim con fillers ("eh", "este", "o sea")**: Scribe los conserva; Whisper los normaliza; Parakeet
  **[no verificado]**. Ningún repo tiene listas de muletillas en español ni prueba con acento dominicano.
- **Export a NLE editable** (FCPXML/OTIO/EDL CMX) para retoque humano: ninguno de los cuatro (solo OpenChatCut en el
  catálogo, AGPL).
- **Entender b-roll sin voz** a escala: video-use es audio-first; las alternativas dependen de muestreo de frames.
- **Escuchar de verdad**: todos miden (LUFS, waveform) pero nadie "oye" — gusto musical y mezcla quedan al humano.
- **Color serio** (LOG→Rec.709 con LUT de cámara, consistencia de piel entre clips): solo `eq`/presets acotados y tone-map HDR.
- **Robustez en Windows**: video-use tiene bugs de codificación abiertos; HyperFrames tiene issues de disco/DLL/EBUSY en
  Windows; Remotion es el más sólido ahí.
- **Performance en piezas largas** con renderers de navegador (Remotion/HyperFrames): lento; hay que mantener el corte
  base en ffmpeg.
