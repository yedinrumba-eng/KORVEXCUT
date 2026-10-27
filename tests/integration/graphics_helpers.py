"""Helpers of the `graphics` integration tests: plant a transcript of a1 in a copy of the synthetic
project, and read what `kcut graphics check --json` printed."""

import hashlib
from pathlib import Path

from kcut.ingest.inventory import load_inventory as read_inventory
from kcut.paths import resolve_in_project
from kcut.project import open_project
from kcut.transcribe.cache import file_sha256, save_transcript, wav16_length_ms
from kcut.transcribe.model import Segment, Transcript, Word
from tests.unit.transcribe_fakes import params_for

# What a1 says, as (text, start ms, end ms) of its own clock. The example EDL keeps the source
# frames 60 to 239 of a1 (2000 ms to 8000 ms) at output frame 30, so all of this is kept, and it
# falls between output frames 105 and 204: after the big graphics of the fixture (0-30 and 40-80)
# that hide the subtitles, and before the closing one (315-345).
PHONE_WORDS = [
    ("Llama", 4500, 4800),
    ("972", 4900, 5200),
    ("808", 5300, 5600),
    ("3211", 5700, 6100),
    ("ya", 6300, 6600),
    ("Higgsfield,", 6700, 7200),
    ("gracias", 7300, 7800),
]


def plant_words(root: Path, words: list[tuple[str, int, int]] | None = None) -> None:
    """Write the transcript of a1 into the cache of `root` (`save_transcript`), like `kcut
    transcribe` would, with `words` (by default `PHONE_WORDS`: a phone number said in digits)."""
    spoken = PHONE_WORDS if words is None else words
    project = open_project(str(root))
    clip = read_inventory(root / ".kcut" / "inventory.json").by_id("a1")
    assert clip is not None and clip.work is not None and clip.work.wav16 is not None
    wav = resolve_in_project(root, clip.work.wav16)
    made = [Word(f"a1:w{i:04d}", i, text, s, e, 0.9) for i, (text, s, e) in enumerate(spoken)]
    segment = Segment(made[0].s_ms, made[-1].e_ms, " ".join(w.text for w in made))
    transcript = Transcript(
        "a1", "ab" * 32, "es", 0.98, wav16_length_ms(wav), made, [segment], params_for(), 1.0
    )
    save_transcript(project, transcript, file_sha256(wav))


def tree_hash(folder: Path) -> str:
    """One hash of the names and the bytes of every file under `folder`."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        digest.update(path.relative_to(folder).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()
