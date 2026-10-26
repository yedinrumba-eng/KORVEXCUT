"""Word-level corrections written by Claude in `edit/correcciones.json` (spec DS8).

A correction names the word by id and carries the text it expects to replace, so that a new
transcription never gets silently patched with fixes meant for another one (lesson 3: fixing by
text eats other phrases).
"""

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from kcut.errors import MAX_MESSAGE, CheckFailed
from kcut.jsonio import MAX_CORRECTIONS_BYTES, read_json
from kcut.project import Project
from kcut.schema_util import (
    SchemaError,
    describe_value,
    join_path,
    obj,
    only_keys,
    opt_str,
    project_error,
    req_list,
    req_str,
)
from kcut.transcribe.model import Word

SCHEMA = "kcut.correcciones/1"
FILE_NAME = "correcciones.json"
MAX_ITEMS = 50_000
MAX_NAMED = 20  # ids a CheckFailed message names; the rest are counted
MAX_TOKENS = 20_000  # tokens the corrections of one clip may produce (spec 001.16, point 9)
MAX_TOTAL_TOKENS = 200_000  # and the corrections of all the clips together (001.17, point 9)
MAX_SHOWN = 80  # characters of a word or an `expect` quoted in a message
_WORD_ID = re.compile(r"[a-z][0-9]{1,6}:w[0-9]{4,8}")
_MISMATCH = "la corrección apunta a otra palabra (¿cambió la transcripción?)"


@dataclass(frozen=True)
class Correction:
    word: str
    expect: str
    text: str
    why: str = ""


def load_corrections(project: Project) -> dict[str, Correction]:
    """Corrections of the project by word id; a project without the file has none.

    The file belongs to the user, so a malformed one is a ProjectError (exit 3).
    """
    path = project.layout.edit / FILE_NAME
    if not path.exists():
        return {}
    try:
        return parse_corrections(read_json(path, MAX_CORRECTIONS_BYTES))
    except SchemaError as exc:
        raise project_error(FILE_NAME, exc) from None


def parse_corrections(data: object) -> dict[str, Correction]:
    """Validate the decoded document: strict keys and types, one correction per word."""
    d = obj(data, "")
    only_keys(d, {"schema", "items"}, "")
    schema = req_str(d, "schema", "")
    if schema != SCHEMA:
        raise SchemaError("schema", f"se esperaba {SCHEMA} (vino {describe_value(schema)})")
    items = req_list(d, "items", "")
    if len(items) > MAX_ITEMS:
        raise SchemaError("items", f"admite como máximo {MAX_ITEMS} correcciones")
    found: dict[str, Correction] = {}
    for index, raw in enumerate(items):
        where = join_path("items", index)
        item = obj(raw, where)
        only_keys(item, {"word", "expect", "text", "why"}, where)
        word = req_str(item, "word", where)
        if _WORD_ID.fullmatch(word) is None:
            raise SchemaError(join_path(where, "word"), "debe ser un id de palabra como a1:w0031")
        if word in found:
            raise SchemaError(
                join_path(where, "word"), "está repetida (una corrección por palabra)"
            )
        found[word] = Correction(
            word=word,
            expect=req_str(item, "expect", where, max_len=200, min_len=1),
            text=req_str(item, "text", where, max_len=200),
            why=opt_str(item, "why", where, "", max_len=300),
        )
    return found


def apply(words: Sequence[Word], corr: Mapping[str, Correction]) -> list[Word]:
    """Words with the corrections applied, each touched word marked `corrected=True`.

    `text` empty deletes the word: it stays in the list with `text == ""` (captions and QA skip
    it). `text` with several words splits the word into tokens that share its duration in
    proportion to `len(token)`; the first token keeps the id, the others are `<id>.1`, `<id>.2`.
    A correction whose `expect` is not the word's raw text raises CheckFailed.
    """
    result: list[Word] = []
    produced = 0
    for word in words:
        item = corr.get(word.id)
        if item is None:
            result.append(word)
            continue
        if item.expect.strip() != word.text.strip():
            expected, actual = _one_line(item.expect), _one_line(word.text)
            raise CheckFailed(f'{_MISMATCH}: {word.id} esperaba "{expected}", dice "{actual}"')
        pieces = _corrected(word, item.text)
        produced += len(pieces)
        if produced > MAX_TOKENS:
            raise CheckFailed(
                f"las correcciones de {word.id.partition(':')[0]} producen más de {MAX_TOKENS} "
                "palabras; revisa edit/correcciones.json"
            )
        result.extend(pieces)
    return result


