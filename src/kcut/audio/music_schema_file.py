"""The `file` section of `edit/music.json` (spec S1.8b, 001.15): its shape (M01), what is wrong with
its numbers and its path (M03) and whether the song is approved in the manifest (M04, DS9).
Split from `music_schema.py` by the 300-line rule.

A message never repeats the path of the song: it can be a person's (`recursos/Maria-809.mp3`)
and Claude reads what is printed. `Issue.path` (`file.path`) says which key it is.
"""

from kcut.audio.music_model import FileCfg
from kcut.errors import GateError, InternalError, ProjectError
from kcut.issues import Issue
from kcut.params import ParamSpec, check_params
from kcut.paths import resolve_in_project, to_rel
from kcut.project import Project
from kcut.recursos.manifest import require_approved

MAX_PATH_CHARS = 200  # as the `image` of a component: a longer text is never looked up
# `src_in_f`, `fade_in_f` and `fade_out_f` go up to 12 h at 60 fps, the ceiling of the EDL (001.37)
MAX_FRAMES = 2_592_000
AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus")
FOLDER = "recursos/"
BAD_PATH = (
    "la ruta no vale: relativa al proyecto, sin .., sin letra de unidad "
    "y sin nombres reservados de Windows"
)
_FILE_SPECS = (
    ParamSpec("path", "path", True, max_len=MAX_PATH_CHARS, help_es="archivo de recursos/"),
    ParamSpec("src_in_f", "int", default=0, help_es="frame del archivo donde empieza"),
    ParamSpec("loop", "bool", default=False, help_es="repetirlo si es más corto que el video"),
    ParamSpec("fade_in_f", "int", default=0, help_es="frames de fundido de entrada"),
    ParamSpec("fade_out_f", "int", default=36, help_es="frames de fundido de salida"),
)


def parse_file_section(raw: object, issues: list[Issue]) -> FileCfg | None:
    """The shape of `file` (M01 in `issues`), or `None` if there is none or it has errors. The
    numbers may be negative here: that is an M03 of `file_problems`."""
    if raw is None:
        return None
    checked, found = check_params(_FILE_SPECS, raw, "file", "M01", None)
    issues.extend(found)
    if found:
        return None
    return FileCfg(
        str(checked["path"]),
        _int(checked["src_in_f"]),
        bool(checked["loop"]),
        _int(checked["fade_in_f"]),
        _int(checked["fade_out_f"]),
    )


def _int(value: object) -> int:
    """A whole number that `check_params` already checked (anything else is a bug)."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise InternalError("music_schema: se esperaba un entero ya revisado")


def file_problems(cfg: FileCfg, project: Project) -> list[Issue]:
    """M03 for what is wrong with the path, the numbers or the file (it is not there), M04 if the
    song is not approved. A manifest that cannot be read is not an issue of `music.json`: the
    ProjectError of `require_approved` goes up (exit 3), as a `sfx.json` that is not JSON does."""
    found: list[Issue] = []
    for name in ("src_in_f", "fade_in_f", "fade_out_f"):
        frames = getattr(cfg, name)
        if frames < 0:
            found.append(Issue("M03", "error", f"file.{name}", "no puede ser negativo"))
        elif frames > MAX_FRAMES:  # 001.37, point 6: never goes on to `ffmpeg` as a huge number
            text = f"no puede pasar de {MAX_FRAMES} frames (12 h a 60 fps)"
            found.append(Issue("M03", "error", f"file.{name}", text))
    where = "file.path"
    try:
        resolved = resolve_in_project(project.root, cfg.path)
        rel = to_rel(project.root, resolved)
    except ProjectError:  # the message of the path check quotes the path: it is not repeated
        found.append(Issue("M03", "error", where, BAD_PATH))
        return found
    if not rel.startswith(FOLDER):
        found.append(Issue("M03", "error", where, f"la canción tiene que estar en {FOLDER}"))
    elif resolved.suffix.lower() not in AUDIO_EXTENSIONS:
        text = f"la extensión tiene que ser una de: {' '.join(AUDIO_EXTENSIONS)}"
        found.append(Issue("M03", "error", where, text))
    elif not resolved.is_file():
        found.append(Issue("M03", "error", where, "la canción no existe en el proyecto"))
    else:
        try:
            require_approved(project, rel)
        except GateError as exc:
            found.append(Issue("M04", "error", where, exc.message_es))
    return found
