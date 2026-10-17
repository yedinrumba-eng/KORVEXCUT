# 001 — Motor kcut (F1a)

Fecha: 16/10/2026 · Slice: S1.1–S1.10 · Estado: APROBADO (Gate 2, Yedin, 16/10/2026)

> Contrato del motor `kcut`. Se implementa **un slice a la vez y en orden**. Cada sección `S1.x`
> es un contrato completo (archivos, formatos, criterios, verificación). Un slice no arranca hasta
> que el anterior tiene todos sus criterios en ✅ con la salida real pegada. Si algo de aquí no
> alcanza para implementar sin adivinar, el implementador devuelve **BLOQUEADO** con la pregunta.

## Objetivo

Que exista el CLI determinista `kcut` (paquete Python 3.12 instalable) que, desde una carpeta de
crudo, haga inventario, sincronice cámaras, transcriba, empaquete la transcripción, enseñe ondas y
frames, valide un EDL en frames enteros, genere el storyboard visual de la Puerta 1 y produzca
`salida/vN.mp4` (cortes, multicámara, looks, gráficos HTML con alfa, voz, SFX, música) auditado
por `kcut qa`, todo comprobado con un pytest de punta a punta sobre un proyecto 100 % sintético.

## Contexto mínimo

1. Repo público MIT `C:\PROYECTOS\KORVEX DEV\KORVEXCUT`. Hoy solo hay docs y `piloto/` (scripts de
   referencia amarrados a un video: se leen como referencia, **no se importan ni se modifican**).
   El código nuevo va en `src/kcut/` y `tests/`.
2. Claude decide (estrategia, EDL, gráficos, sonido) escribiendo archivos en `edit/` de un
   proyecto de video; `kcut` solo ejecuta y mide. Cada proyecto de video vive en cualquier
   carpeta del usuario, fuera de git (D3).
3. Tiempos de edición en **frames enteros**; color con matrices **bt709 explícitas**; ffmpeg
   siempre con **lista de argumentos**; todo I/O en **UTF-8 explícito**.
4. Máquina de referencia: i7-1165G7, 16 GB, Iris Xe, sin NVIDIA, Windows 11, ffmpeg 8.1.1 full
   (gyan.dev), Python 3.12 vía `py -3.12` (el `py` por defecto es 3.14: ctranslate2 no lo soporta).
5. Prohibido leer, listar o referenciar `videoi/` (footage crudo, fuera de git).

---

## 0. Reglas transversales (aplican a TODOS los slices)

### 0.1 Instalación y entorno de desarrollo

Desde la raíz del repo (Git Bash o PowerShell, mismas rutas con `/`):

```
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]" -c requirements.lock
```

- `requirements.lock` (raíz del repo, commiteado, S1.1) fija la versión exacta de cada dependencia
  de runtime y de sus transitivas. Fija `playwright==1.63.0`, cuyo Chromium (`chromium-1243`) ya
  está en `%LOCALAPPDATA%\ms-playwright`; otra versión pediría bajar otro navegador. (001.1)

- `requires-python = ">=3.12,<3.13"` en `pyproject.toml`: pip debe rechazar 3.14.
- Todos los comandos de verificación de este spec usan `.venv/Scripts/python.exe -I -X utf8`
  (lección 6: `-I` ignora `PYTHONUTF8`, por eso va `-X utf8`). Ejemplo:
  `.venv/Scripts/python.exe -I -X utf8 -m kcut doctor --json`.
- Instalación de usuario soportada (no es criterio): `pipx install --python 3.12 .`
- Chromium de Playwright y el modelo `medium` de faster-whisper ya están en esta máquina. Si
  faltan, `kcut` dice el comando para bajarlos y **no lo corre solo** (toda descarga necesita OK).

### 0.2 Árbol final del paquete (cada archivo indica el slice que lo crea)

```
pyproject.toml                                  S1.1
src/kcut/__init__.py  __main__.py  cli.py       S1.1
src/kcut/errors.py  console.py  proc.py         S1.1
src/kcut/toolpath.py  scrub.py                  S1.1 (partidos de proc.py por la regla de 300 líneas; proc los re-exporta)
src/kcut/logfile.py                             S1.2 (partido de proc.py por la regla de 300 líneas en 001.6; proc lo re-exporta)
src/kcut/childlog.py                            S1.1 (001.3: stderr de hijos por trozos con cola de 8 MB; escribe por `logfile.log_writer`)
src/kcut/commands/__init__.py  doctor.py        S1.1
src/kcut/doctor/__init__.py  ffmpeg_caps.py  checks.py          S1.1
src/kcut/doctor/result.py  chain_checks.py                      S1.1/S1.2 (partidos de checks.py por la regla de 300 líneas; 001.4)
src/kcut/assets/fonts/inter-latin-{600,800,900}-normal.woff2  OFL-Inter.txt   S1.1
src/kcut/jsonio.py  schema_util.py  timebase.py  paths.py  project.py          S1.2
src/kcut/config/__init__.py  model.py  load.py  template.py                    S1.2
src/kcut/config/names.py  fields.py                                            S1.2 (partidos por la regla de 300 líneas; 001.6)
src/kcut/recursos/__init__.py  manifest.py                                     S1.2
src/kcut/ff/__init__.py  color.py  args.py                                     S1.2 (`fnum` vive en `ff/args.py`)
src/kcut/audio/__init__.py  wavio.py                                           S1.2
src/kcut/ingest/__init__.py  probe.py  naming.py  classify.py  inventory.py  sync.py  workfiles.py  run.py   S1.2
src/kcut/ingest/inventory_model.py  sync_stage.py                              S1.2 (partidos por la regla de 300 líneas; 001.4)
src/kcut/ingest/sync_reasons.py                                                S1.2 (textos de `reason`, `rejection_motive`, `ambiguity_message`; partido de sync.py por la regla de 300 líneas; 001.7)
src/kcut/ingest/scan.py  examine.py  inventory_check.py  inventory_json.py     S1.2 (partidos por la regla de 300 líneas; 001.6)
src/kcut/commands/new.py  ingest.py                                            S1.2
src/kcut/text/__init__.py  normalize.py  corrections.py                        S1.3
src/kcut/transcribe/__init__.py  model.py  engine.py  cache.py                 S1.3
src/kcut/analysis/__init__.py  energy.py                                       S1.3
src/kcut/pack/__init__.py  phrases.py  markers.py  votes.py  writer.py         S1.3
src/kcut/pack/assemble.py  src/kcut/transcribe/document.py                    S1.3 (partidos por la regla de 300 líneas; 001.11)
src/kcut/commands/transcribe.py  pack.py                                       S1.3
src/kcut/timeparse.py  ff/reader.py                                            S1.4
src/kcut/viz/__init__.py  draw.py  timeline.py  grid.py                        S1.4
src/kcut/commands/view.py  frames.py                                           S1.4
src/kcut/edl/__init__.py  model.py  validate.py  timeline.py  words.py  gate.py              S1.5
src/kcut/render/__init__.py  looks.py  geometry.py  screen_card.py  mezz.py  reads.py  compose.py  encoder.py  lock.py   S1.5
src/kcut/audio/voice_track.py                                                  S1.5
src/kcut/pipeline/__init__.py  mux.py                                          S1.5
src/kcut/commands/edl.py  render.py                                            S1.5
src/kcut/gfx/__init__.py  anchors.py  schema.py  components.py  captions.py  resolve.py  assets.py  page.py  capture.py  overlay.py   S1.6
src/kcut/gfx/web/runtime.js  base.css                                          S1.6
src/kcut/gfx/web/components/captions.js  title.js  label.js  kinetic.js  endcard.js          S1.6
src/kcut/gfx/web/components/steps.js  sticker.js  holo_board.js  globe.js     S1.7
src/kcut/commands/graphics.py                                                  S1.6
src/kcut/audio/sfx_synth.py  sfx_library.py  sfx_schema.py  sfx_bus.py  gain.py             S1.8
src/kcut/audio/chords.py  music_synth.py  music_file.py  music_schema.py       S1.8
src/kcut/audio/loudnorm.py  mix_graph.py  mixer.py                             S1.8
src/kcut/commands/mix.py                                                       S1.8
src/kcut/qa/__init__.py  streams.py  loudness.py  detect.py  transcript_diff.py  contact.py  report.py  run.py   S1.9
src/kcut/pipeline/snapshot.py  build.py                                        S1.9
src/kcut/catalog/__init__.py  model.py  static_items.py  planned.py  collect.py               S1.9
src/kcut/commands/qa.py  build.py  catalog.py                                  S1.9
src/kcut/storyboard/__init__.py  beats.py  notes.py  panel.py  html.py  sheet.py  run.py     S1.10
src/kcut/commands/storyboard.py                                                S1.10
tests/__init__.py  conftest.py  unit/__init__.py  integration/__init__.py  e2e/__init__.py  fixtures/__init__.py   S1.1/S1.2
tests/fixtures/links.py                         S1.2 (crea junctions, symlinks y hard links para los tests; 001.6)
tests/fixtures/spawned.py                                                      S1.2 (helpers de procesos hijo para los tests de log y huérfanos; 001.7)
```

Reglas de código: una entidad por archivo, **≤ 300 líneas por archivo** (si un archivo se pasa,
se parte y se avisa en el reporte; no se comprime código para caber). Vale también para `tests/`:
`tests/unit/test_doctor_checks.py` se pasó de 300 líneas y se parte (p. ej. `TestDoctorCommand` →
`tests/unit/test_doctor_command.py`), conservando los node ids de los criterios S1.1-14 y S1.1-15
(`tests/unit/test_doctor_checks.py::test_whisper_model_not_cached` y `::test_chromium_hint_derived`). (001.2) Type hints completos,
`mypy --strict` limpio, ruff limpio. Cero `TODO`, cero funciones vacías, cero `pass` de relleno.
Comentarios y docstrings en inglés; mensajes al usuario (`*_es`, salida humana) en español.
`piloto/` no se toca.

### 0.3 Proyecto de video (lo crea `kcut new`)

```
<proyecto>/
  kcut.toml                 configuración del video (S1.2)
  crudo/                    material del usuario; kcut NUNCA escribe, mueve, renombra ni borra nada aquí (001.4)
  recursos/recursos.json    manifiesto de recursos (D7); recursos/<sub>/... archivos aprobados
  edit/estrategia.md        Puerta 1; front-matter con "aprobado: si|no"
  edit/versiones.md         lo escribe Claude (D5); kcut no lo toca después de crearlo
  edit/transcripcion.md     kcut pack (S1.3)
  edit/palabras.tsv         kcut pack (S1.3)
  edit/correcciones.json    lo escribe Claude (S1.3)
  edit/edl-vN.json          lo escribe Claude (S1.5)
  edit/graphics.json        lo escribe Claude (S1.6)
  edit/sfx.json  edit/music.json   los escribe Claude (S1.8)
  edit/storyboard.html      kcut storyboard (S1.10)
  salida/vN.mp4             kcut build (S1.9)
  qa/vN/report.json  qa/vN/contact.jpg  qa/vN/inputs/   kcut qa / build (S1.9)
  qa/storyboard.png  [qa/storyboard-p2.png ...]         kcut storyboard (S1.10)
  .kcut/                    regenerable: inventory.json proxy/ wav16/ wav48/ mezz/ transcripts/
                            view/ frames/ build/vN/ storyboard/ logs/ locks/
```

### 0.4 CLI común

- Entry point `kcut = "kcut.cli:main"`; también `python -m kcut`. `kcut --version` imprime
  `kcut 0.1.0` y sale 0.
- Cada subcomando acepta, **después** del nombre del subcomando: `--json`, `--project DIR`,
  `-v/--verbose` (argparse con un parser padre común).
- Proyecto: `--project DIR` o, si falta, se sube desde el cwd hasta encontrar `kcut.toml`. No
  encontrado → exit 3. `doctor`, `catalog` y `new` no requieren proyecto.
- `--json`: stdout contiene **exactamente un** documento JSON (UTF-8, `ensure_ascii=False`), también
  en error: `{"ok": false, "error": {"exit_code": 3, "kind": "ProjectError", "message": "..."}}`.
  Progreso y avisos van a stderr.
- Sin `--json`: texto humano en español a stdout, líneas con prefijo `[OK]`, `[FALTA]`, `[AVISO]`,
  `[ERROR]`, `[INFO]`. Puntuación ASCII (`-`, `...`), sin guiones largos ni emojis; acentos sí.
  La redacción humana es libre; **los tests solo validan `--json` y códigos de salida**.
- Argumento EDL (`--edl` o posicional): ruta relativa al proyecto. Por defecto, `edit/edl-vN.json`
  con el N más alto. Ninguno → exit 3. `N` sale del nombre y debe coincidir con `"version"`.

| Comando | Firma | Slice |
|---|---|---|
| `kcut doctor` | `[--json]` | S1.1 |
| `kcut new` | `<path> [--name N] [--preset 9:16 o 16:9] [--fps F] [--lang es]` | S1.2 |
| `kcut ingest` | `[--no-proxy] [--resync]` | S1.2 |
| `kcut transcribe` | `[IDS...] [--force] [--allow-download]` | S1.3 |
| `kcut pack` | (sin argumentos) | S1.3 |
| `kcut view` | `<clip> <start> <end> [--filmstrip N] [--out PNG]` | S1.4 |
| `kcut frames` | `<clip> <t> [<t> ...] [--grid PCT] [--width PX] [--out DIR]` | S1.4 |
| `kcut edl check` | `[EDL]` | S1.5 |
| `kcut render` | `[--edl EDL] [--no-graphics]` | S1.5 (+S1.6) |
| `kcut graphics` | `check [--edl EDL]` · `capture [--edl EDL] [--force]` · `still <f> [<f> ...] [--edl EDL] [--out DIR]` | S1.6 |
| `kcut mix` | `[--edl EDL]` | S1.8 |
| `kcut qa` | `<video> [--edl EDL]` | S1.9 |
| `kcut build` | `[--edl EDL] [--skip-qa] [--force]` | S1.9 |
| `kcut catalog` | `[--category C]` | S1.9 |
| `kcut storyboard` | `[--edl EDL] [--min-beat-ms MS]` | S1.10 |

### 0.5 Códigos de salida (`src/kcut/errors.py`)

| Exit | Clase | Cuándo |
|---|---|---|
| 0 | — | OK (incluye QA `incomplete`, con aviso) |
| 1 | `CheckFailed` | doctor con requisito faltante, `edl check`/`graphics check` con errores, QA `fail` |
| 2 | `UsageError` | argumentos inválidos (incluye los de argparse) |
| 3 | `ProjectError` | sin `kcut.toml`, config inválida, ruta fuera del proyecto, archivo faltante, JSON mal formado, destino bloqueado por otro programa |
| 4 | `ToolError` | ffmpeg/ffprobe/Chromium terminó con error |
| 5 | `GateError` | estrategia no aprobada; recurso sin aprobar en el manifiesto |
| 6 | `LockedError` | otro proceso está renderizando la misma salida |
| 7 | `MissingDependency` | ffmpeg, modelo de Whisper o Chromium no disponibles en tiempo de ejecución, o binario rechazado por seguridad (ruta no absoluta, `.bat`/`.cmd` en Windows) |
| 10 | `InternalError` | excepción no prevista (traceback completo al log, mensaje corto al usuario) |
| 130 | — | Ctrl+C: se terminan los procesos hijos, se borran los `.partial`, se liberan locks |

`KcutError(Exception)` tiene `exit_code: int` y `message_es: str`; cada subclase fija su código.
`cli.main` captura `KcutError` → imprime `[ERROR] <message_es>` en stderr (o el JSON de error) y
devuelve el código.

### 0.6 Tiempo y unidades (`src/kcut/timebase.py`)

- `fps` del proyecto ∈ {24, 25, 30, 48, 50, 60}. `spf = 48000 // fps` (muestras de audio por frame:
  2000, 1920, 1600, 1000, 960, 800). Cualquier otro fps → `ProjectError`. (DS13)
- Sufijos de campo: `_f` = frames enteros al fps del proyecto · `_ms` = milisegundos enteros, **solo**
  en mediciones (caché de transcripción, inventario). Nunca segundos con decimales en datos; los
  segundos solo aparecen en texto humano y en campos `*_display` de tipo string. (DS1)
- Reloj de fuente: el frame `f` de un clip es el instante `f/fps` s desde el inicio del archivo
  (`format.start_time`); la muestra `n` del wav de 48 kHz es `n/48000` s desde ese mismo inicio.
- En JSON, todo campo `*_f` debe ser entero JSON: `30.0` o `true` → error de esquema.
- Comparaciones ms↔frames siempre con enteros, en unidades de `1/(1000·fps)` s: ms se multiplica
  por `fps`, frames por `1000`. Prohibido `float` para comparar tiempos.
- Funciones exportadas (puras, testeadas):
  `ALLOWED_FPS: frozenset[int]`, `spf(fps: int) -> int`,
  `ms_to_f_floor(ms: int, fps: int) -> int`, `ms_to_f_ceil(ms: int, fps: int) -> int`,
  `ms_to_f_round(ms: int, fps: int) -> int` (redondeo mitad hacia arriba, aritmética entera),
  `f_to_ms_round(f: int, fps: int) -> int`, `rdiv(x: int, d: int) -> int` (= `(2x + d) // (2d)`),
  `fmt_tc(f: int, fps: int) -> str` (`"mm:ss.s"`), `fmt_s(f: int, fps: int) -> str` (`"12.34"`).

### 0.7 Color

- Lectura YUV→RGB siempre `scale=in_color_matrix=bt709:in_range=tv,format=rgb24` (y después
  `format=bgr24` para OpenCV). Escritura RGB→YUV siempre `scale=out_color_matrix=bt709:out_range=tv,format=yuv420p`
  más `-colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv` (lección 5).
- Todos los intermedios (proxies, mezzanines, video final) quedan SDR bt709 rango tv.
- HDR→SDR (cadena del piloto, la única aprobada en esta máquina; libplacebo/Vulkan descartado):
  `zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p`.
- Looks: cadenas RGB-only aplicadas en el lector, entre `format=rgb24` y `format=bgr24` (DS3, S1.5).

### 0.8 Procesos externos (`src/kcut/proc.py`)

- `subprocess` siempre con `list[str]`, `shell=False`. Pasar un `str` → `TypeError` (testeado).
  `args[0]` debe ser una ruta absoluta (de `tool_path` o `sys.executable`); si no → `ValueError`
  "usa tool_path" (testeado). (001.2)
- Un `ChildProcess` que sale del `with` **sin** excepción con el hijo todavía vivo no lo mata en
  silencio: espera hasta `grace_s`; si termina, bien; si no, `kill()` y `ToolError` diciendo que no
  se esperó al hijo. Si sale por excepción: `kill()` + `wait()` como antes. (001.2)
- Todo ffmpeg lleva `-hide_banner -nostdin`; `-y` solo cuando el destino es un `.partial`/temporal.
- stderr de **cada** hijo va a su propio archivo temporal (nunca un handle compartido, nunca `PIPE`
  sin leer) y se agrega al log del comando cuando el hijo termina (0.11). Solo se devuelve en
  memoria cuando se parsea (`-filters`, `loudnorm`, `ebur128`, `blackdetect`). (001.1)
- **Privacidad de metadatos** (001.1): los MOV del iPhone traen ubicación GPS y modelo del equipo,
  y la salida de kcut llega al contexto de un LLM. Todo ffmpeg/ffprobe que abre medios del usuario
  lleva `-loglevel error` (`-v error` en ffprobe), y los intermedios que se escriben desde esos
  medios llevan `-map_metadata -1`. Todo texto de un hijo que vaya a un mensaje de error, a
  `--json` o al log pasa antes por `proc.scrub_media_metadata`. El JSON crudo de ffprobe nunca se
  guarda ni se imprime; de sus `tags` solo se lee `rotate`.
- **Ninguna ruta de archivo dentro de un filtergraph** (los `C:` de Windows rompen el parser).
  Los archivos entran por `-i`; lo que ffmpeg mide se lee de stderr; textos y etiquetas se dibujan
  con Pillow, nunca con `drawtext`.
- Ningún texto del usuario entra a un filtergraph. Los números se formatean con
  `fnum(x: float) -> str` (en `ff/args.py`; `f"{x:.6f}"` sin ceros sobrantes; NaN/inf → `ValueError`) y los colores
  se validan `^#[0-9A-Fa-f]{6}$` y se pasan como `0xRRGGBB`.
- Constructores de argumentos = funciones puras que devuelven `list[str]` (testeadas sin ejecutar).
- Binarios: `KCUT_FFMPEG` / `KCUT_FFPROBE` (variables de entorno, opcionales) o `shutil.which`, con
  las reglas de `proc.tool_path` (S1.1): en Windows `NoDefaultCurrentDirectoryInExePath=1` antes de
  `shutil.which` (si no, un `ffmpeg.exe` plantado en la carpeta de crudo se ejecuta), ruta final
  absoluta, y en Windows solo sufijo `.exe` o `.com` (un `.bat`/`.cmd` pasa por `cmd.exe`, que
  re-parsea los argumentos: `x&whoami` se ejecutó). Si no → `MissingDependency` (7). (001.1)
  La ruta se resuelve **primero** (sigue symlinks) y el sufijo se revisa sobre la ruta **resuelta**:
  un symlink `x.exe` que apunta a un `.cmd` se rechaza. (001.2)

### 0.9 Archivos, rutas y JSON

- `open`, `read_text`, `write_text` siempre con `encoding="utf-8"`; texto escrito con `newline="\n"`.
- JSON: `jsonio.write_json_atomic(path, obj)` (escribe `<path>.tmp`, luego `os.replace`),
  `json.dumps(obj, ensure_ascii=False, indent=1)` + `"\n"`. `jsonio.read_json(path)` →
  `ProjectError` con archivo, línea y columna si está mal formado; también convierte `ValueError`
  y `RecursionError` en `ProjectError` (001.4). Un archivo de **caché** (`.kcut/`) que da
  `ProjectError` se trata como ausente y se reconstruye (con aviso); un archivo del usuario
  (`edit/`, `kcut.toml`, `recursos/recursos.json`) sigue siendo error.
- **Nada de la caché es de confianza** (001.4): todo lo que se lee de `.kcut/` (inventario,
  sidecars) se valida antes de usarse; si no pasa, se trata como ausente. Toda escritura, movida o
  borrado bajo `.kcut/` pasa antes por `workfiles._assert_in_cache(project, path)` (resuelve la ruta
  y exige que quede dentro de `layout.cache`). kcut nunca escribe, mueve ni borra nada bajo `crudo/`.
- Rutas que vienen de datos (JSON, toml) son relativas al proyecto, con `/`, y pasan por
  `paths.resolve_in_project` (S1.2). Se guardan siempre en formato POSIX relativo.
- Validación de esquemas a mano (sin `jsonschema`) con `schema_util.py` (S1.2): claves
  desconocidas → error con su ruta (`spans[3].zoom`), tipos estrictos, rangos.

### 0.10 Windows (requisitos, no detalles)

1. Python 3.12 fijo (`requires-python`), `py -3.12` en toda instrucción.
2. `console.setup_streams()` al inicio de `main`: `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")`.
3. Salida de hijos decodificada con `encoding="utf-8", errors="replace"`.
4. Locks con `msvcrt.locking` (Windows) / `fcntl.flock` (POSIX). **Prohibido `os.kill(pid, 0)`**:
   en Windows la señal 0 es `CTRL_C_EVENT` y otras señales terminan el proceso. (DS11)
5. `os.replace` sobre un destino abierto por un reproductor da `PermissionError` → exit 3 con
   "cierra el archivo <ruta> en el reproductor y repite". Si en el destino (p. ej.
   `.kcut/inventory.json` o un sidecar) hay una **carpeta**, el mensaje es otro: "en <ruta> hay una
   carpeta donde kcut espera un archivo; bórrala o muévela" (exit 3). (001.6)
6. Los tests crean proyectos en rutas con espacio y ñ (`<tmp>/proyecto ñandú`).
7. Rutas rechazadas: absolutas, con letra de unidad, UNC (`\\`), con `..` que escape, con `:`
   (flujos ADS), con byte NUL, con nombres reservados (`CON PRN AUX NUL COM1-9 LPT1-9`, con o sin
   extensión). Comparación con `os.path.normcase`.
8. Nombres de caché cortos (slug ≤ 40 caracteres) para no pegar con rutas largas. Sin symlinks.
9. Ctrl+C: los hijos comparten consola y reciben la señal; el padre espera 5 s y luego `kill()`.
10. URLs de archivo para Chromium con `Path.as_uri()` (codifica espacios y acentos).
11. Búsqueda de ejecutables sin el cwd (`NoDefaultCurrentDirectoryInExePath=1`) y sin `.bat`/`.cmd`
    (0.8). (001.1)
12. Varios hijos que heredan el mismo handle de log se pisan en Windows (2 hijos × 200 líneas
    dejaron 220 líneas en vez de 402): cada hijo escribe su stderr a su propio temporal (0.11). (001.1)

### 0.11 Logs, progreso y locks

- Log por comando: `.kcut/logs/<comando>-<YYYYmmdd-HHMMSS>-<pid>.log` (UTF-8): stderr de los hijos,
  tiempos por paso, tracebacks. Formato por hijo (001.1): al arrancar, una línea de cabecera
  `$ <argumentos unidos con subprocess.list2cmdline>`; al terminar, en un solo bloque, su stderr
  completo (pasado por `scrub_media_metadata`) y la línea `[exit <código> en <s> s]`. Cabecera y
  bloque se escriben en modo append bajo un `threading.Lock` por ruta de log resuelta, así que
  dos hijos concurrentes nunca se pisan. La cola de un error sale solo del stderr de ese hijo.
- Creación y uso seguro del log (001.6; `cli._run_log` y `proc.append_log`): cada corrida crea su
  log con creación exclusiva (`os.open(..., O_CREAT | O_EXCL | O_WRONLY)`, nombre único con el pid)
  dentro de `.kcut/logs/` ya validado (`check_layout_inside`). Antes de **cada** append se comprueba
  con `os.lstat` que la ruta es un archivo regular (`stat.S_ISREG`), con `st_nlink == 1` y que
  resuelve dentro de la caché real; si no, no se escribe ahí (el log va solo a stderr, con aviso).
  Así un hard link plantado en `.kcut/logs/` no puede escribir dentro de `crudo/`.
  Desde 001.7: un `OSError` al abrir o escribir el log nunca sale de `append_log` (va a stderr con
  aviso); la cabecera `$ ...` de un hijo se escribe **antes** del `Popen`; y el log que una corrida
  creó y dejó en 0 bytes se borra al terminar (ver 001.7 punto 4).
- Progreso a stderr como mucho cada 2 s: `render v1: 640/1469 frames (43%) - 18.2 fps - faltan 45 s`.
- Lock por salida: `.kcut/locks/build-vN.lock`, abierto y bloqueado sin espera durante todo el
  comando (`render`, `mix`, `build`, `graphics capture` comparten `build-vN`); si no se puede
  bloquear → `LockedError` (6). El archivo guarda pid y hora solo como información.
- Escritura de salidas grandes en `<nombre>.partial.<ext>` y `os.replace` al final.

### 0.12 Dependencias

Runtime (aprobadas, nada más): `numpy>=1.26`, `scipy>=1.11`, `opencv-python>=4.9`, `Pillow>=12.3`,
`faster-whisper>=1.0`, `playwright>=1.55.1` (pisos de seguridad: Pillow 10.3.0–12.2.0 tiene
avisos OSV, 001.2; el de Playwright viene de 001.1). Versiones exactas en `requirements.lock` (S1.1), que se usa como `-c` al instalar.
Stdlib para todo lo demás (`tomllib`, `argparse`, `wave`, `difflib`, `hashlib`, `html`, `base64`,
`concurrent.futures`, `tempfile`, `threading`).
Dev (Carril C): `pytest>=8`, `pytest-cov>=5`, `pytest-timeout>=2.3`, `ruff>=0.6`, `mypy>=1.10`.
Herramientas externas: ffmpeg/ffprobe ≥ 7 build full. `flite` (filtro de ffmpeg, ya incluido en el
build) se usa **solo en tests** para sintetizar voz.

### 0.13 Decisiones de este spec (DS#) — el dueño las ve en el gate

| # | Decisión | Por qué |
|---|---|---|
| DS1 | Datos de edición en frames; `_ms` enteros solo en mediciones (caché ASR, inventario) | La caché de Whisper no depende del fps del proyecto; Claude nunca escribe ms |
| DS2 | Los PNG de gráficos se componen en numpy dentro del bucle de render: un solo encode | Frame exacto, sin doble compresión; la matriz bt709 la pone el encoder (lección 5) |
| DS3 | Looks = cadenas ffmpeg solo de filtros RGB, después de una conversión bt709 explícita | Un filtro que solo acepta YUV obliga a ffmpeg a meter una conversión oculta con bt601 |
| DS4 | Intermedios de audio en `.f32` crudo (float32 LE mono 48 kHz); `wave` de stdlib solo para s16 | Sin dependencias nuevas y sin recortar picos antes del loudnorm |
| DS5 | Mezcla mono, salida AAC estéreo duplicada | El material del piloto es mono; mezcla estéreo real va con F3 |
| DS6 | Fuentes Inter (OFL) copiadas de Korvex Motion al paquete; Pillow usa `ImageFont.load_default(size)` | Fuentes self-hosted; Pillow no lee woff2 de forma fiable |
| DS7 | Anclas de gráficos y SFX a palabras/frames de fuente, resueltas a frames de salida | Sobreviven a un EDL nuevo (como `KEY` en `piloto/cues.py`) y detectan cues huérfanos |
| DS8 | Correcciones por id de palabra + texto esperado | Lección 3: corregir por texto se come otras frases |
| DS9 | Todo recurso de `recursos/` usado en un build debe estar en el manifiesto con `approved_by` | "Descargar assets sin aprobación" está descartado |
| DS10 | El modelo de Whisper solo se baja con `--allow-download` | Toda descarga necesita OK explícito |
| DS11 | Locks de archivo del sistema operativo | `os.kill(pid, 0)` en Windows manda Ctrl+C o mata el proceso |
| DS12 | Resolución del mezzanine derivada del zoom máximo usado | Cura la deuda 3 sin pagar 4K donde no hace falta |
| DS13 | fps permitido {24,25,30,48,50,60} | Muestras por frame enteras = audio exacto a la muestra |
| DS14 | `kcut new` se niega a crear un proyecto dentro del repo de kcut | D3: el repo público no lleva trabajo de videos |
| DS15 | Storyboard en páginas de 12 paneles de ~1900 px | Que Claude lo lea sin que la imagen se encoja hasta lo ilegible |

### 0.14 Flujo del motor (dónde cae cada comando)

`new` → el usuario suelta material en `crudo/` → `ingest` → `transcribe` → `pack` → Claude lee
`edit/transcripcion.md`, mira dudas con `view`/`frames` (lección 8: antes de botar una pausa larga,
mirar sus frames) → Claude escribe `edit/estrategia.md` (`aprobado: no`), `edit/edl-v1.json`,
`graphics.json`, `sfx.json`, `music.json` → `edl check` + `graphics check` → **`storyboard`** →
el dueño mira `edit/storyboard.html` y aprueba (Puerta 1: Claude pone `aprobado: si`) → `build`
(render + gráficos + mezcla + mux + qa) → notas por chat → `edl-v2.json` → `build` …
`render` y `build` se niegan a correr sin `aprobado: si`; `storyboard` no lo exige.

---

## S1.1 — Andamiaje del paquete + `kcut doctor`

### Archivos

#### `pyproject.toml` — CREAR
- `[build-system]`: `requires = ["setuptools>=77"]`, `build-backend = "setuptools.build_meta"`.
- `[project]`: `name = "kcut"`, `version = "0.1.0"`, `description = "Motor determinista de edicion de video de KORVEXCUT"`,
  `readme = "README.md"`, `license = "MIT"`, `license-files = ["LICENSE"]`,
  `requires-python = ">=3.12,<3.13"`, `dependencies` = lista de 0.12.
- `[project.optional-dependencies] dev` = lista dev de 0.12.
- `[project.scripts] kcut = "kcut.cli:main"`.
- `[tool.setuptools.packages.find] where = ["src"]`.
- `[tool.setuptools.package-data] kcut = ["assets/fonts/*", "gfx/web/*.js", "gfx/web/*.css", "gfx/web/components/*.js"]`.
- `[tool.ruff]`: `line-length = 100`, `target-version = "py312"`, `src = ["src", "tests"]`.
  `[tool.ruff.lint] select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]`, `ignore = ["RUF001", "RUF002", "RUF003"]`.
- `[tool.mypy]`: `python_version = "3.12"`, `strict = true`, `files = ["src"]`, `mypy_path = "src"`.
  Override `ignore_missing_imports = true` para `faster_whisper.*`, `ctranslate2.*`, `scipy.*`.
