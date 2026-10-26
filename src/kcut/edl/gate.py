"""Gate 1: is the strategy approved? (spec S1.5a, 001.4). `render` and `build` refuse to run without
it (exit 5); `edl check` only reports it.

The answer is "no" at the least doubt: the front-matter of `edit/estrategia.md` is read line by
line with a strict pattern, so a line that smuggles a second `aprobado: si` behind a Unicode line
separator is not approval.
"""

import re
import unicodedata
from dataclasses import dataclass

from kcut.errors import GateError, ProjectError
from kcut.jsonio import read_capped
from kcut.paths import resolve_in_project
from kcut.project import Project
from kcut.schema_util import describe_value
from kcut.text.normalize import norm_token

STRATEGY_REL = "edit/estrategia.md"
MAX_STRATEGY_BYTES = 256 * 1024  # a strategy is a page or two; a bigger file is not read
MAX_LINE = 1000  # characters of a front-matter line (the pattern below is not linear on long ones)
_LINE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*?)[ \t]*")
_BAD_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


@dataclass(frozen=True)
class GateStatus:
    approved: bool
    file: str
    reason_es: str


def read_front_matter(text: str) -> dict[str, str]:
    """The `key: value` pairs between the two `---` lines that open `text`.

    Lines are split by `\\n` only (never `str.splitlines()`, which also cuts at U+0085, U+2028 and
    U+2029) and one final `\\r` is dropped. Every line has to match `key: value`, a value cannot
    hold a character of category Cc, Cf, Zl or Zp, and `aprobado` cannot be repeated. Anything
    else, a missing opening or closing `---` included, is a GateError that says why.
    """
    lines = text.split("\n")
    if _chomp(lines[0]) != "---":
        raise GateError("el archivo no empieza con una línea ---")
    found: dict[str, str] = {}
    for number, raw in enumerate(lines[1:], start=2):
        line = _chomp(raw)
        if line == "---":
            return found
        if line == "" and number == len(lines):  # the empty piece after the last newline
            break
        if len(line) > MAX_LINE:
            raise GateError(f"la línea {number} del front-matter es demasiado larga")
        match = _LINE.fullmatch(line)
        if match is None:
            raise GateError(f"la línea {number} del front-matter no es 'clave: valor'")
        key, value = match.group(1), match.group(2)
        if any(unicodedata.category(ch) in _BAD_CATEGORIES for ch in value):
            raise GateError(f"la línea {number} del front-matter lleva caracteres de control")
        if key == "aprobado" and key in found:
            raise GateError("la clave aprobado aparece más de una vez")
        found[key] = value
    raise GateError("el front-matter no cierra con una línea ---")


def strategy_approved(project: Project) -> GateStatus:
    """Is `edit/estrategia.md` approved? Only if its front-matter reads cleanly and `aprobado` is
    `si` (or `sí`, whatever the case). A missing, unreadable or doubtful file is "not approved"
    with the reason."""
    try:
        text = read_capped(resolve_in_project(project.root, STRATEGY_REL), MAX_STRATEGY_BYTES)
        front = read_front_matter(text.decode("utf-8"))
    except FileNotFoundError:
        return GateStatus(False, STRATEGY_REL, f"falta {STRATEGY_REL}")
    except (OSError, ProjectError, UnicodeDecodeError):
        return GateStatus(False, STRATEGY_REL, f"no pude leer {STRATEGY_REL}")
    except GateError as exc:
        return GateStatus(False, STRATEGY_REL, f"{STRATEGY_REL}: {exc.message_es}")
    if "aprobado" not in front:
        return GateStatus(False, STRATEGY_REL, "el front-matter no tiene la clave aprobado")
    if norm_token(front["aprobado"]) != "si":
        said = describe_value(front["aprobado"])
        return GateStatus(False, STRATEGY_REL, f"la estrategia no está aprobada (aprobado: {said})")
    return GateStatus(True, STRATEGY_REL, "estrategia aprobada")


def _chomp(line: str) -> str:
    return line[:-1] if line.endswith("\r") else line
