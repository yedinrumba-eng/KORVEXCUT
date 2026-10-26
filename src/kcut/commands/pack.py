"""kcut pack: turns the cached transcripts into `edit/transcripcion.md` and `edit/palabras.tsv`.

It reads the inventory, the transcripts, the wav16 files (for the energy) and the corrections.
Claude reads the md to decide the cuts; the tsv holds the id of every word.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from kcut.analysis.energy import rms_db_stream
from kcut.audio.wavio import PEAK_BLOCK_FRAMES, WavReader, open_wav
from kcut.console import Out
from kcut.errors import CheckFailed, ProjectError
from kcut.ingest.inventory import Clip, Inventory, Notice
from kcut.jsonio import write_text_atomic
from kcut.pack.assemble import HOP_MS, ClipParts, assemble_clip, displayed_alts
from kcut.pack.crosscam import covered_by_sync
from kcut.pack.guards import refuse_masked, refuse_unmasked
from kcut.pack.pii import mask_text
from kcut.pack.votes import tally
from kcut.pack.writer import UNTRANSCRIBED, MdClip, TsvRow, render_md, render_tsv, voting_status
from kcut.paths import resolve_in_project
from kcut.project import Project, load_inventory, open_project
from kcut.text.corrections import apply_all, load_corrections, mismatch_message, unmatched
from kcut.transcribe.cache import (
    WAV16_RATE,
    file_sha256,
    load_transcript,
    read_index,
    wav16_length_ms,
)
from kcut.transcribe.model import Transcript, Word

NAME = "pack"
HELP_ES = "Empaqueta las transcripciones en edit/transcripcion.md y edit/palabras.tsv"
MD_NAME = "transcripcion.md"
TSV_NAME = "palabras.tsv"
_NOT_VOICE = ("imagen", "doc", "desconocido")
UNMASKED = "PII sin enmascarar (privacy.mask_pii = false)"
_WAV_SCALE = np.float32(32768.0)


@dataclass
class _Run:
    """What one `kcut pack` knows once everything is loaded."""

    project: Project
    inventory: Inventory
    transcripts: dict[str, Transcript]
    words: dict[str, list[Word]]  # after the corrections
    alts: dict[str, str] = field(default_factory=dict)  # the master's votes, by word id
    disagreements: dict[str, int] = field(default_factory=dict)  # per synchronized member
    covered: dict[str, set[str]] = field(default_factory=dict)  # words under another camera's mask


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    return subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)


def run(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    notices: list[Notice] = []
    state = _load(project, notices, getattr(args, "log", None))
    clips: list[MdClip] = []
    rows: list[TsvRow] = []
    docs: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not project.config.privacy.mask_pii:  # every run says so: Claude is reading raw PII
        warnings.append({"id": None, "code": "pii_unmasked", "message_es": UNMASKED})
        out.warn(f"pii_unmasked: {UNMASKED}")
    for clip in state.inventory.clips:
        if clip.clip_class in _NOT_VOICE:
            continue
        if not _has_voice(clip):
            clips.append(MdClip(clip.id, clip.file, role="sin audio"))
        elif clip.id not in state.transcripts:
            message = f"{clip.id}: sin transcribir; corre kcut transcribe"
            warnings.append({"id": clip.id, "code": "not_transcribed", "message_es": message})
            out.line("AVISO", message)
            clips.append(MdClip(clip.id, clip.file, status=UNTRANSCRIBED))
        else:
            parts = _parts(state, clip)
            rows += parts.rows
            clips.append(_md_clip(state, clip, parts))
            docs.append(_doc(state, clip, parts))
    cfg = project.config
    name = cfg.project.name
    if cfg.privacy.mask_pii:  # the names Claude reads in the headings are text too (001.16)
        fillers = cfg.transcribe.fillers
        name = mask_text(name, fillers, parts=False)  # a name, not a path
        clips = [replace(c, file=mask_text(c.file, fillers)) for c in clips]
    md = render_md(name, cfg.output.fps, cfg.analysis.long_pause_ms, clips)
    write_text_atomic(project.layout.edit / MD_NAME, md)
    write_text_atomic(project.layout.edit / TSV_NAME, render_tsv(cfg.output.fps, rows))
    for notice in notices:
        out.warn(f"{notice.code}: {notice.detail}")
    out.line("OK", f"edit/{MD_NAME} y edit/{TSV_NAME}: {len(docs)} clips con texto")
    out.result(
        {
            "ok": True,
            "md": f"edit/{MD_NAME}",
            "tsv": f"edit/{TSV_NAME}",
            "clips": docs,
            "warnings": warnings,
        }
    )
    return 0


def _has_voice(clip: Clip) -> bool:
    audible = clip.audio is not None and not clip.audio.silent
    return clip.clip_class in ("video_voz", "audio") and audible


def _load(project: Project, notices: list[Notice], log: Path | None) -> _Run:
    """Transcripts with the corrections applied, and the votes between cameras.

    A correction that names a word the transcript no longer has is CheckFailed: it was written
    for another transcription. A transcript that does not fit its wav16 counts as missing.
    """
    inventory = load_inventory(project, log)
    corrections = load_corrections(project)
    transcripts: dict[str, Transcript] = {}
    index = read_index(project, notices)  # once for the whole run
    for clip in inventory.clips:
        wav = _wav16_or_none(project, clip) if _has_voice(clip) else None
        if wav is None:
            continue
        length = wav16_length_ms(wav)  # a wav16 whose header lies stops the run, transcript or not
        if clip.id not in index:
            continue
        # the hash of the audio is compared first: a changed wav16 is "another audio" (row 16),
        # whatever its length is, and only then do the words have to fit its length (row 21)
        sha = file_sha256(wav)
        found = load_transcript(project, clip.id, notices, length, index, sha)
        if found is not None:
            transcripts[clip.id] = found
    lost = unmatched(
        corrections, [w for t in transcripts.values() for w in t.words], set(transcripts)
    )
    if lost:
        raise CheckFailed(mismatch_message(lost))
    fillers = project.config.transcribe.fillers
    mask = project.config.privacy.mask_pii
    # what another camera's mask covers is masked before any correction is looked at
    covered = covered_by_sync(transcripts, inventory.sync, fillers) if mask else {}
    if mask:
        refuse_masked(transcripts, corrections, fillers, covered)
    raw = {clip_id: t.words for clip_id, t in transcripts.items()}
    words = apply_all(raw, corrections)
    if project.config.privacy.mask_pii:  # a correction elsewhere may not open a masked number
        refuse_unmasked(raw, words, fillers)
    state = _Run(project, inventory, transcripts, words)
    state.covered = covered  # a number masked in one camera is masked in all
    master = inventory.sync.master
    if master in words:
        # the vote is on the RAW words: the tsv keeps the trace of why a word was corrected
        members = [m for m in inventory.sync.members if m.id in transcripts]
        result = tally(
            transcripts[master].words, [(transcripts[m.id].words, m.offset_ms) for m in members]
        )  # every member is voted once; its own disagreements come out of the same pass
        state.alts = displayed_alts(
            result, [transcripts[m.id].words for m in members], fillers, mask
        )
        state.disagreements.update(
            {m.id: n for m, n in zip(members, result.disagreements, strict=True)}
        )
    return state


def _spoken(words: list[Word]) -> list[Word]:
    """The words that still have text (a deleted word has none)."""
    return [w for w in words if w.text]


def _parts(state: _Run, clip: Clip) -> ClipParts:
    cfg = state.project.config
    transcript = state.transcripts[clip.id]
    alts = state.alts if clip.id == state.inventory.sync.master else {}
    db = _energy(_wav16(state.project, clip))
    return assemble_clip(
        clip.id,
        transcript.words,
        state.words[clip.id],
        db,
        cfg.analysis,
        cfg.transcribe.fillers,
        alts,
        cfg.privacy.mask_pii,
        state.covered.get(clip.id, ()),
    )


def _md_clip(state: _Run, clip: Clip, parts: ClipParts) -> MdClip:
    sync = state.inventory.sync
    transcript = state.transcripts[clip.id]
    length = wav16_length_ms(_wav16(state.project, clip))  # the audio's own length (001.7)
    head = (clip.id, clip.file, length, transcript.language, transcript.language_p)
    if clip.id == sync.master:
        return MdClip(*head, "maestro de sincronia", phrases=parts.phrases, sounds=parts.sounds)
    member = next((m for m in sync.members if m.id == clip.id), None)
    if member is None:
        return MdClip(*head, "sin sincronia", phrases=parts.phrases, sounds=parts.sounds)
    role = f"sincronizado con {sync.master}: {_signed_seconds(member.offset_ms)} s"
    if clip.id not in state.disagreements:  # the master has no transcript: read it in full
        return MdClip(*head, role, phrases=parts.phrases, sounds=parts.sounds)
    count = len(_spoken(state.words[clip.id]))
    status = voting_status(count, state.disagreements[clip.id], sync.master or "")
    return MdClip(*head, role, status=status)


def _doc(state: _Run, clip: Clip, parts: ClipParts) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "id": clip.id,
        "words": len(state.transcripts[clip.id].words),
        "phrases": len(parts.phrases),
    }
    if clip.id in state.disagreements:
        doc["disagreements"] = state.disagreements[clip.id]
    return doc


def _signed_seconds(ms: int) -> str:
    """`+4.722` / `-0.040`: milliseconds as signed seconds with three decimals."""
    return f"{'-' if ms < 0 else '+'}{abs(ms) // 1000}.{abs(ms) % 1000:03d}"


def _wav16_or_none(project: Project, clip: Clip) -> Path | None:
    """The clip's wav16 file, or None if the inventory has none or the file is gone."""
    if clip.work is None or clip.work.wav16 is None:
        return None
    path = resolve_in_project(project.root, clip.work.wav16)
    return path if path.is_file() else None


def _wav16(project: Project, clip: Clip) -> Path:
    if clip.work is None or clip.work.wav16 is None:
        raise ProjectError(f"{clip.id} no tiene wav16; corre kcut ingest")
    path = resolve_in_project(project.root, clip.work.wav16)
    if not path.is_file():
        raise ProjectError(f"falta el wav16 de {clip.id}; corre kcut ingest")
    return path


def _energy(wav: Path) -> NDArray[np.float32]:
    """Level of the wav16 per 10 ms block, read in pieces so a long recording stays flat."""
    wav16_length_ms(wav)  # checks it is a mono 16-bit 16 kHz wav
    with open_wav(wav, "wav16") as handle:
        return rms_db_stream(_chunks(handle), WAV16_RATE, HOP_MS)


def _chunks(handle: WavReader) -> Iterator[NDArray[np.float32]]:
    while block := handle.readframes(PEAK_BLOCK_FRAMES):
        yield np.frombuffer(block, dtype="<i2").astype(np.float32) / _WAV_SCALE