def apply_all(
    words_by_clip: Mapping[str, Sequence[Word]], corr: Mapping[str, Correction]
) -> dict[str, list[Word]]:
    """`apply` to each clip. The tokens the corrections produce are counted across all the clips:
    over `MAX_TOTAL_TOKENS` is CheckFailed, whatever each clip alone would allow."""
    fixed: dict[str, list[Word]] = {}
    produced = 0
    for clip_id, words in words_by_clip.items():
        fixed[clip_id] = apply(words, corr)
        produced += sum(word.corrected for word in fixed[clip_id])
        if produced > MAX_TOTAL_TOKENS:
            raise CheckFailed(
                f"las correcciones producen más de {MAX_TOTAL_TOKENS} palabras entre todos los "
                "clips; revisa edit/correcciones.json"
            )
    return fixed


def unmatched(
    corr: Mapping[str, Correction], words: Iterable[Word], clips: Collection[str]
) -> list[str]:
    """Ids of corrections that belong to one of `clips` but name no word of `words`.

    `words` are the raw words of those clips. Corrections of other clips are not judged here.
    """
    present = {word.id for word in words}
    return sorted(
        word_id for word_id in corr if word_id.partition(":")[0] in clips and word_id not in present
    )


def mismatch_message(word_ids: Sequence[str]) -> str:
    """The CheckFailed text for corrections that point at words the transcript does not have.

    It names the first 20 and counts the rest (`(y 49980 más)`): a hostile file could list 50 000.
    The whole message fits the 300 characters `cli` allows (spec 001.14 point 7, 001.16 point 10):
    ids go in while the room that is left after the fixed text and the count allows it, so a long
    id names fewer than 20 and the count is never the part that gets cut.
    """
    head = f"{_MISMATCH}: "
    total = len(word_ids)
    named: list[str] = []
    used = len(head)
    for index, word_id in enumerate(word_ids[:MAX_NAMED]):
        left = total - index - 1  # ids that would stay out if this one is the last one named
        tail = len(f" (y {left} más)") if left else 0
        if used + len(word_id) + (2 if named else 0) + tail > MAX_MESSAGE:
            break
        used += len(word_id) + (2 if named else 0)
        named.append(word_id)
    more = f" (y {total - len(named)} más)" if total > len(named) else ""
    return head + ", ".join(named) + more


def _one_line(text: str) -> str:
    """`text` on one line and at most 80 characters (it goes into an error message)."""
    flat = text.replace("\r", " ").replace("\n", " ")
    return flat if len(flat) <= MAX_SHOWN else flat[: MAX_SHOWN - 3] + "..."


def _corrected(word: Word, text: str) -> list[Word]:
    tokens = text.split()
    if len(tokens) <= 1:
        return [replace(word, text=tokens[0] if tokens else "", corrected=True)]
    weights = [len(token) for token in tokens]
    total, whole = word.e_ms - word.s_ms, sum(weights)
    pieces: list[Word] = []
    cursor = word.s_ms
    for k, token in enumerate(tokens):
        end = word.e_ms if k == len(tokens) - 1 else cursor + total * weights[k] // whole
        piece_id = word.id if k == 0 else f"{word.id}.{k}"
        pieces.append(replace(word, id=piece_id, text=token, s_ms=cursor, e_ms=end, corrected=True))
        cursor = end
    if total < len(tokens) or any(piece.e_ms <= piece.s_ms for piece in pieces):
        raise CheckFailed(
            f"la palabra {word.id} dura {total} ms y no se puede partir en {len(tokens)}"
        )
    return pieces