- `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `addopts = "-ra --strict-markers"`,
  `timeout = 300`, `markers = ["ffmpeg: necesita ffmpeg", "chromium: necesita Chromium de Playwright", "whisper: necesita el modelo local", "flite: necesita el filtro flite", "slow: tarda mas de 2 s (001.7)", "e2e: punta a punta"]`.

#### `requirements.lock` — CREAR (raíz del repo, commiteado; 001.1)
- Una línea `nombre==versión` por cada distribución de la **clausura de runtime**: las 6 de 0.12 y
  todas sus dependencias transitivas, con la versión instalada en el `.venv` de referencia. Orden
  alfabético sin distinguir mayúsculas. Primera línea: `# kcut runtime lock - <DD/MM/AAAA> - Python <x.y.z> - <plataforma>`.
- Sin la línea de `kcut` (editable) y sin herramientas dev (`pytest`, `pytest-cov`, `pytest-timeout`,
  `ruff`, `mypy`, `coverage`, `iniconfig`, `pluggy`, `mypy_extensions`) salvo que una dependencia de
  runtime las requiera.
- Generación (comando de un solo uso desde el `.venv` de referencia; el script no se commitea):
  clausura con `importlib.metadata.requires()` recursivo desde las 6 raíces, ignorando requisitos
  con marcador `extra ==` y evaluando los demás marcadores con
  `pip._vendor.packaging.requirements.Requirement(r).marker.evaluate()` (marcador `None` = se
  incluye); versión de cada una con `importlib.metadata.version()`.
- Debe fijar `playwright==1.63.0` (su Chromium ya está en disco). Si el venv de referencia tiene
  otra versión de Playwright → BLOQUEADO. Se regenera solo cuando cambia una dependencia, y eso
  pasa por el dueño.

#### `src/kcut/__init__.py` — CREAR
Solo `__version__ = "0.1.0"`.

#### `src/kcut/__main__.py` — CREAR
`raise SystemExit(main())` importando `main` de `kcut.cli`.

#### `src/kcut/cli.py` — CREAR
- `COMMAND_MODULES: tuple[str, ...] = ("kcut.commands.doctor",)` — cada slice agrega el suyo.
- Contrato de cada módulo de comando: `NAME: str`, `HELP_ES: str`,
  `add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser], parent: argparse.ArgumentParser) -> argparse.ArgumentParser`
  y `run(args: argparse.Namespace) -> int`.
- `main(argv: list[str] | None = None) -> int`: `setup_streams()`, arma el parser (`prog="kcut"`,
  `--version`), subcomandos obligatorios, ejecuta `run`, mapea excepciones según 0.5.

#### `src/kcut/errors.py` — CREAR
Jerarquía de 0.5 (`KcutError`, `CheckFailed`, `UsageError`, `ProjectError`, `ToolError`,
`GateError`, `LockedError`, `MissingDependency`, `InternalError`).

#### `src/kcut/console.py` — CREAR
- `setup_streams() -> None` (0.10.2).
- `class Out`: `__init__(self, json_mode: bool)`, `line(self, tag: str, text: str) -> None` (no
  imprime nada en modo JSON), `result(self, obj: Mapping[str, object]) -> None` (en modo JSON
  imprime el documento único; en modo humano no hace nada), `warn(self, text: str) -> None` (stderr siempre).
- `class Progress`: `__init__(self, label: str, total: int, unit: str)`, `update(self, done: int) -> None`
  (stderr, máx. cada 2 s, con velocidad y tiempo restante), `close(self) -> None`.

#### `src/kcut/proc.py` — CREAR (reglas reforzadas en 001.1)
- `tool_path(name: Literal["ffmpeg", "ffprobe"]) -> Path`, sin caché, en este orden:
  1. Candidato: `KCUT_FFMPEG`/`KCUT_FFPROBE` si existe (debe ser ruta absoluta); si no, en Windows
     `os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"` **antes** de `shutil.which(name)`
     (`None` o ruta no absoluta → `MissingDependency` (7)).
  2. Se resuelve **primero**: `Path(candidato).resolve(strict=True)` (sigue symlinks); si no existe o
     no es archivo → 7. (001.2)
  3. **Después**, sobre la ruta ya resuelta, en Windows el sufijo debe ser `.exe` o `.com` (sin
     distinguir mayúsculas): `.bat`, `.cmd`, o un symlink `x.exe` que apunta a un `.cmd` → 7. El
     mensaje dice cuál regla falló. (001.2)
  4. Devuelve la ruta resuelta.
- `scrub_media_metadata(text: str) -> str` (pura): (a) quita cada línea `^\s*Metadata:\s*$` y todas
  las siguientes con más sangría que ella; (b) quita toda línea `clave : valor` cuya clave, sin
  distinguir mayúsculas, contenga `location`, `gps`, `com.apple.`, `make`, `model` o
  `creation_time`; (c) reemplaza cualquier coordenada ISO 6709 (`[+-]\d{1,3}\.\d+[+-]\d{1,3}\.\d+`)
  por `[ubicacion omitida]`.
- `@dataclass(frozen=True) class RunResult: returncode: int; stdout: bytes; stderr: str`
  (`stderr` crudo del hijo solo si `capture_stderr=True`; si no, `""`).
- `run(args: list[str], *, log: Path | None = None, timeout_s: float | None = None, check: bool = True, capture_stderr: bool = False, grace_s: float = 5.0) -> RunResult`:
  stdout por `PIPE`; stderr a un `tempfile.TemporaryFile()` propio de ese hijo. `communicate(timeout=timeout_s)`;
  si vence: `kill()` y `communicate(timeout=grace_s)`; si vuelve a vencer (un nieto mantiene el
  pipe abierto), cierra `proc.stdout` y lanza `ToolError` "se paso del tiempo (<timeout_s> s)"
  sin esperar más (en Windows `kill()` no mata nietos; se anota en el log). Al terminar, por la
  vía que sea, el stderr del hijo se agrega al log (0.11). Con `check=True` y código ≠ 0 →
  `ToolError` con las últimas 20 líneas del stderr **de ese hijo**, pasadas por `scrub_media_metadata`.
- `popen(args: list[str], *, log: Path, stdin_pipe: bool = False, stdout_pipe: bool = False, grace_s: float = 5.0) -> ChildProcess`:
  `class ChildProcess` (context manager) con `stdin`, `stdout`, `pid`,
  `wait(timeout_s: float | None = None, grace_s: float = 5.0) -> int` (misma regla de tiempo duro;
  al final agrega su stderr al log y cierra su temporal), `kill() -> None`,
  `stderr_tail(n: int = 20) -> str` (solo de este hijo, con `scrub_media_metadata`).
  Salida del `with` (001.2): **por excepción** → `kill()` + `wait()` y la excepción sigue;
  **sin excepción** con el hijo ya terminado → se cierra normal (stderr al log); **sin excepción**
  con el hijo vivo → espera hasta `grace_s`; si termina, normal; si no, `kill()` + `wait()` y
  `ToolError` "el proceso <pid> no se espero: se mato al salir" (nunca se mata en silencio y se
  sigue como si nada).
- Log: cabecera `$ ...` al arrancar y bloque de stderr + `[exit ...]` al terminar, bajo un
  `threading.Lock` por ruta de log resuelta (diccionario de locks protegido por un lock global), en
  modo append, `encoding="utf-8"`, `newline="\n"`.
- Ambas: `TypeError` si `args` no es `list[str]`; `ValueError("args[0] debe ser una ruta absoluta: usa tool_path")`
  si `Path(args[0])` no es absoluto, antes de lanzar nada. (001.2)

#### `src/kcut/commands/__init__.py` — CREAR (docstring de una línea)

#### `src/kcut/commands/doctor.py` — CREAR
Comando `doctor`. En S1.1 usa siempre el modelo `medium`; leer `transcribe.model` del `kcut.toml`
dentro de un proyecto lo agrega S1.2 (`commands/doctor.py — MODIFICAR`). Exit 0 si todos los
requeridos pasan, 1 si no.

#### `src/kcut/doctor/__init__.py` — CREAR (docstring)

#### `src/kcut/doctor/ffmpeg_caps.py` — CREAR (puro)
- `parse_version(text: str) -> tuple[int, int, int] | None`: regex `ffmpeg version n?(\d+)\.(\d+)(?:\.(\d+))?`;
  builds tipo `N-12345-g...` → `None`.
- `parse_filters(text: str) -> frozenset[str]`: líneas de `ffmpeg -filters`, regex
  `^\s[T.][S.][C.]?\s+([A-Za-z0-9_]+)\s+[AVN|]+->[AVN|]+\s` (001.1: acepta las dos maquetas,
  ffmpeg 7.x con tres banderas, p. ej. ` ... aresample         A->A       Audio resampling and converting.`,
  y ffmpeg 8.x con dos, p. ej. ` .. acompressor       A->A       Audio compressor.`; la anterior
  `[T.][S.]C?` solo leía 10 de 42 filtros en un ffmpeg n7.1 real). El mínimo sigue siendo ffmpeg 7.
- `parse_encoders(text: str) -> frozenset[str]`: regex `^\s[VAS][F.][S.][X.][B.][D.]\s+([^\s=]\S*)\s`
  (001.1: el grupo excluye `=`, así las líneas de leyenda ` V..... = Video` no se cuentan como encoders).

#### `src/kcut/doctor/checks.py` — CREAR
- `@dataclass(frozen=True) class CheckResult: id: str; required: bool; ok: bool; detail: str; fix_es: str | None`.
- `REQUIRED_FILTERS = ("zscale", "tonemap", "loudnorm", "ebur128", "sidechaincompress", "afftdn", "blackdetect", "freezedetect", "overlay", "acompressor", "highpass", "asplit", "anullsink", "amix", "aresample", "scale", "fps", "colorbalance", "curves", "vibrance", "vignette", "colorhold")`.
- `OPTIONAL_FILTERS = ("flite", "tonemap_opencl")`. `REQUIRED_ENCODERS = ("libx264", "aac", "pcm_s16le")`.
- `run_all(model_name: str) -> list[CheckResult]` en este orden de ids:
  `python` (requerido: `sys.version_info[:2] == (3, 12)`; fix: "instala con py -3.12; ctranslate2 no soporta 3.14"),
  `ffmpeg` (requerido: encontrado y versión mayor ≥ 7; versión `None` → ok con detalle "versión desconocida"),
  `ffprobe` (requerido), `filters` (requerido: faltantes listados; fix: "usa el build full de gyan.dev"),
  `filters_optional` (no requerido), `encoders` (requerido), `libs` (requerido: importan `numpy`,
  `scipy`, `cv2`, `PIL`, `faster_whisper`, `playwright`; detalle con versiones),
  `whisper_model` (requerido: `faster_whisper.utils.download_model(model_name, local_files_only=True)` no lanza; se llama a través del módulo (`import faster_whisper.utils as fw_utils` y `fw_utils.download_model(...)`) para que el test lo pueda reemplazar; fix: "kcut transcribe --allow-download baja el modelo (~1.5 GB para medium); pide OK antes"),
  `chromium` (requerido: `sync_playwright()` lanza Chromium headless, `set_content("<p>ok</p>")`, cierra, en ≤ 30 s; fix derivado de lo instalado, sin ninguna versión escrita a mano en `checks.py` (001.1): `f"Playwright {importlib.metadata.version('playwright')} necesita su Chromium: \"{sys.executable}\" -m playwright install chromium (descarga: pide OK)"`; la ruta del intérprete va entre comillas porque trae espacios, 001.2),
  `fonts` (requerido: existen los 4 archivos de `assets/fonts` vía `importlib.resources` y `ImageFont.load_default(size=16)` es `FreeTypeFont`),
  `disk` (no requerido: ≥ 5 GB libres en el cwd).

#### `src/kcut/assets/fonts/` — CREAR (copiar, no descargar)
Copiar de `C:\PROYECTOS\MOTIONS DESIGN\_repo-publico\korvex-motion\_studio\fonts\` exactamente:
`inter-latin-600-normal.woff2`, `inter-latin-800-normal.woff2`, `inter-latin-900-normal.woff2`,
`OFL-Inter.txt`. (DS6)

#### `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/e2e/__init__.py` — CREAR (vacíos)

#### `tests/conftest.py` — CREAR
Marcadores con skip limpio: `ffmpeg` (skip si `shutil.which("ffmpeg")` falla y no hay `KCUT_FFMPEG`),
`chromium` (skip si Playwright no encuentra el ejecutable), `whisper` (skip si
`download_model("medium", local_files_only=True)` lanza), `flite` (skip si el filtro no está).
Helper `run_kcut(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]` que
llama `[sys.executable, "-I", "-X", "utf8", "-m", "kcut", *args]` con `encoding="utf-8"`.

### Formato `kcut doctor --json`

```json
{"schema": "kcut.doctor/1", "version": "0.1.0", "ok": true,
 "checks": [
  {"id": "python", "required": true, "ok": true, "detail": "3.12.10", "fix_es": null},
  {"id": "ffmpeg", "required": true, "ok": true, "detail": "8.1.1 C:\\...\\ffmpeg.exe", "fix_es": null},
  {"id": "filters", "required": true, "ok": true, "detail": "22/22", "fix_es": null}
 ]}
```

### Criterios de aceptación S1.1

| # | Tiene que cumplirse | Se comprueba con | Estado |
|---|---|---|---|
| 1 | El paquete instala en un venv 3.12 con el lock | `.venv/Scripts/python.exe -m pip install -e ".[dev]" -c requirements.lock` → exit 0 | ❌ |
| 2 | Versión | `.venv/Scripts/python.exe -I -X utf8 -m kcut --version` → `kcut 0.1.0` | ❌ |
| 3 | Doctor pasa en la máquina de referencia | `.venv/Scripts/python.exe -I -X utf8 -m kcut doctor --json` → exit 0 y `"ok": true` | ❌ |
| 4 | Doctor detecta un filtro faltante | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_doctor_checks.py -q` → exit 0, "passed", sin "failed" | ❌ |
| 5 | Parsers de capacidades de ffmpeg | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_ffmpeg_caps.py -q` → exit 0, sin "failed" | ❌ |
| 6 | CLI: exit codes, `--json` en error, `run` rechaza strings | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_cli.py tests/unit/test_proc.py -q` → exit 0 | ❌ |
| 7 | Lint, formato y tipos | `.venv/Scripts/python.exe -I -X utf8 -m ruff check src tests` y `... -m ruff format --check src tests` y `... -m mypy` → exit 0 los tres | ❌ |
| 8 | Python 3.14 rechazado | `py -3.14 -m pip install --dry-run --no-deps -e .` → falla con "requires a different Python" | ❌ |
| 9 | Parsers con ffmpeg 7.1 y 8.x reales: conjuntos exactos de filtros y encoders; leyendas no parseadas | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_ffmpeg_caps.py -q` → exit 0, sin "failed" | ❌ |
| 10 | `tool_path`: no elige un `ffmpeg.exe` plantado en el cwd, devuelve ruta absoluta, rechaza `.cmd`/`.bat` (env y `which`) con exit 7 | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_tool_path.py -q` → exit 0 | ❌ |
| 11 | Log concurrente: 2 hijos × 200 líneas → 400 líneas + 2 cabeceras `$`; cola de error solo del hijo que falló | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_proc_logging.py -q` → exit 0 | ❌ |
| 12 | Timeout duro con un nieto que retiene el pipe → `ToolError` en < `timeout + grace + 3` s | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_proc_timeout.py -q -ra` → exit 0 (passed, o skipped con motivo si el nieto no se pudo lanzar) | ❌ |
| 13 | `scrub_media_metadata` quita bloques `Metadata:`, claves de ubicación/modelo y coordenadas ISO 6709 | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_scrub.py -q` → exit 0 | ❌ |
| 14 | Modelo válido pero no bajado (`download_model` reemplazado para que lance) → check `whisper_model` en `ok: false` con `local_files_only=True` | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/unit/test_doctor_checks.py::test_whisper_model_not_cached" -q` → `1 passed` | ❌ |
| 15 | Pista de instalación de Chromium derivada de la versión instalada, sin versión escrita a mano | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/unit/test_doctor_checks.py::test_chromium_hint_derived" -q` → `1 passed` | ❌ |
| 16 | `requirements.lock`: raíces fijadas sobre sus pisos, `playwright==1.63.0`, sin dev, pins = versiones instaladas | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_requirements_lock.py -q` → exit 0 | ❌ |
| 17 | El lock resuelve | `.venv/Scripts/python.exe -m pip install --dry-run -e . -c requirements.lock` → exit 0 | ❌ |
| 18 | `run`/`popen` rechazan un `args[0]` no absoluto con `ValueError` antes de lanzar | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/unit/test_proc.py::test_rejects_relative_argv0" -q` → `1 passed` | ❌ |
| 19 | Salir del `with` sin excepción con el hijo vivo → espera `grace_s` y luego `ToolError` (no kill silencioso); hijo que termina a tiempo → sin error; salida por excepción → kill + wait | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_proc.py -q -k child_exit` → exit 0, 3 passed | ❌ |
| 20 | `tool_path` resuelve primero y revisa el sufijo sobre la ruta resuelta: symlink `ffmpeg.exe` → `.cmd` rechazado con exit 7 | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/unit/test_tool_path.py::test_symlink_exe_to_cmd_rejected" -q -ra` → `1 passed` (o `1 skipped` con motivo de privilegio de symlink) | ❌ |
| 21 | La pista de Chromium cita la ruta del intérprete entre comillas | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/unit/test_doctor_checks.py::test_chromium_hint_quoted" -q` → `1 passed` | ❌ |
| 22 | Lock con `Pillow>=12.3` (el test de lock aplica el piso nuevo) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_requirements_lock.py -q` → exit 0 | ❌ |
| 23 | Ningún archivo `.py` de `src/` ni de `tests/` pasa de 300 líneas, y los node ids de los criterios 14 y 15 siguen existiendo | `.venv/Scripts/python.exe -I -X utf8 -c "import pathlib,sys; bad=[str(p) for d in ('src','tests') for p in pathlib.Path(d).rglob('*.py') if len(p.read_text(encoding='utf-8').splitlines())>300]; print(bad); sys.exit(1 if bad else 0)"` → `[]`, exit 0; y `.venv/Scripts/python.exe -I -X utf8 -m pytest --collect-only -q "tests/unit/test_doctor_checks.py::test_whisper_model_not_cached" "tests/unit/test_doctor_checks.py::test_chromium_hint_derived"` → 2 tests | ❌ |

### Tests S1.1
`tests/unit/test_ffmpeg_caps.py` (textos reales recortados de `ffmpeg -filters`/`-encoders`/`-version`
de 8.1.1, de 7.1 y un `N-xxxxx`; igualdad **exacta** de conjuntos; las líneas de leyenda no se
parsean), `tests/unit/test_doctor_checks.py` (monkeypatch de `proc.run` para
simular filtros faltantes → `ok: false` y exit 1), `tests/unit/test_cli.py` (`--version`, subcomando
inexistente → 2, `ProjectError` simulado → 3 con JSON de error), `tests/unit/test_proc.py`
(`run("ffmpeg -version")` → `TypeError`), `tests/integration/test_doctor_live.py` (marcador `ffmpeg`:
`doctor --json` real).
Agregados en 001.1: `tests/unit/test_tool_path.py` (Windows: un `ffmpeg.exe` falso en un cwd
temporal no se elige; resultado absoluto; `KCUT_FFMPEG` apuntando a un `.cmd` o `.bat` →
`MissingDependency` con `exit_code == 7`; `shutil.which` simulado devolviendo un `.bat` → rechazado),
`tests/unit/test_scrub.py` (bloque `Metadata:` real de un MOV con `com.apple.quicktime.location.ISO6709`
y `com.apple.quicktime.model` → no queda ninguna de las dos ni la coordenada; líneas sin metadatos
intactas), `tests/integration/test_proc_logging.py` (dos hijos `sys.executable -c` concurrentes,
200 líneas de stderr cada uno, mismo log → las 400 líneas y las 2 cabeceras `$`; la cola del
`ToolError` de un hijo que falla no trae líneas del otro), `tests/integration/test_proc_timeout.py`
(un hijo que lanza un nieto que hereda su stdout y duerme 60 s; `run(..., timeout_s=1)` →
`ToolError` en < `1 + grace_s + 3` s; skip si el nieto no se pudo lanzar),
`tests/unit/test_doctor_checks.py` (caso `test_whisper_model_not_cached`: `fw_utils.download_model`
reemplazado por una función que lanza → `ok: false`, el fix nombra `--allow-download` y se pasó
`local_files_only=True`; caso `test_chromium_hint_derived`: con la versión de Playwright simulada
el fix la nombra, y `checks.py` no contiene ningún literal que case con la regex `1\.\d+\.\d+`),
`tests/unit/test_requirements_lock.py` (las 6 raíces fijadas con `==` y por encima de su piso de
0.12, comparando tuplas numéricas; `playwright==1.63.0`; ninguna herramienta dev; ninguna línea
`kcut`; cada pin igual a `importlib.metadata.version()` del entorno que corre el test).
Agregados en 001.2: en `tests/unit/test_proc.py`, `test_rejects_relative_argv0` (`run(["ffmpeg",
"-version"])` y `popen(["ffmpeg"], ...)` → `ValueError` sin lanzar proceso) y `test_child_exit_*`,
que **reemplazan** el test que fijaba el kill silencioso: (a) `with popen([sys.executable, "-c",
"import time; time.sleep(30)"], ..., grace_s=0.5): pass` → `ToolError` y el hijo ya no vive;
(b) un hijo que termina en 0.1 s dentro de `grace_s=2` → sin error; (c) una excepción dentro del
`with` → sale esa excepción, el hijo muerto. En `tests/unit/test_tool_path.py`,
`test_symlink_exe_to_cmd_rejected` (`KCUT_FFMPEG` = symlink `ffmpeg.exe` → `real.cmd` →
`MissingDependency` con exit 7; skip con motivo si `os.symlink` lanza `OSError` por falta de
privilegio). En `tests/unit/test_doctor_checks.py`, `test_chromium_hint_quoted` (el fix contiene
`f'"{sys.executable}" -m playwright install chromium'`). `test_requirements_lock.py` usa el piso
`Pillow>=12.3`.

---

## S1.2 — `kcut new` + `kcut ingest`

### Archivos

#### `src/kcut/jsonio.py` — CREAR
`read_json(path: Path) -> Any`, `write_json_atomic(path: Path, obj: object) -> None`,
`write_text_atomic(path: Path, text: str) -> None` (0.9).

#### `src/kcut/schema_util.py` — CREAR (puro)
`class SchemaError(ProjectError)` con `path: str`. Helpers: `obj(v, path) -> dict[str, Any]`,
`only_keys(d, allowed: set[str], path) -> None`, `req_int(d, key, path, lo=None, hi=None) -> int`
(rechaza `bool` y `float`), `opt_int`, `req_float` (acepta int y float, rechaza bool/NaN), `opt_float`,
`req_str(d, key, path, max_len=None)`, `opt_str`, `req_bool`, `req_list`, `hex_color(v, path) -> str`
(normaliza a mayúsculas `#RRGGBB`), `one_of(v, choices, path)`.
Mensajes en español con la ruta: `spans[3].zoom: debe estar entre 1.0 y 3.0 (vino 3.4)`.

#### `src/kcut/timebase.py` — CREAR (0.6)

#### `src/kcut/paths.py` — CREAR
- `@dataclass(frozen=True) class Layout` con todas las rutas de 0.3 a partir de `root`
  (`crudo`, `recursos`, `manifest`, `edit`, `salida`, `qa`, `cache`, `inventory`, `proxy`, `wav16`,
  `wav48`, `mezz`, `transcripts`, `view`, `frames`, `build`, `storyboard_cache`, `logs`, `locks`),
  y `build_dir(version: int) -> Path`, `qa_dir(version: int) -> Path`,
  `all_paths() -> tuple[Path, ...]` (todas las carpetas del layout: `crudo/`, `recursos/`, `edit/`,
  `salida/`, `qa/`, `.kcut/` y cada subcarpeta de `.kcut/`) (001.6).
- `find_project(start: Path) -> Path` (sube hasta `kcut.toml`; `ProjectError` si no).
- `resolve_in_project(root: Path, rel: str) -> Path`: reglas 0.10.7; resultado resuelto debe
  quedar dentro de `root.resolve()` (comparación con `normcase`); si no → `ProjectError`.
- `to_rel(root: Path, p: Path) -> str` (POSIX relativo).
- `inside_kcut_repo(p: Path) -> bool`: algún ancestro contiene `src/kcut/__init__.py`.

#### `src/kcut/project.py` — CREAR
`@dataclass class Project: root: Path; config: ProjectConfig; layout: Layout` y
`open_project(explicit: str | None) -> Project` (usa `--project` o `find_project(Path.cwd())`).
(001.4) Rechaza el proyecto con `ProjectError` si `.kcut` o cualquier carpeta de `Layout` que exista
resuelve fuera de la raíz del proyecto (junction o symlink): se comprueba con `Path.resolve()` y
`normcase` antes de devolver el `Project`.
(001.6) La comprobación vive en `check_layout_inside(root: Path, layout: Layout) -> None`: para cada
ruta de `layout.all_paths()` que exista, `ProjectError` si es symlink o junction
(`os.path.islink` / `os.path.isjunction`) **o** si resuelve fuera de la raíz. Así se rechazan también
los enlaces internos: `.kcut → crudo/`, `.kcut → edit/`, `.kcut/logs → crudo/`. La llaman
`open_project` y `kcut new` (cuando la carpeta ya existe), antes de escribir nada.
`load_inventory(project) -> Inventory` → `ProjectError` "corre kcut ingest" si falta.

#### `src/kcut/config/model.py` — CREAR
Dataclasses congeladas: `ProjectSection(name, language, created)`, `OutputSection(preset, fps, w, h, safe_top_px, safe_bottom_px)`,
`BrandSection(accent, accent2, dark, light)`, `TranscribeSection(model, compute_type, beam_size, cpu_threads, fillers, prompt_extra)`,
`AnalysisSection(silence_db, min_silence_ms, phrase_pause_ms, long_pause_ms, low_prob)`,
`SyncSection(master, min_score, min_ratio, max_drift_ms, min_refine_corr, manual: Mapping[str, int])` (`min_refine_corr` desde 001.6),
`CaptionsSection(enabled, uppercase, max_words, max_chars, y, font_px, color, active_color, stroke_color)`,
`VoiceChain(highpass_hz, denoise_nr, denoise_nf, comp_threshold_db, comp_ratio)`,
`AudioSection(voice_lufs, target_lufs, target_tp, voice: VoiceChain)`,
`QaSection(min_transcript_match, lufs_tolerance, max_tp, max_av_delta_ms)`,
`StoryboardSection(min_beat_ms)`, `IngestSection(warn_duration_h, max_duration_h)` (001.4),
`ProjectConfig(...)` con todas + `glossary: tuple[str, ...]`.
`preset "9:16"` → `w=1080, h=1920`; `"16:9"` → `w=1920, h=1080`.

#### `src/kcut/config/load.py` — CREAR
`load_config(path: Path) -> ProjectConfig` con `tomllib`. Clave o sección desconocida → `ProjectError`
nombrándola. Rangos (fuera de rango → `ProjectError`):

| Campo | Tipo | Default | Rango / regla |
|---|---|---|---|
| `project.name` | str | nombre de carpeta | 1–80; sin caracteres de las categorías Unicode `Cc`, `Cf`, `Zl`, `Zp` (incluye U+0085, U+2028, U+2029, U+202E, U+200B) (001.4) |
| `project.language` | str | `"es"` | `^[a-z]{2}$` |
| `project.created` | str | fecha de `new` | `YYYY-MM-DD` |
| `output.preset` | str | `"9:16"` | `"9:16"` o `"16:9"` |
| `output.fps` | int | 30 | `ALLOWED_FPS` |
| `output.safe_top_px` / `safe_bottom_px` | int | 250 / 500 (9:16), 60 / 120 (16:9) | 0–600 |
| `brand.accent/accent2/dark/light` | hex | `#E5FF1F` `#2FA8FF` `#0B0B0E` `#FFFFFF` | hex |
| `glossary.terms` | list[str] | `[]` | ≤ 200, cada uno 1–40; sin `Cc`/`Cf`/`Zl`/`Zp` (001.6, se implementa en S1.3) |
| `transcribe.model` | str | `"medium"` | `tiny base small medium large-v3` |
| `transcribe.compute_type` | str | `"int8"` | `int8 int8_float32 float32` |
| `transcribe.beam_size` | int | 5 | 1–10 |
| `transcribe.cpu_threads` | int | 0 (= `os.cpu_count()`) | 0–64 |
| `transcribe.fillers` | list[str] | ver plantilla | ≤ 50, cada uno 1–40; sin `Cc`/`Cf`/`Zl`/`Zp` (001.6, S1.3) |
| `transcribe.prompt_extra` | str | `""` | ≤ 400; sin `Cc`/`Cf`/`Zl`/`Zp` (001.6, S1.3) |
| `analysis.silence_db` | float | −42.0 | −70 a −20 |
| `analysis.min_silence_ms` | int | 250 | 50–2000 |
| `analysis.phrase_pause_ms` | int | 300 | 100–3000 |
| `analysis.long_pause_ms` | int | 700 | ≥ phrase_pause_ms, ≤ 10000 |
| `analysis.low_prob` | float | 0.5 | 0–1 |
| `sync.master` | str | `""` | `""` o id de clip |
| `sync.min_score` / `min_ratio` / `max_drift_ms` | float/float/int | 0.35 / 1.5 / 20 | 0–1 / ≥ 1 / 1–1000 |
| `sync.min_refine_corr` | float | 0.1 | 0–1 (001.6) |
| `sync.manual` | tabla id → int ms | vacía | ids `^[a-z][0-9]+$` |
| `captions.enabled` / `uppercase` | bool | true / true | — |
| `captions.max_words` / `max_chars` | int | 3 / 18 | 1–6 / 6–40 |
| `captions.y` | float | 0.617 | 0–1 (centro vertical del bloque) |
| `captions.font_px` | int | 76 | 24–200 |
| `captions.color` | hex | `#FFFFFF` | hex |
| `captions.active_color` / `stroke_color` | hex o `""` | `""` (= `brand.accent2` / `brand.dark`) | — |
| `audio.voice_lufs` / `target_lufs` / `target_tp` | float | −16.0 / −14.0 / −1.5 | −30..−10 / −24..−9 / −3..−0.5 |
| `audio.voice.highpass_hz` | int | 80 | 20–300 |
| `audio.voice.denoise_nr` / `denoise_nf` | float | 10 / −40 | 0–40 / −80..−20 |
| `audio.voice.comp_threshold_db` / `comp_ratio` | float | −18 / 3.0 | −40..0 / 1–20 |
| `qa.min_transcript_match` / `lufs_tolerance` / `max_tp` / `max_av_delta_ms` | float/float/float/int | 0.80 / 1.0 / −1.0 / 25 | 0–1 / 0.1–3 / −6..0 / 0–200 |
| `storyboard.min_beat_ms` | int | 500 | 0–5000 |
| `ingest.warn_duration_h` / `max_duration_h` | float (acepta int) | 3 / 12 | 0.1–48 / ≥ `warn_duration_h`, ≤ 48 (001.4) |

Toda regla con regex de esta tabla se aplica con `re.fullmatch` (así un valor con `\n` al final no
pasa). (001.4)

#### `src/kcut/config/template.py` — CREAR
`render_template(name: str, preset: str, fps: int, language: str, created: str) -> str`. Los
strings se escriben con `json.dumps(s, ensure_ascii=False)` (escape compatible con TOML). Salida
exacta (comentarios en español), para `9:16`:

```toml
# kcut.toml - configuracion de este video
[project]
name = "piloto-01"
language = "es"          # idioma principal (subtitulos, muletillas); Whisper detecta por clip
created = "2026-10-16"

[output]
preset = "9:16"          # "9:16" = 1080x1920 · "16:9" = 1920x1080
fps = 30                 # 24, 25, 30, 48, 50 o 60
safe_top_px = 250
safe_bottom_px = 500

[brand]
accent = "#E5FF1F"
accent2 = "#2FA8FF"      # palabra activa de los subtitulos
dark = "#0B0B0E"
light = "#FFFFFF"

[glossary]
terms = []

[transcribe]
model = "medium"
compute_type = "int8"
beam_size = 5
cpu_threads = 0
fillers = ["eh", "ehh", "em", "emm", "mmm", "este", "o sea", "pues", "bueno", "entonces"]
prompt_extra = ""

[analysis]
silence_db = -42.0
min_silence_ms = 250
phrase_pause_ms = 300
long_pause_ms = 700
low_prob = 0.5

[sync]
master = ""
min_score = 0.35
min_ratio = 1.5
max_drift_ms = 20
min_refine_corr = 0.1

[sync.manual]

[captions]
enabled = true
uppercase = true
max_words = 3
max_chars = 18
y = 0.617
font_px = 76
color = "#FFFFFF"
active_color = ""
stroke_color = ""

[audio]
voice_lufs = -16.0
target_lufs = -14.0
target_tp = -1.5

[audio.voice]
highpass_hz = 80
denoise_nr = 10.0
denoise_nf = -40.0
comp_threshold_db = -18.0
comp_ratio = 3.0

[qa]
min_transcript_match = 0.80
lufs_tolerance = 1.0
max_tp = -1.0
max_av_delta_ms = 25

[storyboard]
min_beat_ms = 500

[ingest]
warn_duration_h = 3
max_duration_h = 12
```
Para `16:9`: `safe_top_px = 60`, `safe_bottom_px = 120`. Para `--lang en`: `fillers = ["uh", "um", "uhm", "er", "hmm"]`.

