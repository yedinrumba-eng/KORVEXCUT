"""The words of every clip as the commands that show them to Claude need them (spec 001.15, T1).

`kcut pack` and `kcut view` (and, later, the EDL words and the subtitles) start from the same
thing: the cached transcripts that belong to their audio, with the corrections applied and the
rules about private data kept. This is where that is done once. It does not mask (each consumer
calls `pack.pii.mask_pii` on the WHOLE list of a clip, T2) and it does not vote.
"""

from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

from kcut.errors import CheckFailed
from kcut.ingest.inventory import Clip, Inventory, Notice
from kcut.pack.crosscam import covered_by_sync
from kcut.pack.guards import refuse_masked, refuse_unmasked
from kcut.paths import resolve_in_project
from kcut.project import Project
from kcut.text.corrections import apply_all, load_corrections, mismatch_message, unmatched
from kcut.transcribe import cache
from kcut.transcribe.model import Transcript, Word

_VOICE_CLASSES = ("video_voz", "audio")


@dataclass(frozen=True)
class LoadedWords:
    """By clip id: the raw transcript and its words with the corrections applied, and the raw ids
    of the words that sit under a number another camera masks (`covered`, 001.17 point 2; empty
    when `privacy.mask_pii` is off). Whoever shows the words masks them and covers those ids."""

    transcripts: dict[str, Transcript]
    words: dict[str, list[Word]]
    covered: dict[str, set[str]] = field(default_factory=dict)


def has_voice(clip: Clip) -> bool:
    """Does the clip have audible speech to transcribe (a voice class that is not silent)?"""
    audible = clip.audio is not None and not clip.audio.silent
    return clip.clip_class in _VOICE_CLASSES and audible


def wav16_or_none(project: Project, clip: Clip) -> Path | None:
    """The clip's wav16 file, or None if the inventory has none or the file is gone."""
    if clip.work is None or clip.work.wav16 is None:
        return None
    path = resolve_in_project(project.root, clip.work.wav16)
    return path if path.is_file() else None


def sync_group(inventory: Inventory, clip_ids: Collection[str]) -> set[str]:
    """`clip_ids` plus, for each one that is the master or a member of the camera sync, the
    master and all its members: what a clip needs to be read the way `pack` reads it."""
    sync = inventory.sync
    group = {member.id for member in sync.members}
    if sync.master is not None:
        group.add(sync.master)
    wanted = set(clip_ids)
    return wanted | group if wanted & group else wanted


def load_corrected(
    project: Project,
    inventory: Inventory,
    notices: list[Notice],
    log: Path | None,
    clip_ids: Collection[str] | None = None,
) -> LoadedWords:
    """The transcripts of the clips with voice and a wav16, and their corrected words.

    A transcript that does not fit its wav16 counts as missing (a notice, not an error), and one
    made from another audio is `CheckFailed`. A correction that names a word the transcript no
    longer has is `CheckFailed`: it was written for another transcription. With
    `privacy.mask_pii`, a correction on a masked word, or one that would open a masked number,
    is `CheckFailed` too (001.13 point 5, 001.17 point 5). `log` is the run's log; the loaders
    here report through `notices`, which the caller prints. `covered` is computed once here.

    With `clip_ids` only those clips and their sync group (master and members) are read: a
    command about one clip does not hash every wav16 of the project (001.20, point 11).
    Corrections of the clips left out are not judged. Without it, every clip, as `pack` does.
    """
    corrections = load_corrections(project)
    transcripts: dict[str, Transcript] = {}
    index = cache.read_index(project, notices)  # once for the whole run
    wanted = None if clip_ids is None else sync_group(inventory, clip_ids)
    for clip in inventory.clips:
        if wanted is not None and clip.id not in wanted:
            continue
        wav = wav16_or_none(project, clip) if has_voice(clip) else None
        if wav is None:
            continue
        length = cache.wav16_length_ms(wav)  # a wav16 whose header lies stops the run
        if clip.id not in index:
            continue
        # the hash of the audio is compared first: a changed wav16 is "another audio" (row 16),
        # whatever its length is, and only then do the words have to fit its length (row 21)
        sha = cache.file_sha256(wav)
        found = cache.load_transcript(project, clip.id, notices, length, index, sha)
        if found is not None:
            transcripts[clip.id] = found
    lost = unmatched(
        corrections, [w for t in transcripts.values() for w in t.words], set(transcripts)
    )
    if lost:
        raise CheckFailed(mismatch_message(lost))
    fillers = project.config.transcribe.fillers
    mask = project.config.privacy.mask_pii
    covered: dict[str, set[str]] = {}
    if mask:  # what another camera's mask covers is masked before any correction is looked at
        covered = covered_by_sync(transcripts, inventory.sync, fillers)
        refuse_masked(transcripts, corrections, fillers, covered)
    raw = {clip_id: t.words for clip_id, t in transcripts.items()}
    words = apply_all(raw, corrections)
    if mask:  # a correction elsewhere may not open a masked number
        refuse_unmasked(raw, words, fillers)
    return LoadedWords(transcripts, words, covered)
