"""The words the cut keeps, and the text Claude may read for each (spec S1.5a, 001.15 T1 and T2).

`words` have the corrected text as the transcript holds it (raw: the subtitles of the MP4 and the QA
need what was said). `shown` has what Claude reads: with `privacy.mask_pii` the same words after
`mask_pii` on the WHOLE list of their clip, so a number is found in its context as in
`transcripcion.md`. Everything that reaches Claude from the EDL takes its text from `shown`.
"""

from dataclasses import dataclass
from pathlib import Path

from kcut.commands.pack import UNMASKED
from kcut.edl.model import Edl, VoiceClip
from kcut.edl.words import KeptWord, map_words
from kcut.ingest.inventory import Inventory, Notice
from kcut.pack.assemble import cover
from kcut.pack.pii import mask_pii
from kcut.project import Project
from kcut.transcribe.loaded import LoadedWords, load_corrected
from kcut.transcribe.model import Word


@dataclass(frozen=True)
class KeptWords:
    """`words` (raw), `shown` (id -> the text for Claude; `""` for a word an address swallowed),
    `missing` (voice sources with no transcript) and whether `shown` is masked."""

    words: list[KeptWord]
    shown: dict[str, str]
    missing: tuple[str, ...]
    masked: bool


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
    for src, corrected in have.items():
        shown.update({w.id: w.text for w in _for_claude(project, loaded, src, corrected, masked)})
    return KeptWords(
        words=words,
        shown={word_id: shown[word_id] for word_id in kept},
        missing=tuple(src for src in sources if src not in have),
        masked=masked,
    )


def _for_claude(
    project: Project, loaded: LoadedWords, src: str, corrected: list[Word], masked: bool
) -> list[Word]:
    """The words of a clip as Claude may read them: masked as a whole, and covered where another
    camera masked a number (the way `kcut view` and `pack` do)."""
    if not masked:
        return corrected
    shown = mask_pii(corrected, project.config.transcribe.fillers)[0]
    return cover(shown, loaded.covered.get(src, ()))[0]