#### `src/kcut/recursos/manifest.py` — CREAR (D7, DS9)
Formato `recursos/recursos.json`:

```json
{"schema": "kcut.recursos/1",
 "items": [
  {"file": "recursos/logos/claude-mascota.webp", "kind": "imagen", "origin": "descargado",
   "source_url": "https://ejemplo.com/kit-de-marca", "license": "kit oficial de marca",
   "license_url": null, "obtained": "2026-10-15", "approved_by": "Yedin",
   "approved_on": "2026-10-15", "notes": "mascota 3D, fondo quitado"}
 ]}
```
Reglas: `file` relativo al proyecto, debe empezar con `recursos/` y existir; `kind` ∈
`imagen musica sfx video fuente otro`; `origin` ∈ `propio descargado generado cliente`;
`source_url` obligatorio no vacío si `origin == "descargado"`; `license` no vacío; `obtained`
`YYYY-MM-DD`; `approved_by` string (puede venir vacío en el archivo, pero entonces no se puede usar).
Funciones: `load_manifest(project) -> list[ResourceItem]`, `validate_manifest(project) -> list[str]`
(errores en español), `require_approved(project, rel: str) -> ResourceItem` → `GateError` (5) si el
archivo no está en el manifiesto o `approved_by` está vacío.

#### `src/kcut/ff/color.py` — CREAR (puro)
`HDR_TO_SDR: str` (cadena de 0.7), `CHAIN_VERSION = "tm2"` (001.4: sube por el cambio de etiquetas),
`TAGS_BT709 = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"`,
`is_hdr(transfer: str | None) -> Literal["hlg", "pq"] | None` (`arib-std-b67` → hlg, `smpte2084` → pq),
`sdr_scale(w: int, h: int, in_matrix: str, in_range: str) -> str` →
`scale=W:H:flags=lanczos:in_color_matrix=M:in_range=R:out_color_matrix=bt709:out_range=tv,format=yuv420p`
donde `M` = `bt601` si `color_space` ∈ {`smpte170m`, `bt470bg`}, si no `bt709`; `R` = `pc` si
`color_range == "pc"`, si no `tv`.
`video_chain(info: VideoInfo, w: int, h: int, fps: int) -> str`: SDR → `fps=F,` + `sdr_scale` +
`,` + `TAGS_BT709`; HDR → `fps=F,scale=W:H:flags=lanczos,` + `HDR_TO_SDR` + `,` + `TAGS_BT709`.
(001.4, deuda 16 confirmada por el verificador: sin `setparams` los proxies SDR salían sin las
etiquetas de color.)

#### `src/kcut/ff/args.py` — CREAR (puro, cada uno devuelve `list[str]`)
Todos los de ffmpeg empiezan con `-hide_banner -nostdin -loglevel error`; `wav_args`, `proxy_args`
y `mezz_args` llevan además `-map_metadata -1` antes de la salida (los intermedios no heredan
ubicación ni modelo del equipo). (001.1)
- `ffprobe_args(ffprobe: Path, src: Path) -> list[str]`: `-v error -print_format json -show_format -show_streams`.
- `wav_args(ffmpeg, src, dst, sr: Literal[16000, 48000]) -> list[str]`:
  `-i src -map 0:a:0 -vn -ac 1 -af aresample=SR:resampler=soxr:first_pts=0 -c:a pcm_s16le dst`.
- `proxy_args(ffmpeg, src, dst, chain: str, fps: int) -> list[str]`:
  `-i src -map 0:v:0 -an -vf CHAIN -c:v libx264 -preset veryfast -crf 23 -g F -keyint_min F -pix_fmt yuv420p` + flags de color 0.7 + `-movflags +faststart dst`.
- `mezz_args(ffmpeg, src, dst, chain, fps, start_f: int, count_f: int) -> list[str]`:
  `-ss fnum(start_f/fps) -i src -map 0:v:0 -an -vf CHAIN -frames:v COUNT -c:v libx264 -preset veryfast -crf 14 -g F -keyint_min F -pix_fmt yuv420p` + flags de color + `dst`.

#### `src/kcut/audio/wavio.py` — CREAR
`read_wav_s16_mono(path) -> tuple[NDArray[np.float32], int]` (`wave`; ≠ mono/16 bit → `ProjectError`),
`write_wav_s16_mono(path, x, sr) -> None` (clip a [−1, 1]),
`read_f32(path) -> NDArray[np.float32]`, `write_f32(path, x) -> None` (float32 little-endian crudo, DS4).

#### `src/kcut/ingest/probe.py` — CREAR (puro sobre el JSON de ffprobe)
`@dataclass VideoInfo(codec, w, h, display_w, display_h, rotation, fps_r, fps_avg, vfr, pix_fmt, bit_depth, color_transfer, color_primaries, color_space, color_range, hdr, dolby_vision, dv_profile, start_ms)`,
`@dataclass AudioInfo(codec, sample_rate, channels, start_ms, streams)`,
`@dataclass MediaInfo(duration_ms, size_bytes, format_name, video: VideoInfo | None, audio: AudioInfo | None)`,
`parse_ffprobe(data: Mapping[str, Any]) -> MediaInfo`. Reglas:
- `rotation` del side data `Display Matrix` (o `tags.rotate`); si `abs(rotation) in (90, 270)` se
  intercambian `display_w/h`.
- `vfr = True` si `r_frame_rate` y `avg_frame_rate` (fracciones) difieren > 0.1 %.
- `dolby_vision = True` si hay side data `DOVI configuration record`; `dv_profile` de ese bloque.
- `bit_depth` de `bits_per_raw_sample` o del `pix_fmt` (`10le` → 10, si no 8).
- `start_ms` = `round((stream.start_time - format.start_time) * 1000)`.
- Stream de video con `codec_name` ∈ {`png`, `mjpeg`, `webp`, `bmp`, `tiff`, `gif`} y duración < 0.5 s
  no cuenta como video (portada adjunta).
- Solo se conservan los campos de los dataclasses; de `tags` solo se lee `rotate`. El JSON crudo de
  ffprobe nunca se escribe a disco, a `--json`, a mensajes ni al log (trae `location`, `make`,
  `model`). (001.1)

#### `src/kcut/ingest/naming.py` — CREAR (puro)
`slugify(name: str) -> str` (NFKD, sin marcas, minúsculas, todo lo que no sea `[a-z0-9]` → `-`,
colapsar, recortar `-`, máx. 40; vacío → `"clip"`), `qhash(path: Path) -> str`
(`"sha256:" + sha256(size en 8 bytes LE + primeros 8 MiB + últimos 8 MiB)`).

#### `src/kcut/ingest/classify.py` — CREAR (puro)
- `DOC_EXT = {.txt .md .pdf .doc .docx .rtf .odt}`, `IMG_EXT = {.png .jpg .jpeg .webp .bmp .tif .tiff}`.
- `classify(ext: str, info: MediaInfo | None, audio_peak_dbfs: float | None) -> ClipClass` en este orden:
  extensión de doc → `doc`; extensión de imagen → `imagen`; `info is None` → `desconocido`;
  video + audio con pico > −60 dBFS → `video_voz`; video (con o sin audio) → `video_mudo`;
  solo audio → `audio`.
- Prefijos de id: `video_voz` → `a`, `video_mudo` → `b`, `audio` → `s`, `imagen` → `i`, `doc` → `d`,
  `desconocido` → `u`.
- `assign_ids(files: list[NewFile], previous: Inventory | None) -> tuple[dict[str, str], dict[str, int]]`
  (001.4: **los ids nunca se reusan**): cada archivo busca su clip previo primero por (`qhash`, `file`)
  y luego solo por `qhash`; en ambos casos el prefijo del id previo debe coincidir con la clase
  actual, si no se trata como nuevo. Los nuevos reciben `id_high[prefijo] + 1` (en orden de ruta
  relativa sin distinguir mayúsculas), y `id_high` se actualiza. Un id que desaparece queda retirado
  para siempre. Ej.: `a1`, `a2` (cam2); se re-exporta cam2 (otro `qhash`) → `a3`; luego entra
  cam3 → `a4`; nunca vuelve `a2`.
  (001.6) `ID_HIGH_MAX = 999_998`: si un prefijo llega a ese tope, `ProjectError` en vez de emitir un
  id que el validador (`^[a-z][0-9]{1,6}$`) rechazaría.

#### `src/kcut/ingest/inventory.py` — CREAR (dataclasses en `ingest/inventory_model.py`, 001.4)
Dataclasses + `load_inventory(path) -> Inventory`, `save_inventory(path, inv) -> None`.
Validación al cargar (001.4, `_clip` con `re.fullmatch` en todo): `id` `^[a-z][0-9]{1,6}$` con el
prefijo que corresponde a su `class`; `slug` `^[a-z0-9-]{1,40}$`; `file` bajo `crudo/` y que pase
`resolve_in_project`; `work.proxy` bajo `.kcut/proxy/` y `work.wav16` bajo `.kcut/wav16/` (ambos
resueltos; `null` permitido); `id_high` con claves de prefijo válidas y valores ≥ al número de
cualquier id presente. Si algo falla, el inventario previo se trata como **ausente** (re-ingest
desde cero) con el aviso `inventory_invalid`; nunca se confía en él. Formato `.kcut/inventory.json`:

```json
{"schema": "kcut.inventory/1", "generated": "2026-10-16T10:22:31", "fps": 30,
 "id_high": {"a": 2, "i": 1, "d": 1},
 "clips": [
  {"id": "a1", "file": "crudo/crudo 1.MOV", "slug": "crudo-1", "class": "video_voz",
   "qhash": "sha256:9f2c...", "size_bytes": 1534023111, "duration_ms": 131233, "frames": 3936,
   "video": {"codec": "hevc", "w": 3840, "h": 2160, "display_w": 2160, "display_h": 3840,
             "rotation": -90, "fps_r": "60/1", "fps_avg": "35460/593", "vfr": true,
             "pix_fmt": "yuv420p10le", "bit_depth": 10, "color_transfer": "arib-std-b67",
             "color_primaries": "bt2020", "color_space": "bt2020nc", "color_range": "tv",
             "hdr": "hlg", "dolby_vision": true, "dv_profile": 8, "start_ms": 0},
   "audio": {"codec": "aac", "sample_rate": 44100, "channels": 2, "start_ms": 0, "streams": 1,
             "peak_dbfs": -3.2, "silent": false},
   "work": {"proxy": ".kcut/proxy/a1_crudo-1.mp4", "wav16": ".kcut/wav16/a1_crudo-1.wav",
            "proxy_w": 540, "proxy_h": 960},
   "warnings": ["vfr", "hdr", "dolby_vision", "rotation"]},
  {"id": "i1", "file": "crudo/foto.png", "slug": "foto", "class": "imagen", "qhash": "sha256:...",
   "size_bytes": 20311, "image": {"w": 800, "h": 600, "has_alpha": true}, "warnings": []},
  {"id": "d1", "file": "crudo/brief.txt", "slug": "brief", "class": "doc", "qhash": "sha256:...",
   "size_bytes": 512, "warnings": []}
 ],
 "sync": {"master": "a1",
  "members": [{"id": "a2", "offset_ms": 4722, "score": 0.91, "second": 0.31, "ratio": 2.94,
               "drift_ms": 1, "drift_windows": 9, "method": "envelope+raw"}],
  "rejected": [{"id": "s1", "score": 0.12, "ratio": 1.1, "reason": "pico de correlacion bajo"}]}}
```
- `frames = ms_to_f_floor(duration_ms, fps)` para clips con video o audio; ausente en imagen/doc.
- `offset_ms`: el `t=0` del miembro cae en `t=offset_ms` del maestro (positivo = el miembro empezó
  a grabar después). `method` ∈ `envelope+raw`, `manual`.
- `id_high`: por prefijo, el número más alto que se haya emitido nunca (001.4).
- Códigos de aviso: `vfr hdr dolby_vision dv_profile_unsupported rotation multi_audio silent_audio av_start_offset sync_rejected drift probe_failed unknown_type`,
  y desde 001.4: `wav16_failed` (ffprobe bien pero la extracción del wav16 falló), `long_duration`
  (más de `warn_duration_h`), `too_long` (más de `max_duration_h`: el clip se registra pero no se
  procesa), `skipped_link` (carpeta junction/symlink que no se recorrió), `inventory_invalid`,
  `cache_rebuilt` (un archivo de caché corrupto se reconstruyó).
  Desde 001.6: `sync_weak_refine` (la correlación del refinado quedó bajo `min_refine_corr`: el par se
  rechaza y va a `sync.rejected` con `refine_corr`). Desde 001.7: `sync_ambiguous` (clip corto con
  dos desfases posibles; el par se rechaza, ver 001.7 punto 1). Un archivo que no se pudo leer para el `qhash`
  no recibe clip ni id: va a la lista de avisos del ingest como
  `{"code": "probe_failed", "file": "crudo/x.mov", "message_es": "..."}`.
  `dv_profile_unsupported` cuando `dv_profile == 5` (sin capa base compatible: colores incorrectos, F2).
  `av_start_offset` cuando `abs(video.start_ms - audio.start_ms) > 1000 // fps`.

#### `src/kcut/ingest/sync.py` — CREAR (puro numpy/scipy; técnica de `piloto/sync.py`)
- `envelope(x, sr, hop_ms=5) -> NDArray[np.float32]`: RMS por bloque, `log1p(rms*100)`, z-normalizado.
- `coarse_offset(master_env, member_env, hop_ms) -> CoarseResult(offset_ms: float, score: float, second: float, ratio: float)`:
  `fftconvolve(m, b[::-1], "full")`; para cada lag `k` (en muestras de envolvente, `lag = k - (len(b) - 1)`)
  el valor normalizado es `corr[k] / overlap(lag)`, con `overlap(lag) = min(len(m), lag + len(b)) - max(0, lag)`
  (001.4: se normaliza por el **solape en ese lag**, no por `min(len)`, para no castigar solapes
  parciales). Se ignoran los lags con solape menor que `min(10 s, 0.75 × duración del más corto)` (001.5).
  `score` = máximo normalizado, `offset_ms = lag*hop_ms` de ese máximo, `second` = máximo
  normalizado fuera de ±2000 ms del pico, `ratio = score/second` (`inf` si `second <= 0`).
  `min_score` y `min_ratio` se aplican igual que antes.
- `refine_offset(master, member, sr, coarse_ms, search_ms=50, step=4, window_s=60.0) -> tuple[float, float]`:
  ventana de hasta 60 s en el centro del solape; correlación normalizada (producto punto / normas)
  para cada desplazamiento en `coarse ± search_ms` con paso `step` muestras; devuelve el mejor
  `(offset_ms, corr)`.
- `drift(master, member, sr, offset_ms, window_s=10, hop_s=10, search_ms=20, step=2, min_corr=0.3) -> DriftResult(drift_ms: int | None, windows: int)`:
  si el solape < 30 s → `drift_ms=None`; si no, offset refinado por ventana; `drift_ms = round(max - min)`
  de las ventanas con corr ≥ `min_corr`.
- `sync_pair(master_wav: Path, member_wav: Path, cfg: SyncSection) -> SyncResult` (acepta si
  `score >= min_score` y `ratio >= min_ratio`; `offset_ms = round(refinado)`; aviso `drift` si
  `drift_ms > max_drift_ms`).
  (001.6, decisión del dueño) Después de `refine_offset`, si su correlación es menor que
  `min_refine_corr` (default 0.1), el par se **rechaza** con motivo y aviso `sync_weak_refine`
  aunque `score` y `ratio` pasen. Calibración medida: offsets equivocados en clips cortos dan
  0.012–0.019, el correcto 0.99, y el piloto real (dos iPhones) 0.489. El piso de solape de 0.75
  (001.5) se mantiene. Aceptados y rechazados guardan `refine_corr` en el inventario.
  (001.7) En clips cortos, donde manda el piso de 0.75 y no el de 10 s, se calcula además el mejor
  lag con piso 0.5; si los dos difieren en más de 2 s, el par se rechaza con `sync_ambiguous`
  (detalle en 001.7 punto 1).

#### `src/kcut/ingest/workfiles.py` — CREAR
`ensure_wav16(project, clip) -> Path`, `ensure_wav48(project, clip) -> Path` (mismo esquema en
`.kcut/wav48/`, se usa desde S1.5), `ensure_proxy(project, clip) -> Path`. Cada archivo lleva un
sidecar `<archivo>.json` con `{"qhash": ..., "params": ...}`; si no coincide, se regenera.
Proxy: lado largo 960, lado corto `2*round(corto*960/largo/2)`, `video_chain` de `ff/color.py`.
(001.4) El sidecar del proxy lleva una versión de parámetros que sube con este parche (además de
`CHAIN_VERSION = "tm2"`), así todo proxy cacheado de antes se regenera.
(001.4) `_assert_in_cache(project, path) -> Path`: resuelve `path` y exige que quede dentro de
`layout.cache` (comparación con `normcase`); si no → `ProjectError`. Se llama al **inicio** de toda
función que escribe, mueve o borra (`_build`, `adopt` con su origen **y** su destino, `discard`),
antes de tocar el disco. Un wav16 previo solo se reutiliza si su ruta resuelve bajo `.kcut/wav16/`.
(001.6) `_assert_in_cache` además exige `layout.cache.resolve() == (root / ".kcut").resolve()` y que el
destino no quede bajo `crudo/`. `_copy(src, dst)` vuelve sin hacer nada si
`src.resolve() == dst.resolve()` (nunca borra el origen). Los trabajos de wav16 y proxy llevan
`-t <max_duration_h*3600 + 60>` (no se confía en la duración declarada) y, después de construir el
wav16, `long_duration`/`too_long` se recalculan con su largo real (`nframes / 16000`); si queda
`too_long`, ese wav16 se borra (por `discard`, con `_assert_in_cache`).
(001.4) Pico del wav16 calculado por bloques (`wave.readframes` de a 1 048 576 frames), sin cargar el
archivo entero. Cada trabajo de ffmpeg lleva `timeout_s = 10 × duración_s + 60` de su fuente;
ffprobe, `timeout_s = 60`.
Todo tamaño de proxy y mezzanine se calcula sobre `display_w/display_h` (ffmpeg autorrota al
decodificar, así que el `scale` recibe el frame ya derecho).

#### `src/kcut/ingest/run.py` — CREAR
`run_ingest(project, *, make_proxies: bool, resync: bool, progress) -> Inventory`. Pasos: (1) escanea
`crudo/` recursivo, sin archivos/carpetas que empiezan con `.`; (2) `qhash` + ffprobe (falla →
`desconocido` + aviso `probe_failed`, sigue); (3) wav16 de todo clip con audio, pico en dBFS con
numpy; (4) clasifica e asigna ids; imágenes: Pillow `w`, `h`, `has_alpha` (`"A"` en el modo o
`"transparency"` en `info`); (5) proxies de clips con video salvo `--no-proxy`; (6) sincronía:
grupo = todos los `a` y `s` no silenciosos; maestro = `sync.master` o el `a` de id más bajo; cada
miembro contra el maestro (los manuales de `sync.manual` se usan tal cual, `method: "manual"`); con
`--resync` se recalcula aunque el `qhash` no cambie, si no se reutiliza el resultado previo;
(7) guarda el inventario. Si un proxy falla: guarda el inventario con `proxy: null` y sale con 4.
**No** genera mezzanines.
Reglas agregadas en 001.4 (la etapa de sincronía vive en `ingest/sync_stage.py`):
- Inventario previo inválido (ver `inventory.py`) → se ignora, aviso `inventory_invalid`.
- `os.walk` poda las carpetas que son junction o symlink (`os.path.isjunction` / `os.path.islink`)
  con aviso `skipped_link`, y deduplica por ruta relativa.
- Duración > `warn_duration_h` → aviso `long_duration`; > `max_duration_h` → aviso `too_long`, el
  clip queda en el inventario con su clase y sin wav16, proxy ni sincronía.
- wav16 que falla después de un ffprobe bueno → el clip conserva la clase que le da el probe (p. ej.
  `video_mudo` si tiene video), su proxy y sus `frames`; aviso `wav16_failed` (no `probe_failed`).
- Un `ProjectError` de `proxy_size` (tamaño declarado 0) marca el clip `probe_failed` y sigue.
- (001.6) `ingest/scan.py`: un `OSError` al calcular el `qhash` de un archivo lo marca
  `probe_failed` (sin clip ni id estable; el aviso nombra el archivo) y el ingest sigue con los demás.

#### `src/kcut/commands/new.py` — CREAR
`kcut new <path> [--name N] [--preset 9:16|16:9] [--fps F] [--lang LL]`:
- `inside_kcut_repo(path)` → `ProjectError` "los proyectos de video no van dentro del repo de kcut" (DS14).
- Si `<path>/kcut.toml` existe → `ProjectError` "ya es un proyecto". La carpeta puede existir con
  archivos: no se tocan; se avisa "hay N archivos fuera de crudo/; muévelos a crudo/".
- (001.6) Si la carpeta ya existe: llama `check_layout_inside` antes de escribir nada, y su recorrido
  poda junctions y symlinks. El aviso de "archivos fuera de crudo/" **no** cuenta los archivos del
  propio layout (`kcut.toml`, todo lo de `edit/`, `recursos/`, `salida/`, `qa/` y `.kcut/`): nunca se
  le dice al usuario que mueva `estrategia.md` u otro archivo del gate a `crudo/`.
- (001.4) Nombre: `--name` con caracteres de las categorías Unicode `Cc`, `Cf`, `Zl`, `Zp` o con más
  de 80 caracteres → `UsageError` (2). Nombre por defecto (de la carpeta): se le quitan esos
  caracteres y se recorta a 80; si queda vacío, `"proyecto"`.
- (001.4) Orden sin proyectos a medias: (1) **valida primero** todas las rutas de 0.3: cada carpeta
  debe no existir o ser una carpeta de verdad (un archivo llamado `crudo` → `ProjectError` sin crear
  nada); (2) crea las carpetas que falten; (3) crea `recursos/recursos.json`, `edit/versiones.md` y
  `edit/estrategia.md` **solo si no existen** (nunca se sobrescriben: una `estrategia.md` con
  `aprobado: si` queda intacta); (4) escribe `kcut.toml` **al final**. `created` lista solo lo que
  de verdad se creó.
- Contenido de los archivos que crea: carpetas de 0.3, `kcut.toml` (plantilla), `recursos/recursos.json`
  (`items: []`), `edit/versiones.md` (`# Versiones - <name>\n`), `edit/estrategia.md`:

```
---
video: <name>
formato: <preset> · <w>x<h> · <fps> fps
aprobado: no
aprobado_por:
---
# Estrategia de corte - <name>
```
- `--json` → `{"ok": true, "project": "<ruta absoluta>", "created": ["kcut.toml", "crudo/", ...]}`.

#### `src/kcut/commands/ingest.py` — CREAR
`--json` → `{"ok": true, "inventory": ".kcut/inventory.json", "clips": 5, "by_class": {"video_voz": 2, ...}, "sync": {...}, "warnings": [...], "elapsed_s": 12.4}`.

#### `src/kcut/cli.py` — MODIFICAR
- Agregar `"kcut.commands.new"`, `"kcut.commands.ingest"` a `COMMAND_MODULES`.
- (001.1) `InternalError` (incluye toda excepción no prevista convertida en `InternalError`): si
  hay proyecto (`--project` o subiendo desde el cwd; buscarlo aquí no lanza si no existe), el
  traceback completo va a `.kcut/logs/<comando>-<YYYYmmdd-HHMMSS>-<pid>.log` y el mensaje corto dice la
  ruta de ese log; sin proyecto, el traceback va a stderr solo con `-v`. El traceback nunca entra al
  JSON de `--json`.
- (001.4) El log es **el mismo** que usan los hijos de esa corrida: `cli.main` decide una sola ruta
  de log por invocación y se la pasa al comando; el traceback se **agrega** (modo append, bajo el
  mismo lock por ruta de 0.11), nunca trunca. El mensaje corto que va a stderr o a `--json` pasa
  por `scrub_media_metadata`.

#### `src/kcut/commands/doctor.py` — MODIFICAR (001.1)
Dentro de un proyecto (`--project` o subiendo desde el cwd) usa `transcribe.model` de `kcut.toml`.
Si `kcut.toml` no carga, usa `medium` y agrega el check no requerido `project_config` con
`ok: false` y el error. Fuera de un proyecto, `medium`.

#### `src/kcut/doctor/checks.py` — MODIFICAR
Agregar después de `encoders`: `tonemap_chain` (requerido: ffmpeg corre `HDR_TO_SDR` sobre
`-f lavfi -i testsrc2=s=64x64:d=0.04,setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc,format=yuv420p10le -frames:v 1 -f null -`
con exit 0) y `soxr` (requerido: `-f lavfi -i sine=d=0.1 -af aresample=16000:resampler=soxr -f null -` exit 0).

#### `tests/fixtures/__init__.py` — CREAR (vacío)

#### `tests/fixtures/synth_media.py` — CREAR
`make_media(crudo: Path) -> MediaTruth` genera con ffmpeg lavfi (argumentos en lista; filtergraphs
fijos del test, sin texto de usuario). Mundo sintético: "tiempo real" R; cámara A empieza en R=0,
cámara B en R=1.2 s.
- `tones_expr(shift_s: float) -> str`: expresión `aevalsrc` de R(t+shift):
  `0.4*sin(2*PI*440*T)*between(mod(T,1.7),0,0.35)+0.3*sin(2*PI*660*T)*between(mod(T,2.3),1.1,1.4)+0.6*sin(2*PI*2000*T)*(between(T,3.0,3.1)+between(T,6.0,6.1))`
  con `T = (t+shift)`.
- `crudo/cam a.mp4`: 1440×2560, 30 fps CFR, 12.0 s, `testsrc2` + destello blanco total en el frame
  90 (`drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='eq(n,90)'`), libx264 8 bit bt709;
  audio 44.1 kHz = R(t) (+ si hay `flite`: "hello world this is a test", voz `kal`, con
  `adelay=4200`, mezclado con `amix=inputs=2:normalize=0:duration=first`).
- `crudo/cam b.mov`: 1080×1920, 30 fps, 12.0 s, `testsrc2` + destello en
  el frame 144 (R = 6.0), `format=yuv420p10le`, `setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc`,
  libx264 `-profile:v high10` con `-color_primaries bt2020 -color_trc arib-std-b67 -colorspace bt2020nc`;
  audio 48 kHz = R(t+1.2) + `anoisesrc=a=0.01:seed=42` (semilla fija, 001.6) (+ flite con `adelay=3000`).
- `crudo/pantalla.mp4`: 1894×866, 30 fps, 8 s, `testsrc2`, sin audio.
- `crudo/foto.png` (Pillow, 800×600 RGBA con círculo) y `crudo/brief.txt` ("brief de prueba").
- `MediaTruth`: `offset_b_ms = 1200`, `flash_a_f = 90`, `flash_b_f = 144`, `beeps_real_s = (3.0, 6.0)`,
  `speech_real_s = 4.2`, `has_speech: bool`.

#### `tests/conftest.py` — MODIFICAR
Fixture de sesión `synth_project` (marcador `ffmpeg`): crea `<tmp>/proyecto ñandú`, corre `kcut new`,
`make_media(crudo)`, `kcut ingest`; devuelve `(root, truth)`.

#### `tests/data/ffprobe/iphone_hlg_dv.json`, `screen_sdr_pc.json`, `audio_only.json` — CREAR
JSON a mano con la forma de `ffprobe -show_format -show_streams`. `iphone_hlg_dv.json` = los valores
del ejemplo de inventario (3840×2160, rotación −90, `r_frame_rate 60/1`, `avg_frame_rate 35460/593`,
HLG, DOVI perfil 8). `screen_sdr_pc.json` = h264 1894×866 30/1 `color_range pc` `color_space bt709`.
`audio_only.json` = m4a aac 48000 2 canales.

### Criterios de aceptación S1.2

