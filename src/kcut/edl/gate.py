"""Gate 1: is the strategy approved? (spec S1.5a, 001.4). `render` and `build` refuse to run without
it (exit 5); `edl check` only reports it.

The answer is "no" at the least doubt: the front-matter of `edit/estrategia.md` is read line by
line with a strict pattern, so a line that smuggles a second `aprobado: si` behind a Unicode line
separator is not approval. And the value is compared exactly (001.24, point 3): `❌ sí` or `[ ] sí`
are not `sí`, even though a human reads them as a no.
"""

import re
import unicodedata
from dataclasses import dataclass

from kcut.edl.shown import shown_text
from kcut.errors import GateError, ProjectError
from kcut.jsonio import read_capped
from kcut.paths import resolve_in_project
from kcut.project import Project

STRATEGY_REL = "edit/estrategia.md"
MAX_STRATEGY_BYTES = 256 * 1024  # a strategy is a page or two; a bigger file is not read
MAX_LINE = 1000  # characters of a front-matter line (the pattern below is not linear on long ones)
_LINE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*?)[ \t]*")
_BAD_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})
_YES = frozenset({"si", "sí"})


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
    value = front["aprobado"]
    if not _says_yes(value):
        said = shown_text(value)  # the text of the file is never echoed (001.24, point 6)
        return GateStatus(False, STRATEGY_REL, f"la estrategia no está aprobada (aprobado: {said})")
    return GateStatus(True, STRATEGY_REL, "estrategia aprobada")


def _says_yes(value: str) -> bool:
    """Is the value of `aprobado`, without the U+0020 at its edges, `si` or `sí` after NFC and
    `.lower()`? Nothing else: no punctuation, no marks, no invisible letters. Not `casefold`: it
    turns the long s (U+017F) into `s`, and `ſi` would approve (001.25, point 13)."""
    return unicodedata.normalize("NFC", value.strip(" ")).lower() in _YES


def _chomp(line: str) -> str:
    return line[:-1] if line.endswith("\r") else line
