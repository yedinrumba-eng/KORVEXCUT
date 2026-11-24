"""The words the cut keeps, and the text Claude may read for each (spec S1.5a, 001.15 T1 and T2).

`words` have the corrected text as the transcript holds it (raw: the subtitles of the MP4 and the QA
need what was said). `shown` has what Claude reads: with `privacy.mask_pii` the same words after
`mask_pii` on the WHOLE list of their clip, so a number is found in its context as in
`transcripcion.md`. Everything that reaches Claude from the EDL takes its text from `shown`.
"""

from dataclasses import dataclass, field
from pathlib import Path

from kcut.edl.model import Edl, VoiceClip
from kcut.edl.words import KeptWord, map_words
from kcut.ingest.inventory import Inventory, Notice
from kcut.pack.assemble import cover
from kcut.pack.pii import UNMASKED, mask_pii_spans
from kcut.project import Project
from kcut.transcribe.loaded import LoadedWords, load_corrected
from kcut.transcribe.model import Word


@dataclass(frozen=True)
class KeptWords:
    """`words` (raw, so not in the `repr`: 001.24 point 11), `shown` (id -> the text for Claude;
    `""` for a word an address swallowed), `missing` (voice sources with no transcript) and
    whether `shown` is masked. `hidden` (001.47, point 7) has the ids of the kept words that sit
    inside a masked number or address, the bridges (`y`, `eh`) and separators too, whose text
    `mask_pii` leaves as it is; empty with `privacy.mask_pii = false`."""

    words: list[KeptWord] = field(repr=False)
    shown: dict[str, str]
    missing: tuple[str, ...]
    masked: bool
    hidden: frozenset[str]  # no default (001.49): a constructor that forgets it is a TypeError


def kept_words(
    project: Project,
    edl: Edl,
    inventory: Inventory,
    *,
    notices: list[Notice],
    log: Path | None,
) -> KeptWords:
    """The kept words of the voice clips of `edl`.

    Only the clips the EDL uses for voice (and their sync group) are loaded. A voice source with
    no transcript is in `missing`, in order of first appearance, and has no words. With
    `privacy.mask_pii` off, `shown` is the raw text and `notices` gets `pii_unmasked`."""
    sources = list(dict.fromkeys(c.src for c in edl.clips if isinstance(c, VoiceClip)))
    loaded = load_corrected(project, inventory, notices, log, sources)
    have = {src: loaded.words[src] for src in sources if src in loaded.words}
    words = map_words(edl, have, edl.fps)
    masked = project.config.privacy.mask_pii
    if not masked:
        notices.append(Notice("pii_unmasked", UNMASKED))
    kept = {word.id for word in words}
    shown: dict[str, str] = {}
    inside: set[str] = set()
    for src, corrected in have.items():
        words_of, hidden_of = _for_claude(project, loaded, src, corrected, masked)
        shown.update({w.id: w.text for w in words_of})
        inside |= hidden_of
    return KeptWords(
        words=words,
        shown={word_id: shown[word_id] for word_id in kept},
        missing=tuple(src for src in sources if src not in have),
        masked=masked,
        hidden=frozenset(inside & kept),
    )


def _for_claude(
    project: Project, loaded: LoadedWords, src: str, corrected: list[Word], masked: bool
) -> tuple[list[Word], set[str]]:
    """The words of a clip as Claude may read them: masked as a whole, and covered where another
    camera masked a number (the way `kcut view` and `pack` do); and the ids of the words that sit
    inside a masked number or address, in the same pass and with the same context (001.47)."""
    if not masked:
        return corrected, set()
    shown, _, inside = mask_pii_spans(corrected, project.config.transcribe.fillers)
    return cover(shown, loaded.covered.get(src, ()))[0], inside
