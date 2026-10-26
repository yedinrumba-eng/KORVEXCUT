"""kcut transcribe: Whisper, word by word, once per audio (the cache remembers the rest)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from kcut.console import Out, Progress
from kcut.errors import ProjectError, UsageError
from kcut.ingest.inventory import Clip, Inventory, Notice
from kcut.paths import resolve_in_project
from kcut.project import Project, load_inventory, open_project
from kcut.transcribe.cache import (
    build_params,
    cache_key,
    engine_label,
    file_sha256,
    load_matching,
    point_index,
    read_index,
    save_transcript,
    wav16_length_ms,
)
from kcut.transcribe.engine import Engine, build_prompt
from kcut.transcribe.model import Transcript, Word, word_id

NAME = "transcribe"
HELP_ES = "Transcribe el audio con Whisper, palabra por palabra, y guarda el resultado en caché"


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)
    sub.add_argument("ids", nargs="*", metavar="IDS", help="ids de clip (por defecto, todos)")
    sub.add_argument("--force", action="store_true", help="repite aunque haya caché válida")
    sub.add_argument(
        "--allow-download",
        action="store_true",
        help="permite bajar el modelo de Whisper si falta (descarga única)",
    )
    return sub


def run(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    clips = _select(load_inventory(project, getattr(args, "log", None)), list(args.ids), out)
    if not clips:
        out.line("INFO", "no hay clips con voz para transcribir")
    notices: list[Notice] = []
    prompt = build_prompt(project.config, notices)
    params = build_params(project.config.transcribe, prompt, engine_label())
    index = read_index(project, notices)  # once: every clip below updates this dict
    engine: Engine | None = None
    documents: list[dict[str, Any]] = []
    try:
        for clip in clips:
            wav = _wav16(project, clip)
            sha = file_sha256(wav)
            key = cache_key(sha, params)
            transcript = None
            if not args.force:
                length = wav16_length_ms(wav)
                transcript = load_matching(project, clip.id, key, sha, params, notices, length)
            cached = transcript is not None
            if transcript is None:
                engine = engine or Engine(project.config.transcribe, args.allow_download)
                transcript = _transcribe(engine, clip, wav, prompt, params, key)
                save_transcript(project, transcript, sha, index)
            else:
                point_index(project, clip.id, key, index)
            documents.append(_document(transcript, cached))
            _say(out, documents[-1])
    finally:
        for notice in notices:
            out.warn(f"{notice.code}: {notice.detail}")
    out.result({"ok": True, "clips": documents})
    return 0


def _select(inventory: Inventory, ids: list[str], out: Out) -> list[Clip]:
    """The clips to transcribe: the ones named, or every clip with voice and a wav16."""
    if not ids:
        chosen: list[Clip] = []
        for item in inventory.clips:
            if not _has_voice(item):
                continue
            if item.work is None or item.work.wav16 is None:
                out.warn(f"{item.id}: no tiene wav16 (¿demasiado largo?); no se transcribe")
                continue
            chosen.append(item)
        return chosen
    picked: list[Clip] = []
    for clip_id in dict.fromkeys(ids):
        clip = inventory.by_id(clip_id)
        if clip is None:
            raise UsageError(f"el clip {clip_id} no está en el inventario (corre kcut ingest)")
        if not _has_voice(clip):
            raise UsageError(f"{clip_id} no es un clip con voz (clase {clip.clip_class})")
        picked.append(clip)
    return picked


def _has_voice(clip: Clip) -> bool:
    audible = clip.audio is not None and not clip.audio.silent
    return clip.clip_class in ("video_voz", "audio") and audible


def _wav16(project: Project, clip: Clip) -> Path:
    if clip.work is None or clip.work.wav16 is None:
        raise ProjectError(f"{clip.id} no tiene wav16; corre kcut ingest")
    path = resolve_in_project(project.root, clip.work.wav16)
    if not path.is_file():
        raise ProjectError(f"falta el wav16 de {clip.id}; corre kcut ingest")
    return path


def _transcribe(
    engine: Engine, clip: Clip, wav: Path, prompt: str, params: dict[str, object], key: str
) -> Transcript:
    progress = Progress(f"transcribe {clip.id}", 0, "s")
    try:
        raw = engine.transcribe(wav, prompt, None, progress)
    finally:
        progress.close()
    words = [Word(word_id(clip.id, w.i), w.i, w.text, w.s_ms, w.e_ms, w.p) for w in raw.words]
    return Transcript(
        clip_id=clip.id,
        key=key,
        language=raw.language,
        language_p=raw.language_p,
        duration_ms=wav16_length_ms(wav),  # the wav16's own length, never the declared one
        words=words,
        segments=raw.segments,
        params=params,
        elapsed_s=raw.elapsed_s,
    )


def _document(transcript: Transcript, cached: bool) -> dict[str, Any]:
    seconds = transcript.duration_ms / 1000
    rtf = round(transcript.elapsed_s / seconds, 2) if seconds > 0 else None
    return {
        "id": transcript.clip_id,
        "cached": cached,
        "language": transcript.language,
        "language_p": transcript.language_p,
        "words": len(transcript.words),
        "rtf": rtf,
    }


def _say(out: Out, doc: dict[str, Any]) -> None:
    if doc["cached"]:
        out.line("INFO", f"{doc['id']}: ya estaba transcrito (caché)")
        return
    speed = "" if doc["rtf"] is None else f" - {doc['rtf']}x el tiempo real"
    text = f"{doc['id']}: {doc['words']} palabras - idioma {doc['language']} ({doc['language_p']})"
    out.line("OK", text + speed)