| # | Tiene que cumplirse | Se comprueba con | Estado |
|---|---|---|---|
| 1 | Validación de rutas (traversal, unidad, UNC, ADS, reservados, espacios/acentos OK) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_paths.py -q` → exit 0, sin "failed" | ❌ |
| 2 | Config: plantilla parsea, claves desconocidas y rangos fallan con el nombre | `... -m pytest tests/unit/test_config.py -q` → exit 0 | ❌ |
| 3 | Probe: HDR/DV/rotación/VFR/rango detectados de los JSON de muestra | `... -m pytest tests/unit/test_probe.py tests/unit/test_classify.py tests/unit/test_naming.py -q` → exit 0 | ❌ |
| 4 | Sync recupera offsets positivos y negativos (±1 ms), rechaza señales no relacionadas y detecta deriva | `... -m pytest tests/unit/test_sync.py -q` → exit 0 | ❌ |
| 5 | Constructores de argumentos: listas exactas, sin rutas en `-vf`/`-af` | `... -m pytest tests/unit/test_ff_args.py tests/unit/test_timebase.py tests/unit/test_manifest.py -q` → exit 0 | ❌ |
| 6 | `kcut new` crea el layout; se niega dentro del repo y sobre un proyecto existente | `... -m pytest tests/integration/test_new.py -q` → exit 0 | ❌ |
| 7 | Ingest sintético: ids `a1 a2 b1 i1 d1`, clases correctas, `a2.hdr == "hlg"`, `offset_ms` de a2 ∈ [1199, 1201] | `... -m pytest tests/integration/test_ingest_synth.py -q` → exit 0 | ❌ |
| 8 | Proxies 540×960 (a1, a2) y 960×438 (b1); en **los 3** proxies, ffprobe da `color_space`, `color_primaries` y `color_transfer` = `bt709` y `color_range` = `tv` (001.4); frames = `frames` del inventario ±1; sin mezzanines creados | mismo archivo de test (casos `test_proxies_*`, `test_no_mezz`) → passed | ❌ |
| 9 | Re-ingest idempotente: mismos ids, sin regenerar proxies (mtime igual) | mismo archivo (caso `test_reingest_stable`) → passed | ❌ |
| 10 | Doctor con `tonemap_chain` y `soxr` | `.venv/Scripts/python.exe -I -X utf8 -m kcut doctor --json` → exit 0, ids `tonemap_chain` y `soxr` con `"ok": true` | ❌ |
| 11 | Lint, formato, tipos | `ruff check`, `ruff format --check`, `mypy` como en S1.1 → exit 0 | ❌ |
| 12 | `InternalError` dentro de un proyecto deja el traceback en `.kcut/logs/` y no en stderr; fuera de proyecto, traceback en stderr solo con `-v`; nunca en `--json` | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_cli_internal_error.py -q` → exit 0 | ❌ |
| 13 | Doctor dentro de un proyecto usa `transcribe.model` (`base` en un `kcut.toml` de prueba → el check `whisper_model` nombra `base`); `kcut.toml` roto → `project_config` con `ok: false` | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_doctor_project.py -q` → exit 0 | ❌ |
| 14 | Privacidad: un `.mov` sintético hecho con `-movflags use_metadata_tags -metadata com.apple.quicktime.location.ISO6709=+18.4861-069.9312/ -metadata com.apple.quicktime.model=iPhone15` (precondición del test: el ffprobe crudo sí muestra ambos valores) → ni `.kcut/inventory.json`, ni `kcut ingest --json`, ni los intermedios (`ffprobe` de su wav16 y su proxy), ni el log, ni el mensaje de un `ToolError` provocado sobre ese archivo contienen `18.4861`, `iPhone15` ni `Metadata:` | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_media_privacy.py -q` → exit 0 | ❌ |
| 15 | `kcut new` nunca sobrescribe: con `edit/estrategia.md` (`aprobado: si`), `edit/versiones.md` y `recursos/recursos.json` ya existentes quedan byte a byte iguales y no salen en `created`; con `crudo` existiendo como **archivo** → `ProjectError` sin crear nada (ni `kcut.toml`) (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_new.py -q -k "keeps_existing or crudo_is_file"` → exit 0, 2 passed | ❌ |
| 16 | Caché envenenada: inventario con id `../../x`, con `wav16` apuntando a `crudo/cam a.mp4` y con `.kcut` como junction a otra carpeta → el inventario se descarta (`inventory_invalid`) o el proyecto se rechaza, ningún archivo se escribe fuera de `.kcut/` y `crudo/` queda idéntico (hash y mtime de cada archivo antes y después) (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_cache_trust.py tests/unit/test_inventory_validation.py -q -ra` → exit 0 (el caso junction se salta con motivo si no se puede crear) | ❌ |
| 17 | `project.name` y `--name` rechazan U+2028, U+2029, U+0085, U+202E y U+200B; el nombre por defecto se limpia y se recorta a 80 (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_config.py tests/integration/test_new.py -q -k "name"` → exit 0 | ❌ |
| 18 | `InternalError` agrega el traceback al **mismo** log de la corrida (las líneas de los hijos siguen ahí) y el mensaje corto sale limpio de metadatos (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_cli_internal_error.py -q -k "same_log or scrubbed"` → exit 0 | ❌ |
| 19 | Un proxy cacheado con la versión de parámetros vieja se regenera en el siguiente ingest (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/integration/test_ingest_synth.py::test_proxy_cache_invalidated_by_version" -q` → `1 passed` | ❌ |
| 20 | Ids nunca se reusan: `a1`, `a2`; cam2 re-exportada → `a3`; luego cam3 → `a4`; `a2` no vuelve; match por (`qhash`, `file`) antes que por `qhash` (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_classify.py -q -k ids_never_reused` → exit 0 | ❌ |
| 21 | wav16 que falla tras un ffprobe bueno: el clip conserva su clase (`video_mudo` si tiene video), su proxy y sus `frames`, con aviso `wav16_failed` (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/integration/test_ingest_failures.py::test_wav16_failed_keeps_class" -q` → `1 passed` | ❌ |
| 22 | Sync con solape parcial: dos clips de 120 s parecidos a voz, desfasados 75 s → aceptados con `offset_ms` = 75000 ±1 (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/unit/test_sync.py::test_partial_overlap_75s_accepted" -q` → `1 passed` | ❌ |
| 23 | Límites: pico del wav16 por bloques igual al de numpy entero; `long_duration` y `too_long` con duraciones simuladas; `timeout_s = 10 × duración + 60` en los args de cada trabajo (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_ingest_limits.py -q` → exit 0 | ❌ |
| 24 | Regex de config con `re.fullmatch`: `language = "es\n"` → error (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_config.py -q -k fullmatch` → exit 0 | ❌ |
| 25 | `os.walk` poda junctions/symlinks de carpeta con aviso `skipped_link` y deduplica por ruta relativa (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_ingest_walk.py -q -ra` → exit 0 (skip con motivo si no se puede crear el enlace) | ❌ |
| 26 | `proxy_size` con tamaño declarado 0 → clip `probe_failed` y el ingest sigue (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/integration/test_ingest_failures.py::test_proxy_size_zero_probe_failed" -q` → `1 passed` | ❌ |
| 27 | `read_json` convierte `ValueError` y `RecursionError` en `ProjectError`; un sidecar corrupto se reconstruye (aviso `cache_rebuilt`) en vez de fallar siempre (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_jsonio.py "tests/integration/test_ingest_failures.py::test_corrupt_sidecar_rebuilt" -q` → exit 0 | ❌ |
| 28 | Ningún `.py` de `src/` ni de `tests/` pasa de 300 líneas (incluye los partidos `inventory_model.py`, `sync_stage.py`, `doctor/result.py`, `doctor/chain_checks.py`) (001.4) | `.venv/Scripts/python.exe -I -X utf8 -c "import pathlib,sys; bad=[str(p) for d in ('src','tests') for p in pathlib.Path(d).rglob('*.py') if len(p.read_text(encoding='utf-8').splitlines())>300]; print(bad); sys.exit(1 if bad else 0)"` → `[]`, exit 0 | ❌ |
| 29 | Sync rechaza refinados débiles: dos clips de 12 s parecidos a voz con B empezando 5 s después → rechazados con `sync_weak_refine` (no aceptados con offset 2295); lote sembrado de clips cortos (8–12 s, offsets 3–6 s) → ninguno aceptado con offset equivocado (error > 2 ms); la cámara B sintética sigue aceptada con 1200 ±1 ms (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_sync.py -q -k "weak_refine or short_batch or synth_cam_b"` → exit 0, 3 passed | ❌ |
| 30 | Enlaces internos: `.kcut → crudo/`, `.kcut → edit/` y `.kcut/logs → crudo/` → proyecto rechazado (`ProjectError`) y nada escrito (archivos de `crudo/` y `edit/` idénticos en hash y mtime) (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_cache_trust.py -q -ra -k internal_link` → exit 0 (skip con motivo si no se puede crear el enlace) | ❌ |
| 31 | Log seguro: con un hard link plantado `.kcut/logs/ingest-*.log` que apunta a un archivo de `crudo/`, después de `kcut ingest` ese archivo de `crudo/` queda byte a byte igual; `append_log` rechaza una ruta con `st_nlink == 2` (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_log_safety.py -q -ra` → exit 0 (skip con motivo si no se puede crear el hard link) | ❌ |
| 32 | `OSError` al calcular el `qhash` de un archivo → ese archivo queda `probe_failed` sin id, el aviso lo nombra y los demás se ingieren (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/integration/test_ingest_failures.py::test_hash_oserror_probe_failed" -q` → `1 passed` | ❌ |
| 33 | `_copy` con origen y destino que resuelven al mismo archivo no lo borra ni lo trunca (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_workfiles.py -q -k copy_same` → exit 0 | ❌ |
| 34 | Límites con la duración real: los args de wav16 y proxy llevan `-t <max_duration_h*3600 + 60>`; un clip que declara 1 s pero cuyo wav16 real pasa de `max_duration_h` (configurado chico en el test) termina `too_long` y su wav16 se borra (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_ingest_limits.py -q -k real_length` → exit 0 | ❌ |
| 35 | `kcut new` sobre una carpeta existente: rechaza enlaces internos del layout, poda junctions al recorrer, y el aviso de "fuera de crudo/" no cuenta `edit/estrategia.md`, `recursos/recursos.json` ni `kcut.toml` (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_new.py -q -ra -k "existing_folder"` → exit 0 | ❌ |
| 36 | `ID_HIGH_MAX = 999_998`: asignar un id nuevo con `id_high` en el tope → `ProjectError`; todo id emitido pasa el validador (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_classify.py -q -k id_cap` → exit 0 | ❌ |
| 37 | Una carpeta donde va `.kcut/inventory.json` o un sidecar → `ProjectError` con "hay una carpeta donde kcut espera un archivo" (no el mensaje del reproductor) (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_jsonio.py -q -k directory_target` → exit 0 | ❌ |
| 38 | El ruido de `anoisesrc` del fixture es determinista: dos generaciones de `cam b.mov` dan el mismo sha256 del audio decodificado (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_synth_media.py -q -k seed` → exit 0 | ❌ |
| 39 | Ningún `.py` de `src/` ni de `tests/` pasa de 300 líneas (incluye `config/names.py`, `config/fields.py`, `ingest/scan.py`, `ingest/examine.py`, `ingest/inventory_check.py`, `ingest/inventory_json.py`, `tests/fixtures/links.py`) (001.6) | `.venv/Scripts/python.exe -I -X utf8 -c "import pathlib,sys; bad=[str(p) for d in ('src','tests') for p in pathlib.Path(d).rglob('*.py') if len(p.read_text(encoding='utf-8').splitlines())>300]; print(bad); sys.exit(1 if bad else 0)"` → `[]`, exit 0 | ❌ |
| 40 | Sync en clip corto con audio casi periódico: con la señal de tonos de `tests/unit/sync_signals.py`, dos clips de 12 s con B empezando 4 s y 6 s después → rechazados con `sync_ambiguous` (antes se aceptaban con −2800 y −800); los casos del criterio 29 siguen igual; la cámara B sintética sigue aceptada con 1200 ±1 ms; con el clip más corto de 14 s o más no se calcula el lag con piso 0.5 (001.7) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_sync.py tests/unit/test_sync_floor.py -q -k "ambiguous or weak_refine or short_batch or synth_cam_b"` → exit 0 | ❌ |
| 41 | `kcut new X` con el destino dentro de una carpeta del layout de un proyecto padre (`P/crudo/X`, `P/edit/X`, `P/.kcut/X`…) → exit 3 con "no creo un proyecto dentro de <carpeta>/ de otro proyecto", no se crea nada y `P/crudo/` queda byte a byte igual; `P/otra/X` (fuera del layout) sigue permitido (001.7) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_new_refusals.py -q -k nested_in_layout` → exit 0 | ❌ |
| 42 | `run_ingest(..., log=None)` no crea ni escribe ningún archivo en `.kcut/logs/` (001.7) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_log_safety.py -q -k no_log` → exit 0 | ❌ |
| 43 | Log vacío: `kcut doctor` dentro de un proyecto no deja logs de 0 bytes; una corrida que escribió algo conserva su log; un log de 0 bytes que ya no es el mismo archivo que se creó (otro `st_ino`) o tiene `st_nlink > 1` no se borra (001.7) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_log_safety.py -q -k empty_log` → exit 0 | ❌ |
| 44 | `append_log` con un `OSError` (la carpeta del log es un archivo) no lanza: el texto va a stderr con aviso. `proc.run` de un hijo con ese log termina normal (o por su timeout) y al volver el hijo ya no está vivo (001.7) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_proc.py tests/integration/test_proc_timeout.py -q -k log_oserror` → exit 0 | ❌ |
| 45 | Una carpeta del layout que existe como archivo regular (por ejemplo `.kcut/logs`) → `kcut ingest` sale con exit 3 y "hay un archivo donde kcut espera una carpeta: .kcut/logs"; el `inventory.json` anterior queda byte a byte igual (001.7) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_cache_trust.py -q -k layout_folder_is_file` → exit 0 | ❌ |
| 46 | Los avisos de sync por clip salen del motivo de rechazo guardado, no de si `refine_corr` es `None`: un rechazo por `ratio` con `refine_corr` presente da `sync_rejected`, uno por refinado débil `sync_weak_refine` y uno ambiguo `sync_ambiguous` (001.7) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_sync.py tests/unit/test_inventory.py -q -k warning_from_reason` → exit 0 | ❌ |
| 47 | Suite rápida: en `pytest -q --durations=0` de la suite completa, todo test que tarda más de 2 s lleva `@pytest.mark.slow`; `pytest -m "not slow" -q` sale con exit 0; la suite completa recolecta lo mismo que antes del cambio más los tests nuevos de 001.7 (001.7) | `.venv/Scripts/python.exe -I -X utf8 -m pytest -m "not slow" -q --durations=5` → exit 0 y ningún test listado pasa de 2 s | ❌ |
| 48 | Inventario con `lag_a_ms` o `lag_b_ms` fuera de ±43 200 000 (por ejemplo `10**400`) → `inventory_invalid` y el ingest sale con 0, en modo humano y `--json`; la segunda corrida tampoco falla (001.7 punto 11) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_inventory_validation.py tests/integration/test_cache_trust.py -q -k lag_range` → exit 0 | ❌ |
| 49 | `reason` con secuencias de escape (`\x1b]0;...\x07`, `\x1b[2J`, `\r`) en el inventario → `inventory_invalid`; la línea `AVISO` humana de un rechazo válido sale de la tabla fija, sin el `reason` crudo; un `method` desconocido no se imprime (001.7 punto 12) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_inventory_validation.py tests/integration/test_ingest_output.py -q -k "reason_hygiene or method_hygiene"` → exit 0 | ❌ |
| 50 | `append_log(log, 'x\ud800')` y `proc.run([..., 'clip\ud800.mov'], log=log)` no lanzan; el log tiene el texto con reemplazo (001.7 punto 13) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_logfile.py -q -k surrogate` → exit 0 | ❌ |
| 51 | `crudo/clip\ud800.mov` junto a un clip normal → exit 0, aviso `probe_failed` sin id con "caracteres inválidos", el clip normal se ingiere y `inventory.json` se guarda (001.7 punto 14) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_ingest_failures.py -q -k surrogate_name` → exit 0 | ❌ |
| 52 | Un miembro guardado por una versión anterior del algoritmo de sync (sin `sync_version` o con otra) no se reusa: se vuelve a medir. Con un inventario de 001.6 que aceptó los tonos de 12 s +4 s con −2800, un `kcut ingest` normal (sin `--resync`) lo deja rechazado con `sync_ambiguous`; un miembro con la `sync_version` actual y el mismo `qhash` sí se reusa sin re-medir (001.7 punto 15) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit tests/integration -q -k sync_version` → exit 0 | ❌ |
| 53 | `test_cli_internal_error.py::TestInsideAProject::test_other_errors_leave_no_traceback_in_the_log` vuelve a exigir que el log exista durante el `run` (`args.log is not None and args.log.is_file()`) y falla si `_run_log` deja de crearlo (001.7 punto 16) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_cli_internal_error.py -q` → exit 0 | ❌ |
| 54 | Si el traceback de un `InternalError` cayó a stderr porque el log no se pudo escribir, el mensaje no dice "Detalle técnico en <log>"; si se escribió, sí lo dice (001.7 punto 17) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_cli_internal_error.py -q -k detail_hint` → exit 0 | ❌ |
| 55 | Texto no confiable nunca llega crudo a la consola: con (a) una clave `"\x1b]0;X\x07\x1b[2J"` en `inventory.json`, (b) un `id` de clip con ESC en el inventario y (c) un archivo `crudo/` con U+009B, U+007F y U+202E en el nombre, la salida de `kcut ingest` (stdout y stderr, modo humano y `--json`) no contiene los bytes 0x1B, 0x07 ni 0x7F, ningún carácter U+0080–U+009F ni U+202E, y sí la forma escapada (`\x1b`, `\u202e`…); `safe_text` deja intactos `ñ`, tildes, emoji y `\n` (001.8 punto 1) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit tests/integration -q -k "safe_text or console_hygiene"` → exit 0 | ❌ |
| 56 | En `kcut ingest --json`, un rechazo de sync lleva en `reason` el texto fijo de la tabla (nunca el `reason` guardado) y `method` es `null` si no está en `SYNC_METHODS` (001.8 punto 2) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_ingest_output.py -q -k json_hygiene` → exit 0 | ❌ |
| 57 | Miembro del inventario con `offset_ms` o `drift_ms` fuera de ±43 200 000, o `drift_windows` fuera de 0 … 100 000 → `inventory_invalid` y se re-mide (001.8 punto 3) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_inventory_validation.py -q -k member_ranges` → exit 0 | ❌ |
| 58 | Un entero fuera de rango de 5000 dígitos produce un mensaje de error de menos de 200 caracteres que dice cuántos dígitos tenía (001.8 punto 4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_schema_util.py -q -k long_value` → exit 0 | ❌ |
| 59 | Un float del inventario o de `kcut.toml` que llega como entero gigante (`"score": 10**400`) o como `1e999` → error de validación (`inventory_invalid` en el inventario, `ProjectError` en `kcut.toml`), nunca `OverflowError`; `kcut ingest` sale con 0 (001.9 punto 1) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_schema_util.py tests/unit/test_inventory_validation.py -q -k huge_float` → exit 0 | ❌ |
| 60 | `one_of` con un valor entero de 5000 dígitos da un mensaje de menos de 200 caracteres, sin `ValueError` (001.9 punto 2) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_schema_util.py -q -k describe_long` → exit 0 | ❌ |
| 61 | Con el log saboteado (hard link), lo que cae a stderr (cabecera `$ ...` con un nombre de archivo con U+009B/U+202E y el stderr del hijo con ESC) sale escapado por `safe_text`, sin bytes 0x1B ni U+0080–U+009F ni U+202E (001.9 punto 3) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_logfile.py -q -k stderr_fallback_safe` → exit 0 | ❌ |
| 62 | `MAX_TIME_MS == 48 * 3_600_000` es el tope de `lag_a_ms`, `lag_b_ms`, `offset_ms` y `drift_ms`, y coincide con el máximo de `ingest.max_duration_h` (48.0); ±172 800 000 se acepta, ±172 800 001 da `inventory_invalid` (001.9 punto 4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit -q -k "max_time or lag_range or member_ranges"` → exit 0 | ❌ |

---

## S1.3 — `kcut transcribe` + `kcut pack`

### Archivos

#### `src/kcut/text/normalize.py` — CREAR (puro)
`norm_token(s: str) -> str`: NFD, quitar marcas combinantes, minúsculas, quedarse con `[a-z0-9]`
(`"¿Qué?"` → `"que"`, `"ñandú"` → `"nandu"`). `norm_tokens(text: str) -> list[str]` (split por espacios,
`norm_token`, descarta vacíos).

#### `src/kcut/text/corrections.py` — CREAR (DS8)
Formato `edit/correcciones.json` (lo escribe Claude):

```json
{"schema": "kcut.correcciones/1",
 "items": [
  {"word": "a1:w0031", "expect": "Hicksville,", "text": "Higgsfield,", "why": "glosario"},
  {"word": "a1:w0301", "expect": "por", "text": "por su", "why": "confirmado por Yedin"},
  {"word": "a1:w0400", "expect": "Gracias.", "text": "", "why": "alucinacion sobre silencio"}
 ]}
```
- `expect` debe ser igual (exacto, tras `strip()`) al texto crudo de esa palabra; si no → error
  "la corrección apunta a otra palabra (¿cambió la transcripción?)" → `CheckFailed`.
- `text` vacío = la palabra se borra (subtítulos y QA). Varias palabras en `text` = la palabra se
  parte en tokens que se reparten su duración en proporción a `len(token)` (enteros en ms; el último
  token absorbe el resto).
- `load_corrections(project) -> dict[str, Correction]`; `apply(words: list[Word], corr) -> list[Word]`
  (devuelve palabras corregidas con `corrected: bool`; ids nuevos de tokens extra: `<id>.1`, `<id>.2`).

#### `src/kcut/transcribe/model.py` — CREAR
`@dataclass(frozen=True) Word(id: str, i: int, text: str, s_ms: int, e_ms: int, p: float, corrected: bool = False)`,
`@dataclass Transcript(clip_id, key, language, language_p, duration_ms, words: list[Word], segments: list[Segment], params: dict[str, object], elapsed_s: float)`.
Id de palabra = `f"{clip_id}:w{i:04d}"` (se compone al cargar; la caché no guarda el clip).

#### `src/kcut/transcribe/cache.py` — CREAR
- Clave: `sha256(wav16_sha256 + json.dumps(params, sort_keys=True))`, con `params = {"model", "compute_type", "beam_size", "language": null, "initial_prompt", "vad_filter": false, "condition_on_previous_text": false, "word_timestamps": true, "engine": "faster-whisper <versión>"}`.
- Archivo `.kcut/transcripts/<key>.json`:

```json
{"schema": "kcut.transcript/1", "key": "5be1...", "wav_sha256": "c0ff...",
 "params": {"model": "medium", "compute_type": "int8", "beam_size": 5, "language": null,
            "initial_prompt": "Eh, este, o sea, mmm, bueno, pues. Higgsfield, Claude, IA.",
            "vad_filter": false, "condition_on_previous_text": false, "word_timestamps": true,
            "engine": "faster-whisper 1.2.1"},
 "language": "es", "language_p": 0.98, "duration_ms": 131233, "elapsed_s": 96.1,
 "words": [{"i": 0, "w": "Bueno,", "s_ms": 53412, "e_ms": 53780, "p": 0.91}],
 "segments": [{"s_ms": 53412, "e_ms": 57500, "text": "Bueno, te da curiosidad..."}]}
```
- Índice `.kcut/transcripts/index.json` = `{"a1": "<key>", "a2": "<key>"}`.
- `load_transcript(project, clip_id) -> Transcript | None`.

#### `src/kcut/transcribe/engine.py` — CREAR
- `build_prompt(cfg: ProjectConfig) -> str`: muletillas con mayúscula inicial unidas por `", "` + `". "`
  + glosario unido por `", "` + `"."` + (`" " + prompt_extra` si hay).
- `class Engine`: `__init__(self, cfg: TranscribeSection, allow_download: bool)` carga
  `WhisperModel(model, device="cpu", compute_type=..., cpu_threads=cpu_threads or os.cpu_count(), local_files_only=not allow_download)`;
  error de modelo ausente → `MissingDependency` (7) con el comando `kcut transcribe --allow-download`.
  `transcribe(self, wav16: Path, prompt: str, language: str | None, progress) -> RawResult`:
  `language=None` (detección por clip, **no se fuerza**), `word_timestamps=True`, `vad_filter=False`,
  `condition_on_previous_text=False`, `beam_size`. Palabras: `w.word.strip()`, `s_ms=round(start*1000)`,
  `e_ms=round(end*1000)`, `e_ms = min(e_ms, duration_ms)`, `e_ms >= s_ms + 1`. Progreso por segmento.

#### `src/kcut/analysis/energy.py` — CREAR (puro, lección 2)
- `rms_db(x, sr, hop_ms=10) -> NDArray[np.float32]`: `20*log10(sqrt(mean(x²)) + 1e-9)` por bloque.
- `silence_runs(db, hop_ms, threshold_db, min_ms) -> list[tuple[int, int]]`: rangos `[start_ms, end_ms)`
  con `db < threshold` de duración ≥ `min_ms`.
- `voiced_without_words(db, hop_ms, threshold_db, words, min_ms=250, tol_ms=50) -> list[tuple[int, int]]`:
  tramos con `db >= threshold` de ≥ 250 ms que no tocan ninguna palabra (ampliada ±50 ms).
- `word_in_silence(word, runs) -> bool`: toda la palabra cae dentro de un tramo de silencio.

#### `src/kcut/pack/phrases.py` — CREAR (puro)
`split_phrases(words, runs, phrase_pause_ms) -> list[Phrase]`, `Phrase(words, start_ms, end_ms, pause_before_ms)`.
- Corte: por cada silencio `R` con duración ≥ `phrase_pause_ms`, la frase se corta antes de la
  primera palabra con `s_ms >= R.start + 50`.
- Bordes por energía (no por Whisper): `start_ms = first.s_ms`, salvo que un silencio contenga
  `first.s_ms` (`R.start <= s < R.end`) → `start_ms = R.end`. `end_ms = last.e_ms`, salvo que un
  silencio contenga el final (`R.start < e <= R.end`) → `end_ms = R.start`. Si queda
  `end_ms <= start_ms`, se usan los valores crudos.
- `pause_before_ms` = inicio de esta frase − fin de la anterior (la primera: `None`).

#### `src/kcut/pack/markers.py` — CREAR (puro)
Por palabra, banderas: `F` muletilla (secuencias de `norm_tokens` de cada entrada de `fillers`,
incluidas las de varias palabras), `R` tartamudeo (token igual al anterior en la misma frase),
`?` probabilidad < `low_prob`, `H` posible alucinación (`word_in_silence`), `C` corregida.
Por frase: `retake_of: int | None` = `start_ms` de la frase anterior más reciente del mismo clip
con ≥ 3 tokens, a ≤ 60 s, y `difflib.SequenceMatcher(None, a, b).ratio() >= 0.75`.

#### `src/kcut/pack/votes.py` — CREAR (puro)
`vote(master_words, members: list[tuple[list[Word], int]]) -> dict[str, str]` (id → texto alternativo):
cada palabra del miembro se pasa al reloj del maestro sumando `offset_ms`; candidatas = palabras
del miembro con solape ≥ 50 % de la duración de la palabra del maestro; si alguna tiene el mismo
`norm_token` → acuerdo; si hay candidatas y ninguna coincide → desacuerdo, alternativa = texto más
frecuente entre candidatas (empate: la de mayor solape). Sin candidatas → sin dato.

#### `src/kcut/pack/writer.py` — CREAR (puro: devuelve strings)
`render_md(...) -> str` y `render_tsv(...) -> str`. Formato exacto de `edit/transcripcion.md`:

```
# Transcripcion - <name>
fps 30 · tiempos de fuente (f = frame del clip, s = segundos) · ids por palabra en edit/palabras.tsv
Marcas: {muletilla} · «repeticion» · palabra? = dudosa · palabra[≠otra] = la otra camara oyo distinto · (¿alucinacion?) · ⟳ fNNN = repite la toma de fNNN · <sonido sin texto 0.42 s fA-fB> · (pausa X s) antes de la frase · LARGA = pausa >= long_pause_ms
Antes de botar una pausa LARGA, mira sus frames con kcut frames (puede haber un gesto).

## a1 - crudo/crudo 1.MOV - 131.23 s - idioma es (0.98) - maestro de sincronia
[f1602-1679 | 53.40-55.97] ¿Te da curiosidad de la {eh} IA y no sabes
[f1705-1751 | 56.82-58.38] (pausa 0.86 s LARGA) con qué empezar, «con con» bueno ⟳ f1460
[f1778-1830 | 59.27-61.00] (pausa 0.30 s) ven, que te[≠de] voy a enseñar?

## a2 - crudo/crudo 2.MOV - 126.51 s - idioma es (0.97) - sincronizado con a1: +4.722 s
Transcrito para votar: 412 palabras, 7 desacuerdos (marcados en a1).

## b1 - crudo/pantalla.mp4 - sin audio
```
- Frames de la línea: `ms_to_f_floor(start_ms)` a `ms_to_f_ceil(end_ms)`; segundos con 2 decimales.
- Miembros sincronizados: solo la línea resumen. Clips de audio no sincronizados: frases completas.
- `<sonido sin texto ...>` se inserta en su posición temporal dentro del clip.

Formato `edit/palabras.tsv` (UTF-8, `\t`, primera línea = cabecera):
`id	clip	s_f	e_f	s	p	flags	text	alt	corrected`
ej.: `a1:w0031	a1	1903	1913	63.46	0.62	?V	Hicksville,	Higgsfield	Higgsfield,`
(`s_f` = floor, `e_f` = ceil; `flags` = letras de markers + `V` si hubo desacuerdo).

#### `src/kcut/commands/transcribe.py` — CREAR
`kcut transcribe [IDS...] [--force] [--allow-download]`. Por defecto: todos los `video_voz` y `audio`
no silenciosos. Con caché válida no transcribe (salvo `--force`). Carga el modelo una vez.
`--json` → `{"ok": true, "clips": [{"id": "a1", "cached": false, "language": "es", "language_p": 0.98, "words": 412, "rtf": 0.73}]}`.

#### `src/kcut/commands/pack.py` — CREAR
Lee inventario, transcripciones, wav16, correcciones; escribe `edit/transcripcion.md` y
`edit/palabras.tsv`. Clip transcribible sin transcripción → `[AVISO]` y línea "sin transcribir".

#### `src/kcut/config/load.py` — MODIFICAR (001.6, higiene ante inyección de prompt)
Los textos del usuario en `kcut.toml` que llegan al contexto de Claude o al prompt de Whisper
(`glossary.terms`, `transcribe.fillers`, `transcribe.prompt_extra`, además de `project.name` que ya lo
hace desde 001.4) rechazan cualquier carácter de las categorías Unicode `Cc`, `Cf`, `Zl` y `Zp`
(`ProjectError` que nombra el campo y la posición).

#### `src/kcut/cli.py` — MODIFICAR (agregar `transcribe`, `pack`)

### Criterios de aceptación S1.3

| # | Tiene que cumplirse | Se comprueba con | Estado |
|---|---|---|---|
| 1 | Normalización y correcciones (expect, borrar, partir, error si no coincide) | `... -m pytest tests/unit/test_normalize.py tests/unit/test_corrections.py -q` → exit 0 | ❌ |
| 2 | Silencios por energía, voz sin palabras, palabra en silencio | `... -m pytest tests/unit/test_energy.py -q` → exit 0 | ❌ |
| 3 | Frases cortadas por silencios y bordes recortados por energía (caso "con" estirado 1.68 s) | `... -m pytest tests/unit/test_phrases.py -q` → exit 0 | ❌ |
| 4 | Marcas: muletilla de 2 palabras, tartamudeo, toma repetida, dudosa, alucinación | `... -m pytest tests/unit/test_markers.py tests/unit/test_votes.py -q` → exit 0 | ❌ |
| 5 | Writer produce el formato exacto (golden string) | `... -m pytest tests/unit/test_pack_writer.py -q` → exit 0 | ❌ |
| 6 | Caché: misma clave → no re-transcribe; parámetro distinto → otra clave | `... -m pytest tests/unit/test_transcribe_cache.py -q` → exit 0 | ❌ |
| 7 | Transcripción: proyecto mínimo con un solo clip `crudo/voz.wav` generado con flite ("hello world this is a test", `adelay=1000`, 6 s, sin tonos) → idioma `en`, "hello" y "world" a ±400 ms de lo esperado; segunda corrida `cached: true` | `... -m pytest tests/integration/test_transcribe_synth.py -q` → exit 0 (skip limpio si falta modelo o flite) | ❌ |
| 8 | Sin modelo y sin `--allow-download` → exit 7 con el comando en el mensaje | caso `test_missing_model_exit7` (monkeypatch) → passed | ❌ |
| 9 | Lint, formato, tipos | como en S1.1 → exit 0 | ❌ |
| 10 | `glossary.terms`, `transcribe.fillers` y `transcribe.prompt_extra` con U+2028, U+2029, U+0085, U+202E o U+200B → `ProjectError` que nombra el campo (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_config.py -q -k prompt_hygiene` → exit 0 | ❌ |
| 11 | El largo de referencia de un clip es el de su wav16 (muestras / 16000), no el `duration_ms` declarado en el inventario: un clip que declara 1 s pero cuyo wav16 dura 30 s se transcribe completo y los silencios cubren los 30 s (001.7) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit -q -k "transcribe and real_length"` → exit 0 | ❌ |
| 12 | Paso 0 (001.10 punto 1): un `inventory.json` inválido con un `id` de 5 KB de prosa → en `kcut ingest --json` el aviso `inventory_invalid` lleva en `detail`/`message_es` solo el texto fijo "se ignora el inventario anterior: no pasó la validación" más la ruta del campo recortada a 120 caracteres; el mensaje completo queda solo en el log; en modo humano igual de corto | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_console_hygiene.py -q -k invalid_inventory_json` → exit 0 | ❌ |
| 13 | Paso 0 (001.10 punto 2): `sync.manual.<id>` fuera de ±`MAX_TIME_MS` en `kcut.toml` → `ProjectError` (exit 3) que nombra la clave | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_config.py -q -k manual_range` → exit 0 | ❌ |
| 14 | Paso 0 (001.10 punto 3): un entero de 5000 dígitos en cualquier clave de `kcut.toml` → `ProjectError` (exit 3), nunca `InternalError` | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_config.py -q -k toml_huge_int` → exit 0 | ❌ |
| 15 | Paso 0 (001.10 punto 4): `safe_text` escapa los selectores de variación U+FE00–U+FE0F y U+E0100–U+E01EF y los de uso privado (`Co`); deja intactos ñ, tildes y emoji sin selector | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_console_hygiene.py -q -k variation_selectors` → exit 0 | ❌ |
| 16 | `pack` con un wav16 que cambió después de `transcribe` (su sha256 ya no es el `wav_sha256` de la transcripción) → `CheckFailed` (exit 1) que nombra el clip y dice "corre kcut transcribe"; con el wav16 igual, `pack` sigue normal (001.11 punto 1) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_pack_command.py -q -k stale_transcript` → exit 0 | ❌ |
| 17 | El audio del criterio 7 sale de la primera voz de flite (en este orden: `slt`, `rms`, `awb`, `kal16`, `kal`) con la que Whisper `medium` escribe "hello" y "world" literales; el test exige los dos textos a ±400 ms (001.11 punto 2) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_transcribe_synth.py -q -ra` → `1 passed` | ❌ |

---

## S1.4 — `kcut view` + `kcut frames`

### Archivos

#### `src/kcut/timeparse.py` — CREAR (puro)
`parse_time(s: str, fps: int) -> int`: `^\d+$` → frames; `^\d+(\.\d+)?s$` → segundos → `round`;
`^(\d+):(\d{1,2}(\.\d+)?)$` → mm:ss → `round`; otro → `UsageError`.

#### `src/kcut/ff/reader.py` — CREAR
`class FrameReader` (iterador de `NDArray[np.uint8]` BGR `(h, w, 3)`):
`__init__(self, path: Path, start_f: int, count: int, fps: int, size: tuple[int, int], *, rgb_filters: str = "", log: Path)`.
Argumentos: `-ss fnum(max(0, (start_f - 0.25)/fps)) -i path -frames:v count -vf "scale=in_color_matrix=bt709:in_range=tv,format=rgb24[,RGB_FILTERS],format=bgr24" -f rawvideo -`
(el −0.25 de frame cae justo en el frame pedido, técnica del piloto). Lee exactamente `w*h*3` bytes
por frame; si el proceso entrega menos frames que `count` → `ToolError` con cuántos llegaron.
Función pura `reader_args(...) -> list[str]` testeada. `grab(path: Path, f: int, fps: int, size: tuple[int, int], *, rgb_filters: str = "", log: Path) -> NDArray[np.uint8]` = un frame.

#### `src/kcut/viz/draw.py` — CREAR
`font(size: int) -> ImageFont.FreeTypeFont` (`ImageFont.load_default(size=size)`, cacheado),
`text_box(draw, xy, text, size, fill, bg=None) -> None`, `wrap(text, size, max_px) -> list[str]`.

#### `src/kcut/viz/timeline.py` — CREAR (técnica de `piloto/view.py`)
`render_timeline(wav16: Path, words: list[Word], start_f: int, end_f: int, fps: int, cfg: AnalysisSection, filmstrip: list[NDArray] | None) -> Image.Image`.
Lienzo 2400 × 420 (+ 220 si hay filmstrip, arriba). Fondo `(18, 18, 22)`. Envolvente RMS a 10 ms
(barras azules), línea roja en `silence_db`, bandas de silencio ≥ `min_silence_ms` en rojo oscuro con
su duración, regla cada 0.5 s con segundos y número de frame, cajas de palabras en 3 filas
escalonadas con texto + sufijo de id (`w0031`), cajas amarillas (p ≥ `low_prob`) o naranjas (dudosas).

#### `src/kcut/viz/grid.py` — CREAR
`grid_overlay(img: NDArray, pct: int) -> Image.Image` (líneas cada `pct` %, etiquetas `0.1 … 0.9` en
borde superior e izquierdo, cruz en el centro) y `sheet(images: list[Image.Image], labels: list[str], cols: int = 8) -> Image.Image`.

#### `src/kcut/commands/view.py` — CREAR
`kcut view <clip> <start> <end> [--filmstrip N] [--out PNG]`: tiempos del reloj de fuente del clip;
rango máximo 60 s (si no → `UsageError`); `N` de 0 a 12 frames del proxy equiespaciados. Salida por
defecto `.kcut/view/<clip>_<start_f>-<end_f>.png`. Imprime la ruta; `--json` → `{"ok": true, "png": "...", "words": 23, "silences": 4}`.

#### `src/kcut/commands/frames.py` — CREAR
`kcut frames <clip> <t> [<t> ...] [--grid 10] [--width 540] [--out DIR]`: cada tiempo → PNG del
proxy con rejilla y rótulo (`a1 f1903 63.43 s`); con más de un tiempo, además una hoja
`<clip>_sheet_<f1>-<fn>.png`. Defecto `.kcut/frames/`. `--json` → `{"ok": true, "frames": [{"f": 90, "png": "..."}], "sheet": "..."}`.
Frame fuera de `[0, frames)` → `UsageError`.

#### `src/kcut/cli.py` — MODIFICAR (agregar `view`, `frames`)

### Criterios de aceptación S1.4

| # | Tiene que cumplirse | Se comprueba con | Estado |
|---|---|---|---|
| 1 | Parser de tiempos | `... -m pytest tests/unit/test_timeparse.py -q` → exit 0 | ❌ |
| 2 | Args del lector: matrices bt709, `-ss` con −0.25 frame, filtros RGB intercalados | `... -m pytest tests/unit/test_reader_args.py -q` → exit 0 | ❌ |
| 3 | Imagen de timeline: tamaño 2400×420 / 2400×640, nº de bandas = nº de silencios | `... -m pytest tests/unit/test_timeline_img.py tests/unit/test_grid_img.py -q` → exit 0 | ❌ |
| 4 | `kcut frames a1 90` en el sintético devuelve el destello (gris medio ≥ 200) y `kcut frames a1 60` no (≤ 180): índice de frame correcto | `... -m pytest tests/integration/test_view_frames_synth.py -q` → exit 0 | ❌ |
| 5 | `kcut view a1 60 240 --filmstrip 6 --json` crea el PNG | mismo archivo (caso `test_view_png`) → passed | ❌ |
| 6 | Lint, formato, tipos | como en S1.1 → exit 0 | ❌ |

---

## S1.5 — EDL en frames + `kcut edl check` + `kcut render` base

### Formato `edit/edl-vN.json` (lo escribe Claude)

```json
{"schema": "kcut.edl/1", "version": 1, "fps": 30, "output": {"w": 1080, "h": 1920},
 "frames": 345, "look": "neutro",
 "sources": {"a1": {"qhash": "sha256:4b1e..."}, "a2": {"qhash": "sha256:9f2c..."},
             "b1": {"qhash": "sha256:07aa..."}},
 "clips": [
  {"kind": "gap", "at_f": 0, "dur_f": 30, "why": "gancho sobre color"},
  {"kind": "voice", "at_f": 30, "src": "a1", "in_f": 60, "out_f": 240, "why": "frase 1"},
  {"kind": "gap", "at_f": 210, "dur_f": 60, "why": "inserto de pantalla"},
  {"kind": "voice", "at_f": 270, "src": "a1", "in_f": 300, "out_f": 345, "why": "frase 2"},
  {"kind": "gap", "at_f": 315, "dur_f": 30, "why": "cierre"}
 ],
 "spans": [
  {"kind": "color", "at_f": 0, "dur_f": 30, "color": "#0B0B0E"},
  {"kind": "cam", "at_f": 30, "dur_f": 60, "src": "a1", "zoom": 1.3, "cx": 0.5, "cy": 0.5, "anchor": "top"},
  {"kind": "cam", "at_f": 90, "dur_f": 90, "src": "a2", "zoom": 1.0, "push": 0.05},
  {"kind": "cam", "at_f": 180, "dur_f": 30, "src": "a1", "zoom": 1.5, "cx": 0.4, "look": "calido"},
  {"kind": "screen", "at_f": 210, "dur_f": 60, "src": "b1", "src_f": 0,
   "keys": [{"at_f": 0, "crop": [0.5, 0.5, 1.0], "card": [1040, 476]},
            {"at_f": 30, "crop": [0.7, 0.4, 0.3], "card": [1000, 760]}],
   "remap": [{"at_f": 0, "src_f": 0, "speed": 1.0}, {"at_f": 30, "src_f": 90, "speed": 2.0}]},
  {"kind": "cam", "at_f": 270, "dur_f": 45, "src": "a1", "look": "cinematico"},
  {"kind": "color", "at_f": 315, "dur_f": 30, "color": "#0B0B0E", "fade_out_f": 10}
 ]}
```

Campos (todo `*_f` entero; claves desconocidas = error):
- Raíz: `schema` = `"kcut.edl/1"`, `version` (= N del nombre), `fps` (= proyecto), `output` (= proyecto),
  `frames` (total de salida), `look` (default `"neutro"`), `sources`, `clips`, `spans`.
- `sources` (001.6, decisión del dueño): mapa `{"<id de clip>": {"qhash": "<qhash del inventario>"}}` con
  **todo** `src` usado por `clips` o `spans`. Así un id renumerado nunca corta el video equivocado.
- `clips` = línea de **audio**, contigua: `voice` {`at_f`, `src` (clip con audio del inventario),
  `in_f`, `out_f` (reloj de `src`, `out_f` exclusivo), `why`} o `gap` {`at_f`, `dur_f`, `why`}.
  Duración de voice = `out_f − in_f`.
- `spans` = línea de **video**, contigua, cubre `[0, frames)`. Comunes: `kind`, `at_f`, `dur_f`,
  `look` (opcional; `null`/ausente = el global), `fade_in_f`/`fade_out_f` (opcional, a/desde negro,
  default 0), `why` (opcional).
  - `cam`: `src` (clip con video), `zoom` 1.0–3.0 (default 1.0), `cx`/`cy` 0–1 (default 0.5),
    `anchor` ∈ `top center bottom` (default `center`), `push` 0–0.5 (default 0: zoom sube lineal de
    `zoom` a `zoom*(1+push)` a lo largo del span), `src_f` opcional. **Sin `src_f`** = sincronizado:
    cada frame del span debe caer en un clip `voice` cuyo `src` esté en el grupo de sync del `src`
    del span (o sea él mismo). **Con `src_f`** = libre: reproduce `src` desde `src_f` a 1×.
  - `broll`: `src`, `src_f`, `push` (default 0.07), `cx`, `cy`, `dim` 0–1.5 (default 1.0),
    `sharpen` 0–1 (default 0).
  - `screen`: `src`, `src_f`, `keys` (≥ 1; primero con `at_f = 0`; `at_f` estrictamente creciente y
    `< dur_f`; `crop = [cx, cy, cw]` normalizados al ancho/alto de la fuente, `cw` 0.05–1; `card = [w, h]`
    px de salida con `w ≤ W − 16`, `h ≤ H − 120`), `remap` opcional (primero `at_f = 0`, creciente,
    `speed` 0.25–4, default 1.0), `card_y` 0–1 (default 0.47).
  - `color`: `color` hex.

### Archivos

#### `src/kcut/edl/model.py` — CREAR
Dataclasses `VoiceClip`, `GapClip`, `CamSpan`, `BrollSpan`, `ScreenSpan`, `ColorSpan`, `ScreenKey`,
`RemapPoint`, `Edl`; `parse_edl(data, path_label) -> tuple[Edl | None, list[Issue]]` (no lanza:
junta los errores de esquema como `Issue(code="E01", ...)`); `load_edl(project, rel) -> tuple[Edl | None, list[Issue], int]` (versión del nombre).

#### `src/kcut/edl/validate.py` — CREAR (puro)
`validate(edl, inv: Inventory, cfg: ProjectConfig, version_from_name: int) -> list[Issue]`,
`Issue(code: str, level: Literal["error", "warning"], path: str, message_es: str)`. Reglas:

| Código | Nivel | Regla |
|---|---|---|
| E01 | error | esquema: tipo, clave desconocida, faltante, `*_f` no entero |
| E02 | error | `fps` ≠ proyecto o `version` ≠ N del nombre |
| E03 | error | `output` ≠ tamaño del preset del proyecto |
| E04 | error | `sources`: falta, no cubre algún `src` usado, el clip con ese id no está en el inventario, o su `qhash` en el inventario es distinto del de `sources` (el mensaje nombra el id) (001.6) |
| E05 | error | `src` desconocido o de clase incompatible (voice: clase con audio; cam/broll/screen: con video) |
| E06 | error | voice: `in_f < 0`, `out_f > frames del src`, `out_f <= in_f` |
| E07 | error | clips no contiguos (`at_f` ≠ suma acumulada) |
| E08 | error | suma de clips ≠ `frames` ≠ suma de spans |
| E09 | error | spans no contiguos o `dur_f <= 0` |
| E11 | error | cam sincronizado sobre un `gap`, o sobre un voice de otro grupo, o `src` rechazado/sin sync |
| E12 | error | frames de fuente fuera de `[0, frames del src)` (calculados con `timeline.py`) |
| E13 | error | valor numérico fuera de rango (tabla de campos) o tarjeta que no cabe |
| E14 | error | `look` desconocido |
| E15 | error | `keys`/`remap` mal ordenados o fuera del span |
| E17 | error | `fade_in_f + fade_out_f > dur_f` |
| W01 | warning | span `cam` o `broll` que escala > 10 % por encima de la resolución disponible (`upscale_factor > 1.10`) |
| W02 | warning | clip voice de menos de 3 frames |
| W03 | warning | corte entre dos `cam` del mismo `src` con cambio de zoom < 15 % (salto sin disimular) |
| W04 | warning | span sincronizado que cruza un corte de voz (aviso informativo) |

#### `src/kcut/edl/timeline.py` — CREAR (puro)
- `voice_at(edl, out_f) -> VoiceClip | None`.
- `shift_f(inv, voice_src, cam_src, fps) -> int` = `ms_to_f_round(off(voice_src) − off(cam_src))`
  con `off(master) = 0`, `off(miembro) = offset_ms`. (Ej.: a2 con +4722 ms a 30 fps → −142.)
- `span_source_frames(edl, span, inv) -> list[int]`: un frame de fuente por frame de salida.
  cam sincronizado: `c.in_f + (k − c.at_f) + shift_f(c.src, span.src)`; cam libre/broll:
  `src_f + (k − at_f)`; screen: con `remap`, último punto con `at_f ≤ r` →
  `p.src_f + floor((r − p.at_f) * p.speed)`, sin remap `src_f + r`; color: lista vacía.
- `source_to_output(edl, src, f) -> list[int]` (frames de salida donde se oye ese frame de fuente).

#### `src/kcut/edl/words.py` — CREAR (puro; regla de la lección 4)
`map_words(edl, transcripts: Mapping[str, list[Word]], fps) -> list[KeptWord]`,
`KeptWord(id, text, clip_index, out_s_f, out_e_f, src, s_ms, e_ms)`, ordenadas por `out_s_f`.
En unidades enteras de 0.6 (`A = in_f*1000`, `B = out_f*1000`, `S = s_ms*fps`, `E = e_ms*fps`):
- La palabra entra al clip si **(a)** `A + 80*fps < E <= B` (su final cae dentro), o **(b)**
  `A <= S < B − 50*fps` y `E > B` (empieza dentro y Whisper la estiró más allá del corte).
- Si entra a varios clips, se queda en el de mayor solape `min(E,B) − max(S,A)`; empate → el primero.
- `S0 = max(S, A)`, `E0 = min(E, B, S0 + 900*fps)`; `out_s_f = c.at_f + rdiv(S0 − A, 1000)`;
  `out_e_f = max(out_s_f + ms_to_f_ceil(120, fps), c.at_f + rdiv(E0 − A, 1000))`, recortado a
  `c.at_f + (out_f − in_f)`; si queda `out_e_f <= out_s_f` → `out_e_f = out_s_f + 1` (y si eso se pasa
  del clip, `out_s_f = out_e_f − 1`).
- Se aplican las correcciones antes de mapear; palabras con texto vacío se descartan.

#### `src/kcut/edl/gate.py` — CREAR (puro + lectura)
`read_front_matter(text: str) -> dict[str, str]`: el archivo debe empezar con una línea `---`; se
leen líneas `clave: valor` (split en el primer `:`, strip) hasta la siguiente `---`.
(001.4, cierra en falso ante cualquier duda) Las líneas se separan **solo** por `"\n"` (nunca
`str.splitlines()`, que también corta en U+0085, U+2028 y U+2029) y se quita un `"\r"` final; cada
línea del front-matter debe pasar `re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*?)[ \t]*", línea)`
y su valor no puede tener caracteres de las categorías `Cc`, `Cf`, `Zl` o `Zp`; una clave `aprobado`
repetida es error. Cualquiera de esos errores → `strategy_approved` devuelve `approved: false` con
el motivo, y `render`/`build` salen con 5.
`strategy_approved(project) -> GateStatus(approved: bool, file: str, reason_es: str)`: aprobado solo
si `aprobado` normalizado (`norm_token`) es `"si"` (acepta `si` y `sí`). Archivo ausente → no aprobado.

#### `src/kcut/render/looks.py` — CREAR (DS3, D10)
`LOOKS: Mapping[str, LookDef]`, `LookDef(id, chain: str, name_es, purpose_es, avoid_es, cost)`.
Cadenas exactas (solo filtros RGB):

| id | cadena | para qué |
|---|---|---|
| `neutro` | `""` | sin look |
| `contraste` | `curves=all='0/0 0.25/0.20 0.5/0.5 0.75/0.80 1/1',vibrance=intensity=0.12` | más punch y color |
| `calido` | `colorbalance=rs=0.04:bs=-0.04:rm=0.03:bm=-0.03:rh=0.02:bh=-0.02,vibrance=intensity=0.05` | piel cálida, interiores |
| `frio` | `colorbalance=rs=-0.04:bs=0.05:rm=-0.03:bm=0.04:rh=-0.01:bh=0.02` | tech, noche |
| `cinematico` | `curves=all='0/0.02 0.25/0.21 0.5/0.5 0.75/0.79 1/0.98',colorbalance=rs=-0.05:gs=0.01:bs=0.05:rh=0.05:gh=0.01:bh=-0.04,vibrance=intensity=-0.08,vignette=angle=0.5` | teal-naranja suave con viñeta |
| `bn-acento` | `colorhold=color=0xRRGGBB:similarity=0.25:blend=0.10` con `brand.accent` | blanco y negro salvo el color de marca |

`look_chain(look_id, brand) -> str` (`bn-acento` sustituye `RRGGBB` desde el hex validado).

#### `src/kcut/render/geometry.py` — CREAR (puro)
- `cover_box(sw, sh, W, H) -> tuple[float, float]`: mayor rectángulo con aspecto `W/H` dentro de la fuente.
- `cam_crop(sw, sh, W, H, zoom, cx, cy, anchor) -> tuple[int, int, int, int]` (x, y, w, h): tamaño
  = `cover_box / zoom`; x centrado en `cx*sw` acotado a `[0, sw − w]`; y: `top` → 0, `bottom` → `sh − h`,
  `center` → centrado en `cy*sh` acotado.
- `broll_crop(..., push_k)` igual con zoom = `push_k`.
- `ease_in_out_cubic(x)`, `back_out(x)` (fórmulas de `piloto/compose.py`).
- `screen_state(keys, rel_f) -> tuple[crop, card]`: interpolación `ease_in_out_cubic` entre claves,
  se mantiene la última.
- `upscale_factor(span, mezz_dims, W, H) -> float`.

#### `src/kcut/render/screen_card.py` — CREAR (técnica de `piloto/compose.py::screen_frame`)
`make_background(W, H, dark, accent) -> NDArray` (base `dark` + brillo radial del `accent` en
(0.5, 0.47) con sigma 0.32 e intensidad 0.16) y
`screen_frame(src, rel_f, fps, span, bg, accent) -> NDArray`: alto del recorte = `cw_px * card_h / card_w`;
relleno con `dark` donde el recorte sale de la fuente; entrada `scale = 0.72 + 0.28*back_out(rel_s/0.32)`,
`alpha = min(1, rel_s/0.18)`; esquinas redondeadas r = `max(6, 28*scale)`; borde `accent` de 4 px;
sombra desplazada 24 px, blur sigma 28, opacidad 0.65; centro en `(W/2, card_y*H)`.

#### `src/kcut/render/mezz.py` — CREAR (DS12)
- `plan_mezz(edl, inv, cfg) -> list[MezzJob]` (puro): frames de fuente necesarios por clip (de
  `span_source_frames`) → rangos `[a, b)`; dos rangos se unen si el hueco entre ellos es `< 2*fps`
  → a cada rango `±fps//2` de margen acotado a `[0, frames)` → los que se tocan o solapan tras el
  margen se unen. Escala por clip: cam/broll `s = min(1, H*max(1, zmax)/base_h)` con
  `zmax = max(zoom*(1+push))` de sus spans y `base_h` = alto de `cover_box` en la fuente
  (dimensiones de display); screen `s = min(1, 3840/max(sw, sh))`. Dimensiones pares
  (`2*round(x/2)`). `MezzJob(clip_id, start_f, end_f, w, h, chain, path)`, nombre
  `<id>_<start>-<end>_<w>x<h>_<CHAIN_VERSION>.mp4` en `.kcut/mezz/`.
- `ensure_mezz(project, jobs, progress) -> MezzIndex`: reutiliza un archivo existente que cubra el
  rango con las mismas dimensiones y cadena; si no, lo genera con `mezz_args`.
  `MezzIndex.locate(clip_id, f) -> tuple[Path, int, tuple[int, int]]`.

#### `src/kcut/render/reads.py` — CREAR (puro)
`plan_reads(src_frames: list[int], max_gap: int = 8) -> list[ReadRun]`: corre de índices no
decrecientes con saltos ≤ `max_gap` → `ReadRun(first, last, picks: list[int])` (un lector lee
`[first, last]` seguido y se eligen los frames, con repetición si `speed < 1`).

#### `src/kcut/render/encoder.py` — CREAR
`class Encoder`: `__init__(self, dst: Path, W, H, fps, log)`; `write(self, frame_bgr) -> None`;
`close(self) -> int` (frames escritos). Args: `-f rawvideo -pix_fmt bgr24 -s WxH -r F -i - -vf scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv -c:v libx264 -preset slow -crf 18 -g 2F -pix_fmt yuv420p` + flags de color + `-movflags +faststart dst`. (001.4: el `setparams` final, igual que en los
proxies, para que el video lleve las 4 etiquetas bt709/tv.)

#### `src/kcut/render/lock.py` — CREAR (DS11)
`class OutputLock` (context manager): `__init__(self, locks_dir: Path, name: str)`; bloqueo sin
espera con `msvcrt.locking(fd, LK_NBLCK, 1)` / `fcntl.flock(fd, LOCK_EX | LOCK_NB)` → si falla,
`LockedError`. `atomic_replace(partial: Path, final: Path) -> None` (`PermissionError` → `ProjectError` de 0.10.5).

#### `src/kcut/render/compose.py` — CREAR
`compose_video(project, edl, inv, mezz: MezzIndex, dst: Path, overlay: OverlaySource | None, progress) -> int`.
Por span en orden: frames de fuente → `plan_reads` → `FrameReader` del mezzanine con
`look_chain` → geometría (cam/broll con `cv2.resize`, `INTER_AREA` al bajar, `INTER_CUBIC` al
subir; screen con `screen_frame`; color = relleno). Fórmulas por frame `i` del span (0-based,
`n = dur_f`): zoom de cam `zoom*(1 + push*i/max(1, n-1))`; zoom de broll `1 + push*i/max(1, n-1)`;
broll `sharpen s`: `img*(1+s) - GaussianBlur(img, sigma=2.0)*s` y luego `*dim`, recortado a 0–255
(como `piloto/compose.py::ferrari_frame`); fade in: si `i < fade_in_f`, `*(i+1)/(fade_in_f+1)`;
fade out: si `i >= n - fade_out_f`, `*(n-i)/(fade_out_f+1)` → `overlay.blend(frame, out_f)`
si hay overlay → `Encoder.write`. Afirma frames escritos == `edl.frames` (si no → `InternalError`).

#### `src/kcut/audio/voice_track.py` — CREAR (técnica de `piloto/audio.py`)
`build_voice(project, edl, inv) -> NDArray[np.float32]` de largo exacto `frames*spf`: por clip
`voice`, muestras `[in_f*spf, out_f*spf)` del wav48 de `src` (lo crea `ensure_wav48`) en
`at_f*spf`, con fundidos lineales de 5 ms (240 muestras) en ambos bordes, **salvo** en la unión de
dos clips contiguos en la fuente (`in_f` = `out_f` anterior, mismo `src`). Wav más corto que lo pedido →
`InternalError` (el `edl check` debió atraparlo).

#### `src/kcut/pipeline/__init__.py` — CREAR (docstring) · `src/kcut/pipeline/mux.py` — CREAR
`mux_args(ffmpeg: Path, video: Path, audio: Path, dst: Path, *, audio_f32: bool) -> list[str]`:
`-i video` + (si `audio_f32`: `-f f32le -ar 48000 -ac 1`) `-i audio -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k -ar 48000 -ac 2 -movflags +faststart dst`.

#### `src/kcut/commands/edl.py` — CREAR
`kcut edl check [EDL]`: humano (`[ERROR] E06 clips[4]: ...`, `[AVISO] W03 spans[7]: ...`, estado de
la estrategia) y `--json`:
`{"schema": "kcut.edlcheck/1", "edl": "edit/edl-v1.json", "ok": false, "frames": 345, "duration_display": "00:11.5", "errors": [{"code": "E06", "path": "clips[4]", "message": "..."}], "warnings": [...], "gate": {"approved": false, "file": "edit/estrategia.md"}}`.
Exit 1 si hay errores (los avisos no fallan).

#### `src/kcut/commands/render.py` — CREAR
`kcut render [--edl EDL] [--no-graphics]`: lock `build-vN` → gate (no aprobado → `GateError` 5) →
validación (errores → 1) → `plan_mezz` + `ensure_mezz` → `compose_video` a
`.kcut/build/vN/video.mp4` → `build_voice` → `.kcut/build/vN/voice_raw.f32` → mux de revisión
`.kcut/build/vN/render.mp4` (video copiado + voz cruda en AAC 192k estéreo, con `pipeline/mux.py`).
`--json` → `{"ok": true, "video": "...", "render": "...", "frames": 345, "mezz_built": 3, "mezz_reused": 0, "elapsed_s": 41.2}`.

#### `src/kcut/doctor/checks.py` — MODIFICAR
Agregar `looks` (requerido): cada cadena de `LOOKS` corre en el lector sobre
`-f lavfi -i color=c=gray:s=64x64:d=0.04` con exit 0.

#### `src/kcut/cli.py` — MODIFICAR (agregar `edl`, `render`)

#### `tests/fixtures/synth_edl.py` — CREAR
`write_edl_v1(root: Path) -> EdlTruth`: escribe exactamente el EDL de ejemplo de arriba (con
`sources` llenado con los `qhash` reales de a1, a2 y b1 del inventario, 001.6) en
`edit/edl-v1.json` y `edit/estrategia.md` con `aprobado: si`. `EdlTruth`: `frames = 345`,
`flash_out_f = (60, 150)`, `beep_out_s = (2.0, 5.0)`.

### Criterios de aceptación S1.5

| # | Tiene que cumplirse | Se comprueba con | Estado |
|---|---|---|---|
| 1 | Cada regla E01–E17/W01–W04 tiene un caso que la dispara; el EDL de ejemplo da 0 errores y solo el aviso W01 en `spans[3]` (zoom 1.5 sobre 2560 px) | `... -m pytest tests/unit/test_edl_model.py tests/unit/test_edl_validate.py -q` → exit 0 | ❌ |
| 2 | Mapeo de frames: shift −142 para +4722 ms, remap con speed, libre vs sincronizado | `... -m pytest tests/unit/test_edl_timeline.py -q` → exit 0 | ❌ |
| 3 | Palabras conservadas: inicio temprano (lección 4), estirada sobre el corte, varios clips, mínimo 120 ms | `... -m pytest tests/unit/test_edl_words.py -q` → exit 0 | ❌ |
| 4 | Gate: `si`/`sí` aprueban; `no`, vacío, sin front-matter o archivo ausente no | `... -m pytest tests/unit/test_gate.py -q` → exit 0 | ❌ |
| 5 | Geometría, plan de mezzanines (rangos, margen, escala por zoom) y plan de lecturas | `... -m pytest tests/unit/test_geometry.py tests/unit/test_mezz_plan.py tests/unit/test_reads.py -q` → exit 0 | ❌ |
| 6 | Voz exacta a la muestra: largo `frames*1600`, fades de 240 muestras, sin fade en uniones contiguas | `... -m pytest tests/unit/test_voice_track.py -q` → exit 0 | ❌ |
| 7 | Lock: segundo lock al mismo nombre → `LockedError`; se libera al cerrar | `... -m pytest tests/unit/test_lock.py -q` → exit 0 | ❌ |
| 8 | Looks: neutro conserva gris 128 ±2; calido R−B ≥ 4; frio B−R ≥ 4; contraste oscurece 64 y aclara 192; cinematico esquina ≥ 3 más oscura que el centro; bn-acento deja gris un rojo puro y conserva el acento (G−B ≥ 100); ida y vuelta encoder→lector del lima `#E5FF1F` ±4; con `-v verbose`, ninguna línea `auto_scale_*` convierte desde o hacia un formato `yuv*` | `... -m pytest tests/integration/test_looks_ffmpeg.py -q` → exit 0 | ❌ |
| 9 | Render sin aprobación → exit 5; con aprobación → `video.mp4` de 345 frames 1080×1920 bt709 y `voice_raw.f32` de 552000 muestras | `... -m pytest tests/integration/test_render_synth.py -q` → exit 0 | ❌ |
| 10 | Mezzanines perezosos: a1 tiene 3 archivos (`45-135`, `195-255`, `285-360`, todos 1440×2560), ninguno cubre el frame 0; a2 uno (`69-189`) tone-mapeado con etiquetas bt709; b1 dos (`0-45`, `75-164`) | mismo archivo (caso `test_mezz_lazy`) → passed | ❌ |
| 11 | **Sincronía A/V de punta a punta**: destellos detectados en los frames de salida {60, 150} ±1 y pitidos de 2 kHz en {2.000, 5.000} s ±1 frame en `voice_raw.f32` | `... -m pytest tests/e2e/test_av_sync.py -q` → exit 0 | ❌ |
| 12 | `kcut edl check --json` en el ejemplo → `"ok": true`, `"frames": 345` | mismo archivo de integración (caso `test_edl_check_cli`) → passed | ❌ |
| 13 | Lint, formato, tipos | como en S1.1 → exit 0 | ❌ |
| 14 | Gate a prueba de inyección: `aprobado: no` + U+2028/U+2029/U+0085 + `aprobado: si` en la misma línea física → no aprobado; `aprobado` repetido → no aprobado; línea que no pasa el `fullmatch` → no aprobado (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_gate.py -q -k injection` → exit 0 | ❌ |
| 15 | `video.mp4` del render sintético con `color_space`, `color_primaries`, `color_transfer` = `bt709` y `color_range` = `tv` (001.4) | `.venv/Scripts/python.exe -I -X utf8 -m pytest "tests/integration/test_render_synth.py::test_video_color_tags" -q` → `1 passed` | ❌ |
| 16 | `sources` protege contra ids renumerados: `qhash` distinto en el inventario, clip ausente del inventario, o `src` sin entrada en `sources` → `kcut edl check` exit 1 con E04 que nombra el id, y `kcut render` también sale con 1 sin renderizar (001.6) | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit/test_edl_validate.py tests/integration/test_render_synth.py -q -k sources` → exit 0 | ❌ |

Detección de destello (test): frame `f` es destello si su gris medio ≥ 170 y supera por ≥ 60 el
promedio de los frames `f±3`. Pitido: filtro pasa-banda Butterworth 1800–2200 Hz (scipy), envolvente
a 5 ms, inicio donde cruza el 50 % del máximo.

---

## S1.6 — Capa de gráficos: motor HTML con `seek(t)` + componentes base + subtítulos

### Formato `edit/graphics.json` (lo escribe Claude)

```json
{"schema": "kcut.graphics/1",
 "captions": {"enabled": true, "hide": [{"start": 0, "end": 30}]},
 "cues": [
  {"id": "gancho", "component": "kinetic", "start": 0, "end": 30,
   "params": {"lines": [{"text": "Esto lo hizo", "at_f": 2, "size": 104, "color": "light"},
                        {"text": "la IA", "at_f": 7, "size": 270, "color": "accent"}], "y": 0.45}},
  {"id": "titulo", "component": "title",
   "start": {"word": "a1:w0031", "edge": "start", "offset_f": -1},
   "end": {"word": "a1:w0031", "edge": "start", "offset_f": 30},
   "params": {"text": "Higgsfield", "bar": true, "y": 0.6}},
  {"id": "pill", "component": "label", "start": {"src": "a1", "f": 2010}, "end": 150,
   "params": {"text": "hecho con Higgsfield"}, "hide_captions": false}
 ]}
```
- `start`/`end` (end exclusivo): entero (frame de salida) o ancla. Ancla de palabra:
  `{"word": "<id>", "edge": "start" | "end", "offset_f": int}` → `out_s_f`/`out_e_f` de esa palabra
  conservada (`edl/words.py`) + offset; palabra no conservada → error. Ancla de fuente:
  `{"src": "<clip>", "f": int, "offset_f": int}` → primer frame de salida donde se oye ese frame de
  fuente (`source_to_output`), aviso si aparece varias veces; ausente → error. (DS7)
- Tras resolver: `0 <= start < end <= frames`.
- Colores en params: hex o token de marca `accent accent2 dark light` (Python los resuelve a hex).
- Orden de dibujo = orden del arreglo; los subtítulos siempre arriba de todo.
- `hide_captions`: opcional; por defecto = `big` del componente.
- Todo `at_f` dentro de `params` (líneas, pasos, `path`, `fly_to`, `type_at_f`, `cta_at_f`) es
  relativo al inicio del cue.
- `captions.enabled` de `graphics.json` manda sobre `kcut.toml [captions] enabled`; si falta, vale el
  de `kcut.toml`. El estilo de los subtítulos vive solo en `kcut.toml`. `captions.hide`: ventanas con
  `start`/`end` que siguen las mismas reglas (entero o ancla) que los cues.

### Componentes base (S1.6) — parámetros exactos

`popState` (de `piloto/gfx/overlay.html`): `pop(t, t0, t1, inDur=0.22, outDur=0.16)` → `null` fuera
de `[t0, t1)`; `a = outBack(prog(t, t0, inDur))`, `b = prog(t, t1 − outDur, outDur)`,
`s = (0.6 + 0.4a)(1 + 0.12b)`, `o = clamp(prog(t, t0, 0.6·inDur))·(1 − inCubic(b))`.
Posiciones `x`, `y` = **centro** del elemento como fracción de W/H; tamaños en px de salida.
Texto grande: Inter 900, mayúsculas por CSS, `letter-spacing: -2px`, `line-height: 1`, borde
`-webkit-text-stroke: 12px <dark>` con `paint-order: stroke fill`.

| Componente | big | Parámetros (tipo, default, rango) | Animación |
|---|---|---|---|
| `title` | sí | `text` str req ≤ 40 · `y` 0.6 · `x` 0.5 · `size` 132 (24–400) · `bar` true · `bar_color` accent · `color` (dark si bar, si no light) · `stroke` (= not bar) | `pop(in 0.2, out 0.15)`; barra `scaleX(outCubic(prog(t, start, 0.32)))` desde la izquierda |
| `label` | no | `text` req ≤ 48 · `y` 0.58 · `x` 0.5 · `size` 40 (16–120) · `fg` accent · `bg` dark · `ring` accent | píldora `border-radius 999px`, anillo 4 px, sombra; `pop` por defecto |
| `kinetic` | sí | `lines` lista 1–4 de {`text` ≤ 24, `at_f` ≥ 0, `size` 140 (24–400), `color` light} · `y` 0.5 · `gap_px` 10 (0–200) · `italic` false · `rotate_deg` 0 (−15–15) · `glitch` false | cada línea `pop(start+at_f, end)`; bloque centrado en `y`; `glitch`: sombras `14g px rgba(255,0,80,.8)` y `−14g px rgba(0,220,255,.8)` con `g = 1 − prog(t, t_linea, 0.22)` |
| `endcard` | sí | `lines` como kinetic (1–3) · `cta` str ≤ 40 opcional · `cta_at_f` 22 · `y` 0.47 | líneas como kinetic; `cta` como `label` debajo, `pop(start+cta_at_f, end)` |
| `captions` | — | interno, de `kcut.toml [captions]` | ver abajo |

Subtítulos: bloque centrado en `x = 0.5`, ancho `0.87·W`, centro vertical `captions.y`; palabra
Inter 900 `font_px`, `letter-spacing −1px`, margen `0 9px`, color `captions.color`, borde 11 px
`stroke_color`, sombra `0 6px 18px rgba(0,0,0,.45)`; palabra activa (= última con `s_f ≤ frame`)
en `active_color` con `scale(1 + 0.07·outBack(prog(t, w.s, 0.12)))`; entrada del chunk
`scale(0.86 + 0.14·outBack(prog(t, ch.s, 0.14)))`, `opacity prog(t, ch.s, 0.06)`.

### Regla de chunks de subtítulos (`gfx/captions.py`, puro; de `piloto/cues.py`)

Entrada: `KeptWord` en orden. Texto mostrado = texto corregido sin `, . ; : ! ? ¿ ¡ " ' « » ( )` en
los bordes, en mayúsculas si `uppercase`; vacío → no sale en subtítulos.
Ventanas ocultas = `captions.hide` + cada cue con `hide_captions` efectivo verdadero como
`[start − ms_to_f_ceil(60, fps), end)`.
1. Palabra con `out_s_f` dentro de una ventana oculta → se salta y cierra el chunk actual.
2. Chunk nuevo si el actual no está vacío y: (a) la palabra viene de otro clip del EDL (nunca se
   mezclan clips); (b) el chunk ya tiene `max_words`; (c) `sum(len(t)+1) + len(t_nueva) > max_chars`
   (con texto mostrado); (d) `(out_s_f − último.out_e_f)·1000 > 350·fps`; (e) el texto crudo de la
   última termina en `, . ? ! ; :` y `(último.out_e_f − primero.out_s_f)·1000 >= 400·fps`.
3. Fin del chunk = `último.out_e_f + ms_to_f_ceil(150, fps)`, recortado al inicio del siguiente chunk
   y al inicio de cualquier ventana oculta que empiece dentro del chunk.
Salida: `[{"s_f", "e_f", "words": [{"text", "s_f"}]}]`.

### Archivos

#### `src/kcut/gfx/anchors.py` — CREAR (puro)
`resolve_time(v: int | Mapping, kept: list[KeptWord], edl, path) -> tuple[int, list[str]]` (frame, avisos).

#### `src/kcut/gfx/components.py` — CREAR
Registro `COMPONENTS: Mapping[str, ComponentDef]`; `ComponentDef(id, js_file, big, params: tuple[ParamSpec, ...], name_es, purpose_es, avoid_es, cost, cost_note_es, since)`;
`ParamSpec(name, kind, required, default, lo, hi, max_len, item: tuple[ParamSpec, ...] | None, help_es)` con
`kind` ∈ `str int float bool color point path list`. `validate_params(component, params, path) -> tuple[dict[str, object], list[Issue]]`
(aplica defaults, resuelve colores; parámetro desconocido = error). En S1.6 registra `title`, `label`,
`kinetic`, `endcard`; `captions` es interno y además se publica en el catálogo.

#### `src/kcut/gfx/schema.py` — CREAR
`parse_graphics(data) -> tuple[GraphicsDoc | None, list[Issue]]` (esquema de arriba; `id` único `^[a-z0-9-]{1,32}$`).

#### `src/kcut/gfx/captions.py` — CREAR (regla de arriba)
`build_chunks(kept, cfg: CaptionsSection, hide: list[tuple[int, int]], fps) -> list[Chunk]`.

#### `src/kcut/gfx/resolve.py` — CREAR
`resolve(project, edl, version) -> ResolvedGraphics` (lee graphics.json, transcripciones,
correcciones; valida; resuelve anclas, colores, ventanas, chunks). `data_json(resolved) -> dict`:

```json
{"fps": 30, "w": 1080, "h": 1920, "frames": 345,
 "brand": {"accent": "#E5FF1F", "accent2": "#2FA8FF", "dark": "#0B0B0E", "light": "#FFFFFF"},
 "images": {"recursos/logo.png": "data:image/png;base64,..."},
 "cues": [{"id": "gancho", "component": "kinetic", "start_f": 0, "end_f": 30, "params": {}},
          {"id": "__captions__", "component": "captions", "start_f": 0, "end_f": 345,
           "params": {"style": {}, "chunks": [{"s_f": 105, "e_f": 118, "words": [{"text": "HELLO", "s_f": 105}]}]}}]}
```
Captions activos con un clip voice sin transcripción → error "corre kcut transcribe o pon captions.enabled=false".

#### `src/kcut/gfx/assets.py` — CREAR
`image_data_uri(project, rel) -> str`: `require_approved`, extensión `.png .webp .jpg .jpeg`
(SVG prohibido), ≤ 20 MB, Pillow abre sin error.

#### `src/kcut/gfx/page.py` — CREAR (puro)
`build_page(data: Mapping[str, object], component_ids: list[str]) -> str`: HTML con `base.css`,
`@font-face` Inter 600/800/900 como data URI woff2, `runtime.js`, los JS de los componentes usados y
`<script type="application/json" id="kc-data">` con el JSON donde `</` se escribe `<\/`.
`body` de `W×H`, fondo transparente.

#### `src/kcut/gfx/web/runtime.js` — CREAR
Contrato:
```
window.KC = {register(id, def), clamp(x,a=0,b=1), prog(t,t0,d), outCubic(x), inCubic(x),
             inOutCubic(x), outBack(x), pop(t,t0,t1,inDur=0.22,outDur=0.16) -> {s,o}|null,
             rng(seed) -> () => number /* Park-Miller: seed = seed*16807 % 2147483647 */,
             el(tag, cls, text) -> HTMLElement /* createElement + className + textContent */}
def = {css: string, mount(root, cue, ctx) -> state, update(state, cue, lt, t, ctx)}
ctx = {fps, w, h, brand, images}
window.seek(t: number) -> true   // t = frame/fps; pura: el resultado depende solo de t
window.kcutReady: boolean        // true cuando cargaron fuentes (document.fonts.load de 600/800/900) e imágenes (decode)
```
Al cargar: lee `kc-data`, inyecta los `css`, crea un `div` absoluto `W×H` por cue (en orden) y llama
`mount`. `seek(t)`: por cue, visible si `start_f/fps <= t < end_f/fps` y llama `update` con
`lt = t − start_f/fps`; si no, `display:none`.

Reglas para todo JS de `gfx/web/` (test que las revisa con regex): prohibidos `Date`,
`performance.now`, `Math.random`, `requestAnimationFrame`, `setTimeout`, `setInterval`, `fetch(`,
`XMLHttpRequest`, `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval(`, y en CSS `transition` y
`animation`. Texto siempre con `textContent`.

#### `src/kcut/gfx/web/base.css`, `components/captions.js`, `title.js`, `label.js`, `kinetic.js`, `endcard.js` — CREAR
Según las tablas de arriba.

#### `src/kcut/gfx/capture.py` — CREAR (técnica de `piloto/capture.py`)
- `active_frames(resolved) -> list[int]`: unión de `[start_f, end_f)` de los cues y de los chunks.
- `launch_options() -> dict[str, object]` (única fuente de las opciones de lanzamiento, 001.1):
  `{"headless": True, "chromium_sandbox": True}`. Si con `chromium_sandbox=True` Chromium no
  arranca en Windows, el implementador devuelve **BLOQUEADO** con el error; no se quita el sandbox
  en silencio.
- Bloqueo de red (001.1): antes de `goto`, `page.route("**/*", handler)` donde el handler hace
  `route.abort()` para toda URL que no empiece con `file://` o `data:` y `route.continue_()` para
  esas dos.
- `capture(page_html, work_dir, frames, fps, size, out_dir, progress) -> list[int]`: escribe
  `work_dir/page.html`, Chromium headless con `launch_options()` y el bloqueo de red, viewport `W×H`,
  `device_scale_factor=1`, `goto(as_uri())`,
  espera `window.kcutReady === true` (20 s), CDP `Emulation.setDefaultBackgroundColorOverride` con
  `a=0`, por frame `page.evaluate("t => window.seek(t)", f / fps)` + `Page.captureScreenshot`
  (`format png`, `optimizeForSpeed true`) → `out_dir/{f:06d}.png`. PNG con alfa máximo 0 se borra
  y no entra a la lista. Cualquier `pageerror` o `console.error` → `ToolError` (4) con la lista.
- `capture_stills(..., frames) -> dict[int, Path]`: igual pero sin borrar los vacíos.
- Índice `.kcut/build/vN/gfx/index.json` = `{"fps": 30, "frames": [0, 1, 2], "hash": "<sha256>"}`,
  `hash` = sha256 de (data JSON + runtime + componentes + fuentes). Mismo hash → no recaptura
  (salvo `--force`).

#### `src/kcut/doctor/checks.py` — MODIFICAR (001.1)
El check `chromium` lanza con `gfx.capture.launch_options()`, así doctor prueba las mismas opciones
que usa la captura.

#### `src/kcut/gfx/overlay.py` — CREAR (lección 7)
`class OverlaySource`: `__init__(self, index_path: Path, W: int, H: int)`;
`blend(self, base_bgr, out_f) -> NDArray` → si el frame está en el índice:
`cv2.imread(path, cv2.IMREAD_UNCHANGED)`; forma ≠ `(H, W, 4)` → `InternalError`; alfa recto:
`out = (base·(255 − a) + rgb·a + 127) // 255` en enteros de 16 bits. Función pura `alpha_blend(base, bgra)` testeada.

#### `src/kcut/commands/graphics.py` — CREAR
`kcut graphics check [--edl]` (errores → 1; `--json` con cues resueltos y chunks),
`kcut graphics capture [--edl] [--force]` (lock `build-vN`), `kcut graphics still <f>... [--edl] [--out DIR]`
(PNG con alfa por frame, defecto `.kcut/build/vN/gfx/stills/`).

#### `src/kcut/render/compose.py`, `src/kcut/commands/render.py` — MODIFICAR
`render` sin `--no-graphics` y con `edit/graphics.json`: `resolve` → `capture` (si el hash cambió)
→ `OverlaySource` a `compose_video`. Errores de gráficos → exit 1 antes de renderizar.

#### `src/kcut/cli.py` — MODIFICAR (agregar `graphics`)

#### `tests/fixtures/synth_graphics.py` — CREAR
`write_graphics_v1(root, with_showpieces: bool)`: con `False`, cues `gancho` kinetic 0–30, `titulo`
title 40–80, `pill` label 90–150, `cierre` endcard 315–345; captions activos.

### Criterios de aceptación S1.6

| # | Tiene que cumplirse | Se comprueba con | Estado |
|---|---|---|---|
| 1 | Chunks: ≤ 3 palabras/≤ 18 caracteres, nunca mezcla clips, corte por pausa > 350 ms y por puntuación, ventanas ocultas, recortes del final | `... -m pytest tests/unit/test_captions_chunking.py -q` → exit 0 | ❌ |
| 2 | Anclas de palabra y de fuente, palabra cortada → error | `... -m pytest tests/unit/test_anchors.py tests/unit/test_gfx_schema.py -q` → exit 0 | ❌ |
| 3 | Página: `</script>` en un texto queda escapado; fuentes embebidas; JS sin APIs prohibidas | `... -m pytest tests/unit/test_page_build.py tests/unit/test_gfx_js_rules.py -q` → exit 0 | ❌ |
| 4 | Mezcla alfa exacta (0, 128, 255) | `... -m pytest tests/unit/test_overlay_blend.py -q` → exit 0 | ❌ |
| 5 | Determinismo: capturar el frame 50, luego el 200, luego el 50 otra vez → píxeles idénticos | `... -m pytest tests/integration/test_capture_determinism.py -q` → exit 0 | ❌ |
| 6 | Cada componente base, en el frame central de su cue, deja ≥ 1000 píxeles con alfa > 0 dentro de la franja de ancho completo entre `(y-0.1)·H` y `(y+0.1)·H` (con su `y` efectivo) y < 1 % de sus píxeles con alfa fuera de ella; los subtítulos, igual con `captions.y` | `... -m pytest tests/integration/test_components_base.py -q` → exit 0 | ❌ |
| 7 | Render con gráficos: mismo nº de frames; en el frame 60 la caja del título difiere (diferencia media > 2) del render `--no-graphics` | `... -m pytest tests/integration/test_render_graphics.py -q` → exit 0 | ❌ |
| 8 | Lint, formato, tipos | como en S1.1 → exit 0 | ❌ |
| 9 | Endurecimiento de Chromium: `launch` recibe `chromium_sandbox=True` (comprobado con un doble que registra los kwargs) y arranca de verdad en Windows; una página con `<img src="http://127.0.0.1:<puerto>/x.png">` pasada por `capture_stills` produce 0 peticiones al servidor HTTP local del test, mientras una imagen `data:` sí se pinta | `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/integration/test_capture_hardening.py -q` → exit 0 | ❌ |

---

## S1.7 — Componentes de lucimiento (genéricos y parametrizados)

### Parámetros exactos (todos big=no salvo `holo_board`)

| Componente | Parámetros (tipo, default, rango) | Animación (números del piloto) |
|---|---|---|
| `steps` | `items` lista 1–8 de {`at_f` ≥ 0 estrictamente creciente, `label` ≤ 12, `text` ≤ 40} · `y` 0.136 · `badge` accent · `panel` dark · `ring` accent | cada paso visible de su `at_f` al siguiente (o fin del cue) con `pop(in 0.18, out 0.10)`; panel `rgba(dark,.92)` radio 22, anillo 3 px, badge Inter 900 30 px, texto Inter 800 42 px. Se usa sobre un span `screen` |
| `sticker` | `image` path req (manifiesto aprobado) · `w_px` 280 (40–900) · `x` 0.5 · `y` 0.6 (punto de los pies) · `path` lista opcional de {`at_f`, `x`, `y`} interpolación lineal · `enter` `drop` (`drop` o `pop`) · `idle` `bob` (`bob` o `none`) · `exit` `pop` (`none`, `pop`, `fly_to`) · `fly_to` {`x`, `y`, `at_f`} req si exit=fly_to · `glow` true · `glow_color` accent · `sparkles` true · `seed` 7 | `drop`: cae 430 px en 0.24 s con `sx 0.9 sy 1.12`, aplasta 0.12 s (`sx 1+0.24k`, `sy 1−0.28k`), rebote 0.26 s; `pop`: `pop()` estándar; `bob`: `y −= 7·(0.5−0.5cos(6.2·ti))`, `rotateY 18·sin(2.7ti)`, `rotateZ 3·sin(3.6ti)`; `fly_to`: agachado 0.15 s antes de `at_f`, arco de 300 px, giro −360°, escala a 0.4, opacidad a 0 en los últimos 0.12 s; brillo radial bajo los pies y 7 destellos sembrados. **Sin parpadeo** (versión genérica). La posición la decide Claude mirando `kcut frames`; se verifica pintándola con `kcut graphics still` (lección 9) |
| `holo_board` (big) | `label` ≤ 24 "" · `corner_text` ≤ 24 "" · `text` 1–12 req · `type_at_f` ≥ 0 req (cae la última letra) · `type_step_f` 4 (1–15) · `accent_index` (default última; `null` = ninguna) · `born` {x 0.479, y 0.199} · `center` {x 0.5, y 0.448} · `w_px` 860 · `h_px` 500 · `color` `#6FF6FF` · `beams_from` lista 0–2 de {x, y} | crece 0.45 s `outCubic` de `born` a `center`, alto `outBack` 0.42 s desde +0.08, parpadeo los primeros 0.32 s, se colapsa los últimos 0.22 s; rejilla 40 px que corre 32 px/s, barrido 430 px/s, etiqueta aparece en +0.3 s, barra de progreso de +0.3 s a fin−0.5 s en `accent`; letras en `type_at_f − (n−1−i)·type_step_f` con rebote `outBack` 0.16 s y glitch de ±6 px los primeros 0.08 s; cursor parpadea a 5 Hz antes, fijo durante, 4 Hz después; rayos desde `beams_from` a las esquinas, se apagan de +0.15 a +0.65 s |
| `globe` | `x` 0.306 · `y` 0.396 · `r_px` 190 (40–500) · `color` accent · `spin` 1.4 rad/s (0–6) · `tilt` 0.38 (0–1.2) · `dots` 70 (0–200) · `seed` 7 | canvas `2.95·r`, paralelos cada 30° y meridianos cada 30°, cara frontal opaca y trasera al 18 %, halo radial, anillo; `pop(in 0.4, out 0.2)` + giro de −90° a 0 en 0.5 s `outCubic` |

### Archivos

#### `src/kcut/gfx/web/components/steps.js`, `sticker.js`, `holo_board.js`, `globe.js` — CREAR
Según la tabla, con las reglas JS de S1.6 (el globo usa canvas 2D; los destellos y rayos, SVG creado
con `createElementNS` y `setAttribute`).

#### `src/kcut/gfx/components.py` — MODIFICAR
Registrar los 4 con sus `ParamSpec`. `sticker.image` → `assets.image_data_uri` (GateError 5 si no está aprobado).

#### `tests/fixtures/synth_graphics.py` — MODIFICAR
Con `with_showpieces=True` agrega: `pasos` steps 210–270 (3 pasos en 0, 20, 40), `mascota` sticker
180–210 con `recursos/logo.png` (`exit fly_to` a {0.3, 0.4, at_f 20}), `holo` holo_board 270–315
`text "HOLA"`, `type_at_f 30`, `mundo` globe 280–315. Crea `recursos/logo.png` (256×256 RGBA círculo)
y su entrada en el manifiesto con `approved_by "test"`.

### Criterios de aceptación S1.7

| # | Tiene que cumplirse | Se comprueba con | Estado |
|---|---|---|---|
| 1 | Validación de parámetros (rangos, `fly_to` obligatorio con exit=fly_to, `at_f` crecientes) | `... -m pytest tests/unit/test_components_params.py -q` → exit 0 | ❌ |
| 2 | Stills en el frame central del cue: steps (≥ 1000 px con alfa en la franja `(y±0.05)·H`); sticker (≥ 1000 px con alfa en el cuadrado de lado `2·w_px` centrado en `(x·W, y·H)`); holo (≥ 5000 px con alfa en el rectángulo `w_px×h_px` centrado en `center`, tras `type_at_f` hay píxeles del color `accent` ±10 dentro de él); globe (≥ 2000 px con alfa dentro del círculo de radio `1.5·r_px` y < 1 % fuera) | `... -m pytest tests/integration/test_components_showpiece.py -q` → exit 0 | ❌ |
| 3 | Sticker con imagen sin `approved_by` → `kcut graphics check` exit 5 | mismo archivo (caso `test_sticker_unapproved_exit5`) → passed | ❌ |
| 4 | Determinismo del sticker y el holo (mismo frame dos veces = mismos píxeles) | mismo archivo (caso `test_showpiece_deterministic`) → passed | ❌ |
| 5 | Lint, formato, tipos, reglas JS | como en S1.1 + `tests/unit/test_gfx_js_rules.py` → exit 0 | ❌ |

---

## S1.8 — Audio: voz, SFX sintetizados, música, ducking, loudness

### Formato `edit/sfx.json`

```json
{"schema": "kcut.sfx/1", "bus_gain_db": 0.0,
 "events": [
  {"type": "boom", "at": 0},
  {"type": "whoosh", "at": 30, "dur_f": 14, "align": "center", "seed": 2},
  {"type": "pop", "at": {"word": "a1:w0031", "edge": "start", "offset_f": 0}, "freq": 700},
  {"type": "riser", "at": 210, "dur_f": 15, "align": "end"},
  {"type": "typing", "at": 285, "dur_f": 25, "gain": 0.85}
 ],
 "windows": [{"start": 210, "end": 270, "gain_db": 4.0}]}
```
- `at`: frame de salida o ancla (mismas reglas de S1.6). `align` ∈ `start` (default), `center`,
  `end` → la muestra 0 / la del medio / la última cae en `at_f·spf`; lo que quede antes de 0 se recorta.
- `gain` lineal 0–2 (default por tipo), `seed` int ≥ 0, `freq` (solo pop) 100–4000 Hz.
- **Sin normalización global del bus** (lección 10): el nivel se ajusta con `gain`, `bus_gain_db`
  (−24 a +12) y `windows` (`gain_db` −24 a +12, rampas de 10 ms).

Biblioteca (port exacto de `piloto/audio.py`, determinista por semilla; largo en muestras =
`dur_f·spf` cuando el tipo usa duración):

| type | dur_f | params | gain default | para qué |
|---|---|---|---|---|
| `whoosh` | default `round(0.45·fps)` | seed | 0.45 | cambio de plano, entrada de gráfico |
| `boom` | fijo 0.9 s | — | 0.75 | golpe de gancho o cierre |
| `pop` | fijo 0.12 s | freq 820 | 0.6 | aparición de texto |
| `shimmer` | default `round(1.1·fps)` | — | 0.6 | brillo, revelación |
| `key` | fijo 0.05 s | seed | 0.6 | tecla suelta |
| `click` | fijo 0.06 s | — | 0.7 | clic de interfaz |
| `kick` | fijo 0.32 s | — | 0.9 | bombo para beat |
| `hat` | fijo 0.045 s | seed | 0.95 | hi-hat |
| `pad` | requerido | — | 0.55 | colchón armónico corto |
| `typing` | requerido | rate 13.0 (4–25) | 0.85 | tecleo |
| `riser` | requerido | — | 0.45 | subida antes de un golpe |
| `blip8` | fijo 0.22 s | — | 0.7 | arpegio 8-bit |
| `powerup` | fijo 0.55 s | — | 0.7 | aparición mágica |

### Formato `edit/music.json`

```json
{"schema": "kcut.music/1", "mode": "synth", "gain_db": -8.0,
 "synth": {"bpm": 120, "progression": ["Am", "F", "C", "G"], "drums": true,
           "mute_drums": [{"start": 210, "end": 270}], "stop_drums_f": 330, "origin_f": 0},
 "file": null,
 "duck": {"enabled": true, "threshold": 0.03, "ratio": 10.0, "attack_ms": 15, "release_ms": 350,
          "makeup": 1.0, "knee": 2.828},
 "windows": [{"start": 0, "end": 30, "gain_db": 3.0}]}
```
- `mode` ∈ `synth`, `file`, `none`. `gain_db` −40 a +6.
- `synth`: `bpm` 60–180; `progression` 1–16 acordes con raíz ∈ {C C# Db D D# Eb E F F# Gb G G# Ab A A# Bb B}
  y sufijo opcional `m`; `drums` bool; `mute_drums` ventanas en frames; `stop_drums_f` opcional;
  `origin_f` ≥ 0 (desfase de la rejilla).
- `file`: `{"path": "recursos/musica/tema.mp3", "src_in_f": 0, "loop": false, "fade_in_f": 0, "fade_out_f": 36}`
  (path aprobado en el manifiesto; si no → exit 5).
- `duck`: rangos `threshold` 0.001–1, `ratio` 1–20, `attack_ms` 1–200, `release_ms` 10–2000,
  `makeup` 1–4, `knee` 1–8.
- Sin `edit/music.json` = `mode: none`. Sin `edit/sfx.json` = sin SFX.

### Archivos

#### `src/kcut/audio/sfx_synth.py` — CREAR
Port de las 13 funciones de `piloto/audio.py` con firma `(n: int, sr: int, **params) -> NDArray[np.float32]`
(`n` = muestras), mismas fórmulas y semillas (`whoosh` usa `seed`, `boom` semilla 7, `key` 100+seed,
`hat` 300+seed, `typing` 55, `riser` 77). Sin aleatoriedad global.

#### `src/kcut/audio/sfx_library.py` — CREAR
`SFX: Mapping[str, SfxDef]`, `SfxDef(id, fn, fixed_s: float | None, default_dur_s: float | None, requires_dur: bool, params: tuple[ParamSpec, ...], default_gain, name_es, purpose_es, avoid_es, cost)`.

#### `src/kcut/audio/sfx_schema.py`, `music_schema.py` — CREAR
`parse_sfx(data, ...)`, `parse_music(data, ...)` con las reglas de arriba → `(doc | None, list[Issue])`.

#### `src/kcut/audio/gain.py` — CREAR (puro)
`apply_gain_windows(x, windows: list[tuple[int, int, float]], spf, sr, ramp_ms=10) -> NDArray` (dB → lineal,
rampas lineales en ambos bordes, fuera de ventanas ganancia 1).

#### `src/kcut/audio/sfx_bus.py` — CREAR (puro)
`build_sfx_bus(events_resolved, total: int, spf, sr) -> NDArray[np.float32]`: suma en float32, sin normalizar.

#### `src/kcut/audio/chords.py` — CREAR (puro)
`parse_chord(sym) -> tuple[int, tuple[int, int, int]]`: bajo = raíz en MIDI dentro de `[40, 51]`;
tríada mayor (0, 4, 7) o menor (0, 3, 7), cada nota movida por octavas a `[55, 66]`. (`Am` → bajo 45,
notas (57, 60, 64)).

#### `src/kcut/audio/music_synth.py` — CREAR (port de `piloto/music.py`)
`synth_music(cfg, total: int, fps, sr) -> NDArray`: `BEAT = 60/bpm`, `BAR = 4·BEAT`, origen en
`origin_f`; pad (sierras desafinadas ±0.07 semitonos, ataque 0.18 s, pasa-bajos 1100 Hz), bajo
(tiempos 1 y 3 + anticipación en el "y" del 4), arpegio de corcheas en triangular una octava arriba
(pasa-bajos 3200 Hz), batería (bombo en 1 y 3, hi-hat a contratiempo) callada si
`start_s − 0.05 <= t < end_s` de alguna `mute_drums` o `t >= stop_drums_f/fps`; fundido final 1.2 s,
pasa-altos 35 Hz, pico a 0.9. Largo exacto `total`.

#### `src/kcut/audio/music_file.py` — CREAR
`load_music_file(project, cfg, total, spf) -> NDArray`: decodifica con ffmpeg a `-f f32le -ac 1 -ar 48000`
(stdout), toma desde `src_in_f·spf`, `loop` repite, si no rellena con ceros (aviso), fundidos lineales.

#### `src/kcut/audio/loudnorm.py` — CREAR
`pass1_args(ffmpeg, src_f32, I, TP, LRA) -> list[str]` (`-f f32le -ar 48000 -ac 1 -i src -af loudnorm=I=..:TP=..:LRA=11:print_format=json -f null -`),
`parse_pass1(stderr: str) -> LoudnormMeasure | None` (último bloque `{...}`; `input_i` = `"-inf"` o
< −60 → `None` = silencio, no se normaliza y se avisa),
`pass2_args(ffmpeg, src, dst, I, TP, LRA, m) -> list[str]` (`measured_I/TP/LRA/thresh`, `offset`,
`linear=true`, `print_format=summary`, `,aresample=48000`, salida `-f f32le -ar 48000 -ac 1 dst`).
`normalize(project, src, dst, I, TP) -> None`.

#### `src/kcut/audio/mix_graph.py` — CREAR (puro; lección 11)
`build_graph(has_music: bool, duck: bool, duck_cfg) -> tuple[str, int]` (filter_complex, nº de entradas):
- voz + música + duck: `[0:a]asplit=2[vm][vs];[1:a][vs]sidechaincompress=threshold=T:ratio=R:attack=A:release=Rl:makeup=M:knee=K[md];[vm][md][2:a]amix=inputs=3:normalize=0:duration=first:dropout_transition=0[mix]`
- voz + música sin duck: `[0:a][1:a][2:a]amix=inputs=3:normalize=0:duration=first:dropout_transition=0[mix]`
- sin música: `[0:a][1:a]amix=inputs=2:normalize=0:duration=first:dropout_transition=0[mix]`
Regla verificada por test: toda salida de `asplit` se consume; si alguna sobrara, va a `anullsink`.
`duck_only_graph(duck_cfg) -> str` (para el test de ducking: salida `[md]`).

#### `src/kcut/audio/mixer.py` — CREAR
`mix(project, edl, version, progress) -> Path`, en `.kcut/build/vN/`:
1. `voice_raw.f32` (de `build_voice`; se recalcula siempre, es barato).
2. Cadena de voz con ffmpeg: `highpass=f=HP,afftdn=nr=NR:nf=NF,acompressor=threshold=<lineal de comp_threshold_db>:ratio=R:attack=10:release=150:makeup=1`
   → `voice_chain.f32` → loudnorm 2 pasadas a `voice_lufs` con TP −2.0 → `voice.f32`.
3. Música (`synth` o `file`) → `gain_db` + `windows` → `music.f32`.
4. SFX → `bus_gain_db` + `windows` → `sfx.f32`.
5. `build_graph` → `mix_pre.f32` → loudnorm 2 pasadas a `target_lufs` / `target_tp` → `mix.f32`.
6. Tras **cada** paso de ffmpeg se ajusta el largo a exactamente `frames·spf` (rellenar ceros o
   recortar); diferencia > `spf` → `InternalError`.
7. `mix.wav` (s16le mono 48 kHz) desde `mix.f32`.

#### `src/kcut/commands/mix.py` — CREAR
`kcut mix [--edl]` (lock `build-vN`; gate no requerido). `--json` →
`{"ok": true, "mix": ".kcut/build/v1/mix.wav", "samples": 552000, "voice_lufs": -16.1, "mix_I": -14.0, "mix_TP": -1.6, "sfx_events": 9, "music": "synth"}`
(`voice_lufs`, `mix_I`, `mix_TP` medidos con `ebur128=peak=true` sobre `voice.f32` y `mix.wav`).

#### `src/kcut/cli.py` — MODIFICAR (agregar `mix`)

#### `tests/fixtures/synth_audio.py` — CREAR
`write_audio_plans(root)`: `edit/sfx.json` = el ejemplo de arriba con `at` enteros + kick/hat
alternos cada 8 frames entre 210 y 270; `edit/music.json` = el ejemplo de arriba.

### Criterios de aceptación S1.8

| # | Tiene que cumplirse | Se comprueba con | Estado |
|---|---|---|---|
| 1 | SFX deterministas (misma semilla = mismos bytes), largos exactos, finitos, pico ≤ 1 | `... -m pytest tests/unit/test_sfx_synth.py -q` → exit 0 | ❌ |
| 2 | Bus: evento en el frame f empieza en la muestra `f·1600` (start/center/end); sin normalización global | `... -m pytest tests/unit/test_sfx_bus.py tests/unit/test_gain.py -q` → exit 0 | ❌ |
| 3 | Acordes y música sintética: largo exacto, batería callada en `mute_drums` (energía < 5 % del resto en esa banda) | `... -m pytest tests/unit/test_chords.py tests/unit/test_music_synth.py -q` → exit 0 | ❌ |
| 4 | Parser de loudnorm (normal, `-inf`), grafo sin salidas colgando, esquemas de sfx/music | `... -m pytest tests/unit/test_loudnorm_parse.py tests/unit/test_mix_graph.py tests/unit/test_audio_schemas.py -q` → exit 0 | ❌ |
| 5 | Ducking: con voz a ráfagas, la música baja ≥ 10 dB RMS mientras hay voz | `... -m pytest tests/integration/test_ducking.py -q` → exit 0 | ❌ |
| 6 | `kcut mix` sintético: `mix.wav` de 552000 muestras; ebur128 sobre el wav I ∈ [−14.5, −13.5] y TP ≤ −1.0 | `... -m pytest tests/integration/test_mix_synth.py -q` → exit 0 | ❌ |
| 7 | Música de archivo sin aprobar → exit 5 | mismo archivo (caso `test_music_file_unapproved`) → passed | ❌ |
| 8 | Lint, formato, tipos | como en S1.1 → exit 0 | ❌ |

---

## S1.9 — `kcut qa` + `kcut build` + `kcut catalog` + e2e sintético

### Formato `qa/vN/report.json`

```json
{"schema": "kcut.qa/1", "video": "salida/v1.mp4", "edl": "qa/v1/inputs/edl-v1.json",
 "generated": "2026-10-16T12:00:00", "verdict": "pass",
 "checks": [
  {"id": "frames", "status": "pass", "value": 345, "expected": 345},
  {"id": "video_stream", "status": "pass", "value": {"codec": "h264", "size": "1080x1920", "fps": "30/1", "color_space": "bt709"}},
  {"id": "audio_stream", "status": "pass", "value": {"codec": "aac", "sample_rate": 48000, "channels": 2}},
  {"id": "av_delta", "status": "pass", "value_ms": 0.0, "max_ms": 25},
  {"id": "loudness", "status": "pass", "I_LUFS": -14.2, "TP_dBTP": -1.4, "LRA": 4.1, "target": -14.0, "tolerance": 1.0, "max_tp": -1.0},
  {"id": "black", "status": "pass", "intervals": [{"start_f": 0, "end_f": 12, "expected": true}]},
  {"id": "freeze", "status": "pass", "intervals": [{"start_f": 318, "end_f": 345, "expected": true}]},
  {"id": "transcript", "status": "pass", "match": 0.86, "min": 0.80, "language": "es",
   "expected_words": 120, "heard_words": 118,
   "diffs": [{"op": "replace", "expected": "aqui", "heard": "y", "at_f": 1020, "at_display": "00:34.0"}]}
 ],
 "file_mb": 4.1, "duration_display": "00:11.5", "contact_sheet": "qa/v1/contact.jpg",
 "timings_s": {"probe": 1.1, "loudness": 0.8, "detect": 2.0, "transcript": 14.0, "contact": 0.6}}
```
`status` ∈ `pass fail skipped` (con `reason_es` si skipped). `verdict`: `fail` si algún check falla;
`incomplete` si ninguno falla y alguno se saltó; si no `pass`. Exit: `fail` → 1, resto → 0.

Checks y umbrales (`[qa]` de `kcut.toml`):
- `frames`: ffprobe `-count_frames` `nb_read_frames` == `edl.frames`.
- `video_stream`: h264, tamaño del preset, `r_frame_rate == "<fps>/1"`, `color_space bt709`.
- `audio_stream`: aac, 48000, 2 canales.
- `av_delta`: `|dur_audio − dur_video| ≤ max_av_delta_ms`.
- `loudness`: `ebur128=peak=true` (último bloque `Summary`), `|I − target_lufs| ≤ lufs_tolerance`, `TP ≤ max_tp`.
- `black`: `blackdetect=d=0.15:pix_th=0.06`; intervalo esperado si ≥ 80 % de sus frames cae en spans
  `color` con luma ≤ 0.12 (`0.2126R+0.7152G+0.0722B` normalizado) o en zonas de fade; algún
  intervalo no esperado → fail.
- `freeze`: `freezedetect=n=0.002:d=0.6`; esperado si cae (≥ 80 %) en spans `color`, `screen` o
  `broll`; congelado dentro de un `cam` → fail.
- `transcript`: esperadas = **todas** las palabras conservadas del EDL (`map_words`, con correcciones,
  incluidas las tapadas por gráficos); oídas = Whisper sobre el audio del render (idioma = el más
  frecuente entre los clips de voz; caché por hash del wav); `norm_token` a ambos lados;
  `difflib.SequenceMatcher(autojunk=False)`; `match = ratio ≥ min_transcript_match`. Modelo ausente,
  sin palabras esperadas o render con I < −50 LUFS → `skipped`.
- Hoja de contacto `qa/vN/contact.jpg`: un frame cada 2 s, 216×384 (9:16) o 384×216 (16:9),
  13 columnas, rótulo Pillow con `mm:ss.s` y frame (sin `drawtext`).

### Formato `kcut catalog --json` (D8: única fuente de verdad)

```json
{"schema": "kcut.catalog/1", "engine_version": "0.1.0",
 "items": [
  {"category": "graphic", "id": "title", "name_es": "Titulo grande",
   "purpose_es": "Nombra la marca o la idea clave en la palabra que la dice",
   "avoid_es": "No lo uses sobre una cara en primer plano ni dos veces seguidas",
   "status": "available", "since": "S1.6", "cost": "bajo",
   "cost_note_es": "captura HTML ~55 ms por frame mientras esta en pantalla",
   "params": [{"name": "text", "kind": "str", "required": true, "default": null, "lo": null, "hi": null, "help_es": "texto del titulo"}]},
  {"category": "camera", "id": "face_follow", "name_es": "Reencuadre siguiendo la cara",
   "purpose_es": "Mantener la cara centrada en 9:16", "avoid_es": "Todavia no existe",
   "status": "planned", "since": "F2", "cost": "medio", "cost_note_es": "", "params": []}
 ]}
```
Categorías: `graphic`, `look`, `sfx`, `music`, `camera`, `transition`, `workflow`. `cost` ∈ `bajo medio alto`.
Disponibles en 001: graphic {`captions`, `title`, `label`, `kinetic`, `endcard`, `steps`, `sticker`,
`holo_board`, `globe`} · look {los 6} · sfx {los 13} · music {`synth`, `file`, `none`} · camera
{`zoom`, `push`, `reframe` (cx/cy/anchor), `screen_card`, `broll_push`, `color_card`} · transition
{`cut`, `fade_black`} · workflow {`qa`; `storyboard` lo agrega S1.10}. Planeados: camera
{`face_follow` F2, `hand_track` F2, `privacy_blur` F2}, transition {`crossfade` F2, `whip` F2},
graphic {`lower_third` F2, `matte_captions` F2}, music {`beat_cut` F4}.

### Archivos

#### `src/kcut/qa/streams.py`, `loudness.py`, `detect.py`, `transcript_diff.py` — CREAR (parsers puros + llamadas)
`parse_probe(data, edl, cfg) -> list[Check]`; `parse_ebur128(stderr) -> tuple[float, float, float]`
(último `Summary:`; `I:`, `Peak:` del bloque true peak, `LRA:`); `parse_black(stderr, fps)`,
`parse_freeze(stderr, fps)` → intervalos en frames (`round(t·fps)`), `classify_intervals(intervals, edl, kind)`;
`diff_transcript(expected: list[KeptWord], heard: list[str]) -> TranscriptDiff`.

#### `src/kcut/qa/contact.py`, `report.py`, `run.py` — CREAR
`run_qa(project, video_rel, edl_rel | None, progress) -> QaReport`; si no viene `--edl`, se infiere
`vN` del nombre `salida/vN.mp4` y se usa `qa/vN/inputs/edl-vN.json` si existe, si no `edit/edl-vN.json`.

#### `src/kcut/pipeline/snapshot.py` — CREAR
`snapshot_inputs(project, version) -> Path`: copia a `qa/vN/inputs/` los que existan de
`edit/edl-vN.json`, `edit/graphics.json`, `edit/sfx.json`, `edit/music.json`, `edit/correcciones.json`,
`edit/estrategia.md`, `kcut.toml`, y escribe `inputs.json` con el sha256 de cada uno.

#### `src/kcut/pipeline/build.py` — CREAR
`run_build(project, edl_rel, *, skip_qa: bool, force: bool, progress) -> BuildResult`: lock `build-vN`
→ `salida/vN.mp4` existe y no hay `--force` → `ProjectError` → gate (5) → `edl check` (1) →
`validate_manifest` (errores → 1) → gráficos (resolve + capture) → render de video con overlay (sin el
`render.mp4` de revisión) → `mix` → mux (`audio_f32=False`, desde `mix.wav`) a `salida/vN.partial.mp4` → `atomic_replace` → snapshot → qa (si no `--skip-qa`).
Tiempos por paso en el reporte y en el log. El lock lo toman los comandos (`render`, `mix`,
`build`, `graphics capture`); las funciones internas que `build` llama no lo vuelven a pedir.

#### `src/kcut/catalog/model.py`, `static_items.py`, `planned.py`, `collect.py` — CREAR
`CatalogItem` (campos del JSON). `collect() -> list[CatalogItem]` arma: gráficos desde
`gfx/components.py` (+ `captions`), looks desde `render/looks.py`, sfx desde `audio/sfx_library.py`,
música (`static_items`), cámara y transición (`static_items`, cada uno con `edl_field` que debe
existir en `edl/model.py`), workflow (`static_items`), planeados (`planned.py`). Ids únicos por categoría.

#### `src/kcut/commands/qa.py`, `build.py`, `catalog.py` — CREAR
`kcut catalog [--category C]`: no requiere proyecto; humano = tabla por categoría
(`[disponible] graphic/title - Titulo grande - costo bajo - <para qué>`).

#### `src/kcut/cli.py` — MODIFICAR (agregar `qa`, `build`, `catalog`)

#### `tests/fixtures/synth_project.py` — CREAR
`make_project(root) -> ProjectTruth`: `kcut new` + `make_media` + `kcut ingest` + `kcut transcribe`
(si hay modelo) + `write_edl_v1` + `write_graphics_v1(with_showpieces=True)` + `write_audio_plans`;
en el `kcut.toml` del sintético `min_transcript_match = 0.5`. Ejecutable para revisión humana:
`.venv/Scripts/python.exe -X utf8 -m tests.fixtures.synth_project "<carpeta>"` (sin `-I`, para que `-m`
encuentre `tests`).

### Criterios de aceptación S1.9

| # | Tiene que cumplirse | Se comprueba con | Estado |
|---|---|---|---|
| 1 | Parsers de QA (ffprobe, ebur128, blackdetect, freezedetect) y clasificación esperado/no esperado | `... -m pytest tests/unit/test_qa_streams.py tests/unit/test_qa_loudness.py tests/unit/test_qa_detect.py -q` → exit 0 | ❌ |
| 2 | Diff de transcripción contra todas las palabras conservadas (una palabra tapada por un gráfico NO cuenta como diferencia si se oye) | `... -m pytest tests/unit/test_transcript_diff.py -q` → exit 0 | ❌ |
| 3 | Catálogo: ids únicos, todo `available` tiene implementación (JS registrado, cadena de look, función de SFX, campo de EDL), todo lo implementado está en el catálogo | `... -m pytest tests/unit/test_catalog.py -q` → exit 0 | ❌ |
| 4 | `kcut catalog --json` fuera de un proyecto | `.venv/Scripts/python.exe -I -X utf8 -m kcut catalog --json` → exit 0, `"schema": "kcut.catalog/1"` | ❌ |
| 5 | **E2E**: `kcut build` sintético crea `salida/v1.mp4`; reporte con `frames` 345, `av_delta` ≤ 25 ms, I ∈ [−15, −13], TP ≤ −1.0, `black` y `freeze` pass, `transcript` pass (≥ 0.5) o skipped sin modelo; `verdict` ∈ {pass, incomplete} | `... -m pytest tests/e2e/test_build_synth.py -q` → exit 0 | ❌ |
| 6 | Build se niega a pisar `salida/v1.mp4` sin `--force` (exit 3) y sin aprobación (exit 5) | mismo archivo (casos `test_build_no_overwrite`, `test_build_gate`) → passed | ❌ |
| 7 | Snapshot de entradas con sha256 en `qa/v1/inputs/inputs.json` | mismo archivo (caso `test_snapshot`) → passed | ❌ |
| 8 | Suite completa con cobertura ≥ 70 % | `.venv/Scripts/python.exe -I -X utf8 -m pytest --cov=kcut --cov-report=term-missing --cov-fail-under=70` → exit 0 | ❌ |
| 9 | Lint, formato, tipos | como en S1.1 → exit 0 | ❌ |

---

## S1.10 — `kcut storyboard` (Puerta 1 visual)

Objetivo del slice: desde un EDL **borrador** (sin aprobación) + `graphics.json` + `sfx.json` +
`music.json`, antes de cualquier render completo, generar `edit/storyboard.html` (autocontenido, abre
sin internet) y `qa/storyboard.png` (hoja que Claude puede leer). Es lo que el dueño mira para
aprobar. No usa mezzanines ni renderiza el video.

### Reglas

- Requisitos: inventario con proxies de los clips usados. El EDL debe pasar `edl check` sin errores
  (avisos OK). Transcripciones, gráficos, sfx y música son opcionales (si faltan, el panel lo dice).
  **No** exige `aprobado: si`; el HTML muestra "BORRADOR - estrategia sin aprobar" o "Estrategia aprobada".
- Beats (`storyboard/beats.py`, puro): se recorren los spans en orden; un span con
  `dur_f < ms_to_f_round(min_beat_ms, fps)` se une al beat anterior; si es el primero, se une al
  siguiente. Span representativo del beat = el más largo (empate: el primero). Frame del panel =
  `rep.at_f + rep.dur_f // 2`. `--min-beat-ms` pisa `[storyboard] min_beat_ms`.
- Imagen del panel (`storyboard/panel.py`): frame de fuente del span representativo en el frame del
  panel según `span_source_frames`, leído del **proxy** con `grab()` y el look del span; misma
  geometría del render (`cam_crop`, `broll_crop`, `screen_frame`, color, fade) a tamaño de salida;
  encima el still de gráficos de ese frame (`capture_stills`, una sola sesión de Chromium para
  todos los paneles) con `alpha_blend`; se reduce al ancho del panel. Lecturas de proxy en paralelo
  con `ThreadPoolExecutor(max_workers=min(4, os.cpu_count()))`.
- Textos del panel (`storyboard/notes.py`, puro): timecode `mm:ss.s → mm:ss.s (X.X s · fA-fB)`;
  etiqueta de cámara (`a1 · zoom 1.30 · cx 0.40 · look calido`, `pantalla b1`, `b-roll b1 · push 0.07`,
  `color #0B0B0E`; con varios spans: `a1 → b1 (0.4 s) → a1`); lo que se dice = palabras conservadas
  del beat unidas (o "(sin transcripcion)"); gráficos activos en el beat (`title: Higgsfield 01.3-02.6`);
  SFX del beat (`whoosh @01.0`); música (`synth 120 bpm · ducking`, ventanas que tocan el beat).
- HTML (`storyboard/html.py`, puro): cabecera (nombre, versión, duración, preset, fps, nº de paneles,
  fecha, estado de la estrategia), un `<section class="panel">` por beat con `<img>` JPEG calidad 80
  en data URI, `<h3>` timecode y las notas; todo texto con `html.escape`; CSS en línea; sin JS ni
  recursos externos.
- PNG (`storyboard/sheet.py`, DS15): 9:16 → 6 columnas de 300 px (panel 300×533), 16:9 → 4 columnas
  de 456 px (panel 456×256); bloque de texto de 180 px bajo cada panel (fuente Pillow tamaño 20,
  hasta 6 líneas, ajuste por ancho); margen 16 px; franja de cabecera de 60 px; máximo 12 paneles
  por página: `qa/storyboard.png`, `qa/storyboard-p2.png`, ...
- Barato: sin mezzanines, sin render; meta < 60 s para un video de ~60 s en la laptop de referencia.

`kcut storyboard --json`:
```json
{"schema": "kcut.storyboard/1", "ok": true, "edl": "edit/edl-v1.json", "approved": false,
 "html": "edit/storyboard.html", "png": ["qa/storyboard.png"], "elapsed_s": 14.2,
 "panels": [{"index": 0, "at_f": 0, "dur_f": 30, "frame_f": 15, "spans": [0], "label": "color #0B0B0E",
             "say": "", "gfx": ["kinetic:gancho"], "gfx_alpha_px": 41230, "sfx": ["boom @00.0"],
             "music": "synth 120 bpm · ducking"}]}
```

### Archivos

#### `src/kcut/storyboard/beats.py`, `notes.py`, `panel.py`, `html.py`, `sheet.py`, `run.py` — CREAR
Según las reglas. `run_storyboard(project, edl_rel, min_beat_ms: int | None, progress) -> StoryboardResult`.

#### `src/kcut/commands/storyboard.py` — CREAR
`kcut storyboard [--edl EDL] [--min-beat-ms MS]`. Errores del EDL → exit 1.

#### `src/kcut/catalog/static_items.py` — MODIFICAR
Agregar `workflow/storyboard` (`available`, `since S1.10`, costo bajo, "< 1 min para ~60 s de video",
para qué: "ver el corte cuadro por cuadro antes de aprobar la estrategia", cuándo no: "no sustituye
ver el render final").

#### `src/kcut/cli.py` — MODIFICAR (agregar `storyboard`)

### Criterios de aceptación S1.10

| # | Tiene que cumplirse | Se comprueba con | Estado |
|---|---|---|---|
| 1 | Beats: spans cortos se unen al anterior (o al siguiente si es el primero), representativo y frame del panel correctos | `... -m pytest tests/unit/test_beats.py -q` → exit 0 | ❌ |
| 2 | Notas y HTML: escapado de `<script>` en textos, N `<section class="panel">`, sin `http`/`src="file` | `... -m pytest tests/unit/test_storyboard_notes.py tests/unit/test_storyboard_html.py -q` → exit 0 | ❌ |
| 3 | Sintético: 7 paneles (= 7 spans), `edit/storyboard.html` y `qa/storyboard.png` existen; PNG de 1912 px de ancho y alto entre 600 y 1600 | `... -m pytest tests/e2e/test_storyboard_synth.py -q` → exit 0 | ❌ |
| 4 | Gráficos presentes donde hay cues: con el graphics.json sintético todos los paneles tienen `gfx_alpha_px > 0`; con un graphics.json de un solo cue (span 2) y captions apagados, solo el panel 2 | mismo archivo (caso `test_gfx_presence`) → passed | ❌ |
| 5 | Funciona sin aprobación y sin crear mezzanines (`.kcut/mezz/` sin archivos nuevos) | mismo archivo (caso `test_no_gate_no_mezz`) → passed | ❌ |
| 6 | Barato: `elapsed_s` < 60 en el sintético | mismo archivo (caso `test_fast`) → passed | ❌ |
| 7 | Catálogo incluye `workflow/storyboard` disponible | `.venv/Scripts/python.exe -I -X utf8 -m kcut catalog --json --category workflow` → exit 0 y contiene `"id": "storyboard"` | ❌ |
| 8 | `kcut render` sigue negándose sin `aprobado: si` aunque exista storyboard | caso `test_render_still_gated` en el mismo archivo → passed | ❌ |
| 9 | Lint, formato, tipos y suite completa | `ruff check`, `ruff format --check`, `mypy`, `pytest` completo → exit 0 | ❌ |

---

## Tests (plan global)

Obligatorios por §9 (lógica con reglas, validadores, parsers, seguridad de rutas): EDL
(modelo/validación/mapeo), sync, chunks y mapeo palabra→salida, loudness, detectores de QA,
validación de rutas, constructores de argumentos de ffmpeg, correcciones, manifiesto, catálogo.

- `tests/unit/`: puros, sin ffmpeg ni Chromium, < 5 s cada uno. Corren con
  `.venv/Scripts/python.exe -I -X utf8 -m pytest tests/unit -q`.
- `tests/integration/`: con marcadores `ffmpeg`, `chromium`, `whisper`, `flite`; skip limpio si falta
  la herramienta (el skip se ve en `-ra`).
- `tests/e2e/`: `@pytest.mark.e2e @pytest.mark.slow @pytest.mark.timeout(900)`; usan el proyecto
  sintético de sesión (en una ruta con espacio y ñ).
- Datos: nada de footage real en el repo. Todo medio se genera en tiempo de test con lavfi
  (`testsrc2`, `aevalsrc`, `anoisesrc`, `flite`) y Pillow. `tests/data/` solo trae JSON de ffprobe a mano.
- Verificación en vivo (no automática, para el dueño, tras S1.10): generar el sintético con
  `tests.fixtures.synth_project`, abrir `edit/storyboard.html` en el navegador y `salida/v1.mp4` en
  un reproductor; Claude lee `qa/storyboard.png` y `qa/v1/contact.jpg`.
- Un test que no se corrió no cuenta (R1): cada criterio se cierra pegando la salida real.

## Rendimiento esperado (laptop de referencia; informativo salvo donde un criterio lo fija)

| Paso | Medido en el piloto | Esperado en kcut |
|---|---|---|
| Transcribir (medium, CPU int8) | 131 s en 96 s (0.73× tiempo real) | ≤ 0.8× tiempo real; caché = 0 s |
| Tone-map HDR→SDR | 68 s × 2 cámaras a 1440×2560 en ~11 min (~4.9× la duración) | proxies 540×960 ≤ 2× la duración del clip; mezzanines solo de los tramos usados (≈ +35 % de píxeles con zoom 1.55) |
| Componer la base | 1469 frames en ~2 min | similar, ahora con overlay en el mismo paso |
| Capturar gráficos | 1469 PNG en 72–86 s (~18 fps) | ~55 ms por frame, solo frames activos |
| Encode final (x264 slow CRF 18) | ~1 min 45 s | dentro del render (un solo encode) |
| Storyboard | no existía | < 60 s para ~60 s de video (criterio en el sintético) |
| Doctor | — | < 60 s (incluye lanzar Chromium) |

## FUERA de alcance

- Spec 002: plugin de Claude Code (marketplace, skill, agentes, comandos `/korvexcut:*`), entrevista
  de intake, menú de ideas (su UI; aquí solo `kcut catalog`), lógica del agente buscador de assets
  (aquí solo el formato del manifiesto), prueba de aceptación con un segundo video real, lectura de
  `perfil.md`/`marca.js` de Korvex Motion.
- F2+: rastreo de manos (`piloto/track.py`), detección de caras (YuNet/MediaPipe), reencuadre
  automático, matting, blur de privacidad, crossfade y transiciones animadas, lower thirds.
- F3–F5: audio externo con limpieza avanzada, mezcla estéreo real, montaje a BPM, puntuación de clips
  por visión, variantes de formato, SRT, póster, preview para WhatsApp.
- ElevenLabs Scribe o cualquier servicio de pago; export a NLE (FCPXML/OTIO/EDL CMX).
- Compensar deriva de reloj entre cámaras (solo se **detecta**); elegir pista de audio
  (`--audio-track`); Dolby Vision perfil 5 (solo aviso).
- Tocar `piloto/`, `videoi/`, `README.md`, `HANDOFF.md`, `PROGRESO.md`, `docs/piloto/`, `docs/research/`
  (la documentación la actualiza el `sdd-archiver`). Nada de dependencias fuera de 0.12.
- Remotion, HyperFrames, libplacebo/Vulkan, `cv2.CascadeClassifier` (descartados, R6).

## Preguntas que bloquean

Ninguna. Las decisiones que tomé para cerrar huecos están en la tabla DS1–DS15 (0.13); si el dueño
cambia alguna en el gate, se ajusta el spec antes de arrancar S1.1.

## Cambios

### 001.1 — 16/10/2026 — parche tras revisión de S1.1 (aprobado por Yedin)

S1.1 se reabre: el criterio 1 cambió y los criterios 9–17 son nuevos. S1.2 suma los criterios
12–14 y S1.6 el 9. El resto del spec no cambia.

1. **Regex de filtros** (S1.1 `doctor/ffmpeg_caps.py`): `[T.][S.]C?` → `[T.][S.][C.]?`. Acepta
   ffmpeg 7.x (tres banderas) y 8.x (dos). Con la anterior, un ffmpeg n7.1 real listaba 42 filtros y
   se leían 10. El mínimo sigue en ffmpeg 7 (decisión del dueño). Tests con líneas reales de 7.1 y 8.x.
2. **Regex de encoders** (S1.1): el grupo `(\S+)` pasa a `([^\s=]\S*)` para no contar las líneas de
   leyenda (`V..... = Video` agregaba `=`). Tests con igualdad exacta de conjuntos y un caso de leyenda.
3. **`proc.tool_path`** (§0.5, §0.8, §0.10.11, S1.1; seguridad ALTO + MEDIO): en Windows
   `NoDefaultCurrentDirectoryInExePath=1` antes de `shutil.which` (un `ffmpeg.exe` plantado en la
   carpeta de crudo se ejecutaba); la ruta final debe ser absoluta; en Windows solo `.exe`/`.com`, con
   `.bat`/`.cmd` rechazados tanto desde `which` como desde `KCUT_FFMPEG`/`KCUT_FFPROBE` (`cmd.exe`
   re-parsea: `x&whoami` se ejecutó). Fallo → `MissingDependency` (7). Tests: criterio S1.1-10.
4. **Log de hijos** (§0.8, §0.10.12, §0.11, S1.1; verificador ALTO): stderr de cada hijo a su propio
   temporal, agregado al log al terminar bajo un lock por ruta de log; la cola de un error sale solo
   de ese hijo; `popen` devuelve `ChildProcess`. Test: criterio S1.1-11.
5. **Timeout duro** (S1.1 `proc.run` y `ChildProcess.wait`): `kill()` + `communicate(timeout=grace_s)`;
   si sigue trabado, se cierran los pipes y `ToolError`. Test con un nieto que retiene el pipe
   (skip si no se puede reproducir): criterio S1.1-12.
6. **S1.2 agregados**: (a) `cli.py — MODIFICAR`: traceback de `InternalError` al log del proyecto, o a
   stderr solo con `-v` si no hay proyecto; (b) `commands/doctor.py — MODIFICAR`: dentro de un
   proyecto usa `transcribe.model` (S1.1 queda con `medium` fijo). Criterios S1.2-12 y S1.2-13.
7. **Privacidad de metadatos** (§0.8, S1.1 `scrub_media_metadata`, S1.2 `ff/args.py` y `probe.py`):
   `-loglevel error` en todo comando sobre medios del usuario, `-map_metadata -1` en los
   intermedios, limpieza de errores/`--json`/log, y el JSON crudo de ffprobe nunca sale. Tests:
   criterios S1.1-13 y S1.2-14 (archivo sintético con ubicación y modelo).
8. **Chromium endurecido** (S1.6 `gfx/capture.py`, y el check `chromium` de doctor usa las mismas
   opciones): `chromium_sandbox=True` y `page.route` que aborta todo lo que no sea `file://` o
   `data:`. Si el sandbox no funciona en Windows → BLOQUEADO, no se quita en silencio. Criterio S1.6-9.
9. **Dependencias** (§0.1, §0.12, S1.1): pisos `Pillow>=10.3` y `playwright>=1.55.1` (CVE conocidos
   debajo); nuevo `requirements.lock` commiteado con la clausura de runtime fijada desde el venv de
   referencia; instalación con `-c requirements.lock` (sale el argumento `"playwright==1.63.0"`
   aparte; el lock lo fija); la pista de instalación de Chromium del doctor sale de la versión
   instalada, sin una segunda versión escrita a mano en `checks.py`. Criterios S1.1-1 (cambiado),
   S1.1-15, S1.1-16 y S1.1-17.
10. **Hueco de test** (S1.1): el caso "modelo válido pero no bajado" se prueba reemplazando
    `download_model` para que lance, no con un nombre de modelo inválido. Criterio S1.1-14.
11. **Pendiente para el `sdd-archiver`** (fuera del alcance del implementador; el README no se toca
    en los slices): documentar que el usuario corre `kcut ...` (entry point) o
    `python -I -X utf8 -m kcut`, nunca `python -m kcut` a secas desde una carpeta de crudo: el cwd
    entra a `sys.path` y un `cv2.py` plantado ahí se importaría.

### 001.2 — 16/10/2026 — ronda 3 de S1.1 (aprobado por Yedin)

S1.1 suma los criterios 18–23. El resto del spec no cambia.

1. **Piso de Pillow** (§0.12, S1.1 `requirements.lock` y su test): `Pillow>=10.3` → `Pillow>=12.3`.
   OSV consultado en vivo el 16/10/2026: Pillow 10.3.0–12.2.0 tiene entre 26 y 38 avisos, entre ellos
   lectura/escritura fuera de límites (HIGH) en `paste`/`crop` e inyección de comandos en
   `WindowsViewer`; 12.3.0 tiene 0. Si el `.venv` de referencia tiene un Pillow menor, se actualiza
   y se regenera el lock. El piso `playwright>=1.55.1` se mantiene, pero **no** está respaldado por
   un aviso de OSV: no hace daño. Criterio S1.1-22.
2. **`args[0]` absoluto** (§0.8, S1.1 `proc.run`/`popen`): si no es ruta absoluta → `ValueError`
   "usa tool_path" antes de lanzar nada. Criterio S1.1-18.
3. **Salida de `ChildProcess`** (§0.8, S1.1): salir del `with` sin excepción con el hijo vivo ya no lo
   mata en silencio: espera `grace_s`; si no terminó, `kill()` + `ToolError`. La salida por
   excepción sigue igual (kill + wait). `popen` recibe `grace_s`. Los tests `test_child_exit_*`
   reemplazan el que fijaba el kill silencioso. Criterio S1.1-19.
4. **`tool_path` resuelve antes de revisar el sufijo** (§0.8, S1.1): el `.exe`/`.com` se exige sobre
   la ruta resuelta, así un symlink `x.exe` → `.cmd` se rechaza. Criterio S1.1-20.
5. **Pista de Chromium con comillas** (S1.1 `checks.py`): `"<sys.executable>" -m playwright install chromium`,
   porque la ruta trae espacios. Criterio S1.1-21.
6. **Tamaño de los tests** (§0.2): `tests/unit/test_doctor_checks.py` pasó de 300 líneas; se parte
   (p. ej. `TestDoctorCommand` → `tests/unit/test_doctor_command.py`) sin romper los node ids de los
   criterios 14 y 15. Criterio S1.1-23.

### 001.3 — 16/10/2026 — deuda pagada (aprobado por Yedin: arreglar deuda de inmediato)

Refinamientos del contrato de S1.1 (deudas 6, 8, 9, 11, 12 y 13 de `PROGRESO.md`). La deuda 15
(README: cómo correr `kcut`, pendiente del punto 11 de 001.1) también se pagó; no cambia el
contrato. El resto del spec no cambia.

1. **`_validate` rechaza `.bat`/`.cmd`** (§0.8, S1.1 `proc.run`/`popen`; deuda 6): en Windows, un
   `args[0]` absoluto cuyo nombre termina en `.bat` o `.cmd` (sin importar mayúsculas, y quitando
   antes los puntos y espacios finales, que Windows ignora: `x.bat ` también pasaba por `cmd.exe`)
   → `ValueError` antes de lanzar nada. Test: `tests/unit/test_proc.py::test_rejects_bat_and_cmd_on_windows`.
2. **stderr por trozos con cola acotada** (§0.8, §0.11; deuda 8): `_finalize` ya no lee el stderr
   entero a memoria. El log recibe el stderr completo, por trozos de 1 MB, limpiado línea por línea
   (las líneas no se parten antes de limpiar, así un bloque `Metadata:` no se pierde entre trozos);
   una sola línea de más de 1 MB conserva su primer MB y la marca `[... X MB omitidos]`. En memoria
   (cola de error y `capture_stderr`) quedan solo los últimos 8 MB, empezando en una línea entera y
   precedidos de la línea `[... X MB omitidos]` cuando se cortó; las líneas con sangría justo
   después del corte también se van (podrían ser de un bloque `Metadata:` cuyo encabezado quedó
   fuera, y el filtro no las reconocería). La lógica vive en
   `src/kcut/childlog.py` (nuevo: partido de `proc.py` por la regla de 300 líneas). Tests:
   `tests/integration/test_proc_stderr_cap.py`.
3. **Reglas de `scrub_media_metadata`** (§0.8; deuda 9): (a) claves sensibles por palabra completa
   y solo en claves cortas (hasta 3 palabras antes de `:`), así "Unable to make progress: ..." y
   "Could not determine model: ..." se conservan; (b) también se limpian las líneas
   `TAG:<clave>=<valor>` y los pares JSON `"<clave>": "<valor>"`; (c) ISO 6709 también en las formas
   compactas DM/DMS que terminan en `/` (`+181030-0695555/`, `+1810.5-06955.9/`) y con altitud final.
   Una sola lista de claves para todos los formatos: palabras `location`, `iso6709`, `make`, `model`,
   `creation_time`, `serial`, `artist`, `comment`, `title`, `description`, `encoded_by`, `copyright`;
   prefijos `com.apple.` y `gps`. `scrub.MetadataScrubber` es el mismo filtro con estado entre
   trozos. Tests: `tests/unit/test_scrub.py`.
4. **Tests con el intérprete base** (§0.2; deuda 11): los tests que lanzan hijos con `sleep` largo
   usan `sys._base_executable`, no el `python.exe` del venv (en Windows es un lanzador cuyo hijo
   sobrevive al `kill()`); el nieto del test de timeout se mata por su PID registrado con
   `taskkill /T`. Test: `tests/integration/test_proc_timeout.py::test_killing_the_child_leaves_no_sleeping_interpreter`.
5. **Pistas del doctor derivadas** (S1.1 `checks.py`; deuda 12): la pista de `fonts` toma el piso de
   Pillow de los metadatos instalados de kcut (salen de `pyproject.toml`; hoy `Pillow >= 12.3`);
   `checks.py` no escribe ninguna versión de Pillow a mano. Test:
   `tests/unit/test_doctor_checks.py::test_fonts_hint_derived`.
6. **Capturas reales de ffmpeg n7.1** (S1.1 tests; deuda 13): `tests/data/ffmpeg-n7.1-filters.txt`
   y `tests/data/ffmpeg-n7.1-encoders.txt` son la salida entera y sin tocar de
   `-hide_banner -filters` y `-hide_banner -encoders` del ffmpeg n7.1 de
   `@remotion/compositor-win32-x64-msvc` 4.0.503; los tests comparan conjuntos exactos (42 filtros,
   19 encoders). El docstring ya no dice que las líneas de n7.0.1 son textuales (sus descripciones
   están reescritas). Se mantiene la cobertura de 8.1.1 y 7.0.1.

### 001.4 — 16/10/2026 — ronda 2 de S1.2 (hallazgos de revisión; regla de Yedin: arreglar de inmediato)

Revisión de S1.2: el verificador encontró 1 CRÍTICO y seguridad 1 ALTO. Regla de Yedin del 16/10/2026:
todo hallazgo se anota y se arregla de inmediato. S1.2 suma los criterios 15–28 (el 8 se endurece) y
S1.5 los criterios 14–15. No hay entrada 001.3 en esta rama: la agrega otra rama.

1. **CRÍTICO — `kcut new` no sobrescribe** (S1.2 `commands/new.py`): `edit/estrategia.md`,
   `edit/versiones.md` y `recursos/recursos.json` se crean solo si faltan; `created` lista solo lo
   creado; primero se validan todas las carpetas y `kcut.toml` se escribe al final (sin proyectos a
   medias). Criterio S1.2-15.
2. **ALTO — confianza en la caché** (§0.3, §0.9, S1.2 `inventory.py`, `workfiles.py`, `project.py`):
   (a) `_clip` valida id/clase, slug, `file` bajo `crudo/`, `work.proxy` y `work.wav16` bajo su
   carpeta, con `re.fullmatch`; un inventario inválido se trata como ausente con aviso;
   (b) `_assert_in_cache` al inicio de toda escritura/movida/borrado (`_build`, `adopt` origen y
   destino, `discard`); (c) un wav16 viejo solo se reusa si resuelve bajo `.kcut/wav16/`;
   (d) `open_project` rechaza `.kcut` o carpetas del layout que resuelvan fuera de la raíz;
   (e) kcut nunca escribe, mueve ni borra bajo `crudo/`. Criterio S1.2-16 (regresión con caché envenenada).
3. **Inyección en el gate** (S1.2 config y `new`; S1.5 `edl/gate.py`): `project.name` y `--name`
   rechazan las categorías Unicode `Cc`, `Cf`, `Zl`, `Zp`; el lector del front-matter separa solo por
   `"\n"`, aplica `re.fullmatch` por línea y un `aprobado` repetido es error (cierra en falso).
   Criterios S1.2-17 y S1.5-14.
4. **Traceback de `InternalError`** (S1.2 `cli.py`): se agrega al mismo log de la corrida que usan
   los hijos, nunca trunca; el mensaje corto pasa por `scrub_media_metadata`. Criterio S1.2-18.
5. **Etiquetas de color SDR** (deuda 16, confirmada por el verificador; S1.2 `ff/color.py`, S1.5
   `render/encoder.py`): `setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv`
   al final de `video_chain` y del encoder final; `CHAIN_VERSION` → `"tm2"` y sube la versión de
   parámetros del proxy para invalidar la caché. Criterios S1.2-8 (ahora exige las 4 etiquetas en
   los 3 proxies), S1.2-19 y S1.5-15.
6. **Ids nunca se reusan** (S1.2 `classify.assign_ids`, inventario con `id_high`): match por
   (`qhash`, `file`) y luego por `qhash` (con prefijo coincidente); los nuevos reciben máx + 1.
   Criterio S1.2-20.
7. **wav16 fallido tras un ffprobe bueno** (S1.2 `run.py`): el clip conserva su clase, proxy y
   `frames`; aviso `wav16_failed`, no `probe_failed`. Criterio S1.2-21.
8. **Score de sync normalizado por el solape** (S1.2 `sync.py`): se divide por el solape en el lag
   del pico, no por `min(len)`; se ignoran lags con solape < `min(10 s, 0.5 × el más corto)`;
   `min_score`/`min_ratio` iguales. Criterio S1.2-22.
9. **Límites de recursos** (S1.2 config `[ingest]`, `workfiles.py`, `run.py`): pico del wav16 por
   bloques; `warn_duration_h = 3` y `max_duration_h = 12` (avisos `long_duration` y `too_long`);
   `timeout_s = 10 × duración + 60` por trabajo de ffmpeg. Criterio S1.2-23.
10. **BAJOs** (S1.2): regex de config con `re.fullmatch`; `os.walk` poda junctions/symlinks con
    aviso y deduplica por ruta relativa; el nombre por defecto de `kcut new` se recorta a 80;
    `proxy_size` con tamaño 0 marca `probe_failed` y sigue; `read_json` convierte `ValueError` y
    `RecursionError` en `ProjectError` y la caché corrupta se reconstruye. Criterios S1.2-24 a S1.2-27.
11. **Árbol** (§0.2): se agregan `ingest/inventory_model.py`, `ingest/sync_stage.py`,
    `doctor/result.py`, `doctor/chain_checks.py` (partidos por la regla de 300 líneas); `fnum` vive
    en `ff/args.py`. Criterio S1.2-28.

### 001.5 — 16/10/2026 — piso de solape de la sincronía (aprobado por Yedin)

- S1.2 `sync.py`: el piso de solape pasa de `min(10 s, 0.5 × el más corto)` a `min(10 s, 0.75 × el más corto)`. Con 0.5, un pico secundario en un solape chico se inflaba al normalizar por el solape (cámara B sintética: ratio 1.39 < `min_ratio` 1.5, rechazada, contradiciendo S1.2-7). Con 0.75: ratio 1.77, aceptada con offset 1200 ms. En clips largos (≥ 13.4 s el más corto) el piso sigue siendo 10 s, así que el caso de 75 s de solape (S1.2-22) no cambia. Lo reportó el implementador como BLOQUEADO; Yedin eligió la opción A.

### 001.6 — 16/10/2026 — ronda 3 de S1.2 (aprobado por Yedin)

Revisión de S1.2, ronda 2: el verificador encontró 1 ALTO y varios MEDIO; seguridad aprobó con 1
MEDIO y algunos BAJO. Incluye decisiones de Yedin del 16/10/2026. S1.2 suma los criterios 29–39,
S1.3 el 10 y S1.5 el 16.

1. **ALTO — sync con refinado débil** (S1.2 `sync.py`, config `[sync] min_refine_corr`, default 0.1,
   rango 0–1; decisión del dueño): si la correlación de `refine_offset` queda bajo el umbral, el par
   se rechaza con `sync_weak_refine`. Se mantiene el piso de solape de 0.75. Calibración: offsets
   equivocados en clips cortos 0.012–0.019, correcto 0.99, piloto real 0.489. Criterio S1.2-29.
2. **`sources` en el EDL** (S1.5, decisión del dueño): mapa `id → {qhash}` con todo `src` usado;
   `edl check`, `render` y `build` salen con 1 (E04 con el id) si el `qhash` no coincide o el clip
   falta. Criterio S1.5-16.
3. **MEDIO — enlaces internos** (S1.2 `paths.Layout.all_paths`, `project.check_layout_inside`,
   `workfiles._assert_in_cache`): toda ruta del layout que sea symlink o junction se rechaza, además
   de exigir que resuelva dentro de la raíz; `_assert_in_cache` exige que la caché sea de verdad
   `<raíz>/.kcut` y que el destino no esté bajo `crudo/`. Criterio S1.2-30.
4. **MEDIO — log** (§0.11, `cli._run_log`, `proc.append_log`): creación exclusiva con nombre único
   (incluye el pid: `<comando>-<YYYYmmdd-HHMMSS>-<pid>.log`); antes de cada append, archivo regular
   con `st_nlink == 1` dentro de la caché real, si no solo stderr. Criterio S1.2-31.
5. **MEDIO — `OSError` al hashear** (S1.2 `ingest/scan.py`): ese archivo queda `probe_failed` sin id
   y el ingest sigue. Criterio S1.2-32.
6. **BAJOs** (S1.2): `_copy` no hace nada si origen y destino son el mismo archivo; `-t` en wav16 y
   proxy y recálculo de `long_duration`/`too_long` con el largo real del wav16 (se borra si queda
   `too_long`); `kcut new` llama `check_layout_inside`, poda junctions y su aviso no cuenta los
   archivos del layout; `ID_HIGH_MAX = 999_998` con `ProjectError` en el tope; `anoisesrc` del
   fixture con `seed=42`; mensaje claro cuando hay una carpeta donde va un archivo.
   Criterios S1.2-33 a S1.2-38.
7. **Árbol** (§0.2): `config/names.py`, `config/fields.py`, `ingest/scan.py`, `ingest/examine.py`,
   `ingest/inventory_check.py`, `ingest/inventory_json.py`, `tests/fixtures/links.py`. Criterio S1.2-39.
8. **Higiene ante inyección de prompt** (S1.3 `config/load.py — MODIFICAR`): `glossary.terms`,
   `transcribe.fillers` y `transcribe.prompt_extra` rechazan `Cc`/`Cf`/`Zl`/`Zp` como `project.name`.
   Criterio S1.3-10.
9. **Lección pagada** (para `PROGRESO.md`, la anota el `sdd-archiver`): en Windows, dentro de un venv,
   `sys.executable` es un lanzador que arranca al intérprete base como otro proceso; `kill()` mata al
   lanzador y el intérprete real sigue vivo (y retiene pipes). Todo `proc.run([sys.executable, ...])`
   futuro en kcut, o en sus tests, que dependa de matar al hijo debe usar el intérprete base
   (`sys._base_executable`), sabiendo que ese no ve los paquetes del venv.

### 001.7 — 17/10/2026 — cierre de S1.2: deuda de la ronda 3 (aprobado por Yedin)

S1.2 quedó APROBADO por verificador y seguridad en la ronda 3 (0 CRÍTICO, 0 ALTO). Lo que dejaron
(1 MEDIO, 6 BAJO y dos notas) se paga de una por la regla del dueño. S1.2 suma los criterios 40–54
y S1.3 el 11. Se implementa **después** de mergear la rama de deuda de S1.1 (001.3), que también
toca `proc.py`.

1. **MEDIO — sync ambiguo en clips cortos** (S1.2 `ingest/sync.py`; decisión del dueño 17/10/2026).
   Caso: audio casi periódico, clip corto y desfase grande; el lag verdadero cae bajo el piso de
   solape de 0.75 y el refinado correlaciona fuerte en el lag equivocado (tonos del fixture, 12 s,
   +4 s → aceptado con −2800; +6 s → −800 con `refine_corr` 0.85).
   - Cuándo aplica: solo si el piso efectivo de `coarse_offset` es el de la fracción
     (`MIN_OVERLAP_FRACTION * min(len)` < el de `_MIN_OVERLAP_S`), es decir con el clip más corto
     por debajo de ~13.4 s. Con clips más largos no se calcula nada extra.
   - Qué hace: calcula también el mejor lag con piso 0.5 (misma normalización por solape, misma
     envolvente). Si `|lag_0.5 − lag_0.75| > 2000 ms`, el par se rechaza: va a `sync.rejected` con
     `reason: "ambiguous"`, los dos lags en ms, y aviso `sync_ambiguous` con
     "sincronía ambigua: clip corto con dos desfases posibles (<a> s y <b> s); revísalo a mano".
   - El umbral de 2 s y el piso 0.5 son constantes con nombre en `sync.py` (no van a `kcut.toml`).
   - Si con esto la cámara B sintética (criterio 7) o cualquier caso del criterio 29 **con la
     config por defecto** deja de dar lo que da hoy, el implementador **para y devuelve BLOQUEADO**
     con las mediciones.
   - Resuelto tras el BLOQUEADO del 17/10 (coordinador): orden fijo score → ratio → refinado →
     `weak_refine` → ambigüedad. Las variantes `lenient` (`min_refine_corr = 0`) de
     `tests/unit/test_sync.py::test_weak_refine_rejects_a_12s_pair_shifted_5s` y
     `tests/integration/test_ingest_edge.py::TestWeakRefine::test_the_threshold_can_be_lowered_in_the_config`
     demuestran que sin la regla del refinado se acepta un desfase equivocado; el chequeo nuevo
     también lo atrapa (es una segunda red, lo esperado). Esas dos variantes desactivan además el
     chequeo de ambigüedad con `monkeypatch` sobre su constante, y sus asserts no cambian.
   - Forma del dato: `SyncRejected` gana `lag_a_ms` (lag con piso 0.75) y `lag_b_ms` (lag con piso
     0.5), opcionales (`null` si no aplica), en el modelo, en `inventory.json` y en el cargador
     (validados como enteros). `reason` sigue el estilo actual: texto que empieza con
     `sync_ambiguous` (igual que `sync_weak_refine`). El aviso por clip lleva `sync_ambiguous`
     **y** `sync_rejected`, como hoy `sync_weak_refine`. El mensaje "sincronía ambigua: … (<a> s y
     <b> s); revísalo a mano" sale en la línea `AVISO` humana y como `message_es` en `--json`.
   - Criterio S1.2-40.
2. **BAJO — `kcut new` anidado** (S1.2 `commands/new.py`): antes de crear nada, si un ancestro del
   destino tiene `kcut.toml` y el destino cae dentro de una carpeta de ese `Layout`
   (`paths.Layout`), → `ProjectError` (exit 3): "no creo un proyecto dentro de <carpeta>/ de otro
   proyecto (<ruta del padre>)". Fuera de las carpetas del layout se sigue permitiendo. Criterio
   S1.2-41.
3. **BAJO — `run_ingest` con `log=None`** (S1.2 `ingest/run.py:49`): si la CLI pasó `None`
   ("esta corrida no deja log"), `run_ingest` no calcula otro nombre ni escribe log; todo va a
   stderr. Criterio S1.2-42.
4. **BAJO — logs vacíos** (§0.11, `cli._run_log`): la creación exclusiva al arrancar se mantiene
   (reserva el nombre). Al terminar la corrida, pase lo que pase, si el log que **esta** corrida creó
   sigue en 0 bytes, se borra solo si es el mismo archivo (mismo `st_dev` y `st_ino` que al crearlo,
   tomados con `os.fstat` sobre el handle de creación), regular y con `st_nlink == 1`. Si algo de
   eso no se cumple, no se toca. Tres tests de 001.6 afirmaban que el log vacío queda después de
   `cli.main` (`test_log_safety.py::TestCreation::test_the_name_carries_the_pid_and_the_log_exists_empty`,
   `test_cli_internal_error.py::TestInsideAProject::test_other_errors_leave_no_traceback_in_the_log`,
   `test_cli_internal_error.py::TestSameLog::test_one_log_path_is_chosen_per_invocation`): sus
   asserts de "existe, vacío, `st_nlink == 1`" pasan al interior del `run` falso (donde el log
   existe) y después de `main` afirman que ya no está. Criterio S1.2-43.
5. **BAJO — `append_log` con `OSError` y hijo huérfano** (§0.11, `logfile.py`, `proc.py`
   `ChildProcess.__init__`, `project.check_layout_inside`; hallazgo de seguridad). Desde el merge de
   001.3 toda escritura al log pasa por el context manager `logfile.log_writer(log)` (mismo lock por
   ruta, `unsafe_reason`, `fstat` regular con `st_nlink == 1`, si no `_to_stderr`):
   - `log_writer` captura `OSError` de `mkdir`/`os.open`/`fstat` y cae a `_to_stderr` con el texto
     del error como motivo. Un `OSError` en un `write` a mitad del bloque tampoco sale: el handle que
     entrega `log_writer` va envuelto de modo que, desde ese `write`, el resto del texto va a stderr
     con un aviso único. Ni `append_log` ni `log_writer` lanzan nunca `OSError`. Si stderr también
     falla (cerrado o `None`), el texto se descarta en silencio: el log nunca tumba un comando.
   - `ChildProcess.__init__` escribe la cabecera `$ ...` **antes** del `Popen`. Si algo lanza entre
     el `Popen` y el final de `__init__`, hace `kill()` + `wait()` del hijo antes de propagar.
   - `check_layout_inside`: toda carpeta del layout que exista tiene que ser carpeta (`is_dir()`
     sobre una ruta que ya se comprobó que no es enlace); si es un archivo → `ProjectError` (exit 3):
     "hay un archivo donde kcut espera una carpeta: <ruta relativa>".
   - Criterios S1.2-44 y S1.2-45.
6. **BAJO — avisos de sync desde el motivo** (S1.2, nota del verificador): el aviso por clip se
   deriva del motivo de rechazo guardado (`score`, `ratio`, `weak_refine`, `ambiguous`), no de si
   `refine_corr` es `None`. Una función pura mapea el `reason` guardado a su motivo por el prefijo o
   texto que ya escribe hoy cada rechazo (los textos actuales no cambian). Criterio S1.2-46.
7. **BAJO — árbol** (§0.2): `src/kcut/logfile.py`, `src/kcut/childlog.py` (este último de 001.3) y `src/kcut/ingest/sync_reasons.py` (nuevo en 001.7). Ya aplicado en este parche.
8. **BAJO — no se cambia: archivo que no se pudo hashear recibe id nuevo después** (`scan.py:68-72`).
   El verificador sugirió conservar la entrada previa del mismo `file`. **Se rechaza**: esa entrada
   llevaría un `qhash` viejo; si el archivo cambió mientras estaba bloqueado, el EDL y el inventario
   coincidirían en el `qhash` viejo, E04 no saltaría y `render` cortaría el video equivocado. Un id
   nuevo con E04 ruidoso es el fallo seguro.
9. **Suite rápida** (deuda de PROGRESO; `pyproject.toml` y tests): el marcador `slow` pasa a
   "tarda mas de 2 s". Todo test que en `pytest -q --durations=0` de la suite completa tarde más
   de 2 s lleva `@pytest.mark.slow` (por función o por módulo con `pytestmark`). Suite rápida:
   `pytest -m "not slow"`; suite completa: `pytest`, como hoy. No se borra ni se salta ningún test.
   Criterio S1.2-47.
10. **Nota de seguridad para S1.3+**: tras el recheck de largo real, el inventario sigue guardando
    el `duration_ms`/`frames` declarado; solo los avisos usan el largo real. Todo slice que use el
    largo de un clip para un tope, un bucle o una ventana lo saca del wav16. Criterio S1.3-11.
11. **MEDIO — lags sin rango en un inventario hostil** (revisión de seguridad de 001.7;
    `ingest/inventory.py` carga de `SyncRejected`, `ingest/sync_reasons.py`): `lag_a_ms` y
    `lag_b_ms` se validan con rango `-43_200_000 … 43_200_000` (12 h) como los demás enteros de
    tiempo; fuera de rango → `inventory_invalid` (el inventario se reconstruye, como cualquier
    otro campo inválido). `ambiguity_message` formatea los segundos sin división de enteros
    grandes que pueda lanzar. Criterio S1.2-48.
12. **MEDIO — texto crudo del inventario en la consola** (`commands/ingest.py` `_rejection_text` y
    la línea de `method`; `ingest/inventory.py`): la línea `AVISO` humana nunca imprime `reason` ni
    `method` tal como vienen del `inventory.json`. El texto sale de una tabla fija según
    `rejection_motive(reason)` (y "sin sincronía" si es `None`); `method` solo se imprime si es uno
    de los valores que kcut escribe, si no se omite. Además la carga de `reason` y `method` exige
    `max_len = 300` y rechaza `Cc`/`Cf`/`Zl`/`Zp` como `project.name` → `inventory_invalid`. En
    `--json` no cambia nada (ya sale escapado). Criterio S1.2-49.
13. **BAJO — surrogate suelto en el log** (`logfile.py` `_FdSink.write` y el fallback a stderr):
    `encode("utf-8", errors="replace")`; un argumento o texto con un surrogate suelto (`\ud800`)
    nunca lanza `UnicodeEncodeError` (completa la promesa del punto 5). Criterio S1.2-50.
14. **BAJO — nombre con surrogate suelto en `crudo/`** (`ingest/scan.py` y `jsonio.py`, deuda vista
    por seguridad): un archivo cuyo nombre no se puede codificar en UTF-8 no entra al inventario: va
    a la lista de avisos como `probe_failed` sin id, con "el nombre de este archivo tiene
    caracteres inválidos; renómbralo" (el `file` del aviso se escribe con `errors="replace"`), y el
    ingest sigue. `save_inventory` nunca lanza `UnicodeEncodeError`. Criterio S1.2-51.
15. **MEDIO — reuso de un sync medido con el algoritmo viejo** (revisión del verificador;
    `ingest/sync.py`, `ingest/sync_stage.py` `_reusable`, modelo/JSON/cargador del inventario).
    Constante `SYNC_VERSION = 2` en `sync.py` (001.7 es la versión 2; todo lo anterior cuenta como
    1). Cada miembro, aceptado o rechazado, guarda `sync_version`. `_reusable` solo reusa un
    miembro si su `sync_version` es la actual **y** coincide el `qhash`; si falta o es otra, se
    vuelve a medir como con `--resync` para ese par. Regla para adelante: todo cambio que pueda
    cambiar el resultado del sync sube `SYNC_VERSION`. El cargador valida `sync_version` como
    entero `1 … 1000`; un inventario sin el campo es válido y vale como versión 1. Criterio S1.2-52.
16. **MEDIO — test debilitado por el punto 4** (`tests/unit/test_cli_internal_error.py`):
    `TestInsideAProject::test_other_errors_leave_no_traceback_in_the_log` usa un `run` falso que
    afirma `args.log is not None and args.log.is_file()` antes de lanzar, así recupera el "existe"
    que tenía el `== [""]` original. El archivo sigue en ≤ 300 líneas. Criterio S1.2-53.
17. **BAJO — "Detalle técnico en <log>" cuando el traceback cayó a stderr** (`cli.py` manejo de
    `InternalError`, `logfile.py`): `append_log` devuelve `bool` (`True` si el texto quedó en el
    log, `False` si cayó a stderr o se descartó). `cli` agrega la frase "Detalle técnico en <log>"
    solo con `True`; se borra el `except OSError` que quedó muerto. Criterio S1.2-54.

### 001.8 — 17/10/2026 — higiene de la consola (revisión de seguridad de 001.7; regla de Yedin: arreglar de inmediato)

Segunda pasada de seguridad sobre 001.7: APROBADO (0 CRÍTICO, 0 ALTO), con 1 MEDIO anterior a 001.7
y 3 BAJO. S1.2 suma los criterios 55–58.

1. **MEDIO — texto no confiable crudo en la consola** (`console.py` y `cli.py`). Los mensajes del
   cargador interpolan claves e ids del `inventory.json` (`clips[<id>]`, `<ruta>.<clave>`,
   `id_high.<prefijo>`), y las líneas `[OK]`/`AVISO` llevan nombres de archivo de `crudo/`; todo eso
   llegaba sin limpiar a la terminal (secuencias de escape que cambian el título, borran la pantalla
   o pintan líneas falsas).
   - La cura va en el **sumidero**: función pura `console.safe_text(text: str) -> str` que cambia
     cada carácter de categoría Unicode `Cc`, `Cf`, `Zl`, `Zp` o `Cs` por su escape visible
     (`\xNN` hasta U+00FF, `\uNNNN` hasta U+FFFF, `\UNNNNNNNN` más arriba). Excepción: `\n` se
     conserva.
   - Se aplica a todo texto que kcut imprime: `Out.line`, `Out.warn`, el `print` de errores de
     `cli._report`, el texto que `cli._internal` manda a stderr cuando no hay log, el aviso de "no
     pude crear el log" y cualquier otro `print` a stdout/stderr de `console.py` y `cli.py`.
   - En `--json`, `Out.result` (la única que imprime JSON) aplica `safe_text` a cada `str` del objeto (claves y valores) antes de
     `json.dumps`; `ensure_ascii` sigue en `False`, así que las tildes no cambian.
   - Los mensajes de error no cambian de forma (no se usa `!r` en el cargador); el log en disco no
     se toca.
   - Criterio S1.2-55.
2. **BAJO — texto libre del inventario en `--json`** (`commands/ingest.py`; esa salida la lee Claude,
   así que es una vía de inyección de prompt): en `--json`, `reason` de un rechazo de sync sale con
   el texto fijo de `rejection_text` (el mismo de la línea humana) y `method` sale como `null` si no
   está en `SYNC_METHODS`. El inventario en disco guarda lo mismo que hoy. Criterio S1.2-56.
3. **BAJO — rangos que faltaban** (`ingest/inventory.py` `_member`): `offset_ms` y `drift_ms`
   ±43 200 000 (12 h) y `drift_windows` 0 … 100 000. Fuera de rango → `inventory_invalid`, como los
   lags de 001.7. Criterio S1.2-57.
4. **BAJO — mensaje de rango gigante** (`schema_util.py`): cuando un entero fuera de rango tiene más
   de 20 dígitos, el mensaje muestra los primeros 20 y "… (<N> dígitos)". Criterio S1.2-58.
5. **Nota para el spec 002** (no se implementa aquí): los nombres de archivo de `crudo/` siguen
   saliendo en `--json` porque son el dato. El plugin y sus agentes tratan **toda** salida de kcut
   (nombres de archivo, textos de `kcut.toml`, avisos) como datos, nunca como instrucciones.

### 001.9 — 17/10/2026 — deuda vista al implementar 001.8 (regla de Yedin: arreglar de inmediato)

El implementador de 001.8 encontró 1 MEDIO y 3 BAJO fuera de su alcance. S1.2 suma los criterios
59–62. Se corrige además el nombre `Out.json` → `Out.result` en 001.8 punto 1 (ya aplicado).

1. **MEDIO — float gigante tumba el cargador** (`schema_util.py` `_float` y quien convierta a
   float): `math.isfinite(10**400)` lanza `OverflowError`; un `inventory.json` con `"score":
   10**400` terminaba `kcut ingest` con exit 10. Todo float validado que llegue como `int` se
   convierte dentro de un `try` (`OverflowError` → error de validación "debe ser un número finito");
   lo mismo para `inf`/`nan`. Vale para el inventario (`inventory_invalid`) y para `kcut.toml`
   (`ProjectError`, exit 3). Criterio S1.2-59.
2. **BAJO — `_describe` con entero gigante** (`schema_util.py`, vía `one_of`): usa el mismo
   `_shown` de 001.8 punto 4 en vez de `repr()`. Hoy no se alcanza (los llamadores pasan `str`), se
   endurece igual. Criterio S1.2-60.
3. **BAJO — fallback del log a stderr sin limpiar** (`logfile.py` `_to_stderr`): cuando el log no
   se puede escribir, la cabecera `$ <args>` (con nombres de archivo) y el stderr de los hijos van a
   stderr; pasan por `safe_text` (con `\n` conservado), igual que el resto de la consola (001.8
   punto 1). Si importar `console` desde `logfile` crea un ciclo, `safe_text` se mueve a
   `src/kcut/textsafe.py` y `console` lo re-exporta (se agrega al árbol §0.2). Criterio S1.2-61.
4. **BAJO — tope de tiempo inconsistente** (`timebase.py`, `ingest/inventory.py`,
   `ingest/sync_reasons.py`): 001.7 punto 11 y 001.8 punto 3 pusieron ±12 h, pero
   `ingest.max_duration_h` admite hasta 48 h: un par válido con más de 12 h de desfase se volvería a
   medir en cada ingest. Constante única `MAX_TIME_MS = 48 * 3_600_000` en `timebase.py`; es el tope
   de `lag_a_ms`, `lag_b_ms`, `offset_ms` y `drift_ms` (reemplaza `MAX_LAG_MS` y los ±43 200 000), y
   el cargador de `kcut.toml` usa el mismo 48 como máximo de `max_duration_h`. Los tests de borde de
   las filas 48 y 57 cambian su borde a ±172 800 000 (el contrato cambió; sus asserts no se
   aflojan). Criterio S1.2-62.

### 001.10 — 17/10/2026 — paso 0 de S1.3: notas de seguridad fuera del diff de 001.8/001.9

La revisión de seguridad de 001.8 + 001.9 dio APROBADO con 0 hallazgos en el diff. Dejó notas sobre
código anterior. Por la regla de Yedin se arreglan ya, como **paso 0 de S1.3** (antes de
`transcribe`/`pack`, en el mismo slice y con los mismos revisores). S1.3 suma los criterios 12–15.

1. **MEDIO — prosa del atacante en el aviso `inventory_invalid`** (`ingest/run.py` `_previous`,
   `commands/ingest.py`): el mensaje del cargador (claves, ids y `!r` de valores del
   `inventory.json`, sin tope) salía entero en `--json` (`warnings[].detail` y `message_es`), que lee
   Claude: vía de inyección de prompt. Tanto en `--json` como en la línea humana, el aviso dice solo
   "se ignora el inventario anterior: no pasó la validación" más la ruta del campo que falló
   (`clips[3].slug`, sin el valor) recortada a 120 caracteres; el mensaje completo va solo al log.
   El `error.message` de un `kcut.toml` inválido no cambia (el archivo es del usuario; 001.8 punto 5).
   Criterio S1.3-12.
2. **BAJO — `sync.manual` sin rango** (`config/load.py`): cada `sync.manual.<id>` se valida con
   ±`MAX_TIME_MS`; si no, `ProjectError` que nombra la clave. Así kcut no escribe un offset que luego
   su propio cargador rechaza. Criterio S1.3-13.
3. **BAJO — entero gigante en `kcut.toml`** (`config/load.py` `parse_config`): se captura
   `ValueError` (cubre `tomllib.TOMLDecodeError`, que es subclase, y el "Exceeds the limit (4300
   digits)") → `ProjectError` (exit 3). Criterio S1.3-14.
4. **BAJO — selectores de variación y uso privado** (`console.py` `safe_text`): además de
   Cc/Cf/Zl/Zp/Cs, se escapan U+FE00–U+FE0F, U+E0100–U+E01EF y la categoría `Co`. Sirven para
   esconder texto a quien revisa lo que lee Claude. Criterio S1.3-15.
5. **Nota, sin código**: `_clean` de `Out.result` funde dos claves que solo difieren en lo escapado.
   Hoy ninguna clave de la salida JSON viene del proyecto; todo slice que saque claves de datos del
   usuario o del inventario lo revisa.

### 001.11 — 17/10/2026 — ajustes de S1.3 tras la implementación (coordinador)

El implementador de S1.3 terminó (filas 1–15 en verde) y dejó huecos y decisiones. S1.3 suma los
criterios 16 y 17.

1. **Transcripción vieja en `pack`** (`commands/pack.py` / `pack/assemble.py`): antes de usar la
   transcripción de un clip, `pack` calcula el sha256 del wav16 actual y lo compara con el
   `wav_sha256` guardado; si no coincide → `CheckFailed` (exit 1): "la transcripción de <id> es de
   otro audio; corre kcut transcribe". Sin esto, un wav16 regenerado daría frases con tiempos de otro
   audio. Criterio S1.3-16.
2. **Voz del audio sintético del criterio 7** (`tests/integration/test_transcribe_synth.py`): la voz
   `kal` de flite deforma "world" y Whisper escribe "well". El spec no fija la voz: se usa la primera
   de `slt`, `rms`, `awb`, `kal16`, `kal` con la que Whisper `medium` escribe "hello" y "world"
   literales, y el test vuelve a exigir los dos textos (±400 ms), como dice el criterio 7. Si
   ninguna voz sirve, el implementador para y devuelve BLOQUEADO con lo que transcribió cada una.
   Criterio S1.3-17.
3. **PyAV** (`transcribe/engine.py`; decisión del implementador, aceptada): `faster-whisper 1.2.1`
   llama `av.open(..., metadata_errors=...)`, que `av==19.0.1` del lock ya no acepta. `Engine` lee el
   wav16 con `audio/wavio.read_wav_s16_mono` y le pasa a Whisper el array float32 a 16 kHz; PyAV no
   interviene. Equivale a lo pedido (el wav16 ya es mono a 16 kHz) y da el largo real (001.7 punto 10).
4. **Decisiones del implementador aceptadas**:
   - `why` es opcional en `correcciones.json`.
   - Un id explícito que no existe o no tiene voz → `UsageError` (2).
   - JSON de `pack`: `{ok, md, tsv, clips: [{id, words, phrases[, disagreements]}], warnings: [...]}`.
   - El encabezado "sin sincronia" va en los clips con voz que no son maestro ni miembro.
   - Si el maestro no tiene transcripción, sus miembros se leen completos.
   - Palabras de Whisper con texto vacío se descartan.
   - Las palabras borradas por corrección quedan en el tsv con la marca `C`.
   - `<sonido sin texto ...>` va en línea propia, ordenada por tiempo.
   - `(¿alucinacion?)` va después de la palabra.
   - Dos clips con audio idéntico comparten caché.
   - La muletilla con mayúscula inicial solo lleva mayúscula en la primera letra del bloque.
   - Excepción `InventoryInvalid(ProjectError)` con `.field`.
   - Archivos fuera del árbol, partidos por la regla de 300 líneas: `src/kcut/transcribe/document.py`
     y `src/kcut/pack/assemble.py`.
5. **Ejemplos del writer**: manda la regla normativa (inicio con `floor`, fin con `ceil`, centésimas
   redondeadas) sobre los números del ejemplo; una palabra corregida lleva la marca `C`
   (`?VC`, no `?V`).
