"""Transcript cache (spec S1.3): `.kcut/transcripts/<key>.json` plus an `index.json` clip -> key.

The key hashes the wav16 and every parameter that can change the words, so the same audio with
the same settings is never transcribed twice, and any other setting gets its own file. Nothing
read back from `.kcut/` is trusted (spec 0.9): a file that does not validate counts as absent.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path

from kcut.audio.wavio import open_wav
from kcut.config.model import TranscribeSection
from kcut.errors import CheckFailed, InternalError, ProjectError
from kcut.ingest import workfiles
from kcut.ingest.inventory import Notice
from kcut.jsonio import MAX_INDEX_BYTES, read_json, write_json_atomic
from kcut.project import Project
from kcut.schema_util import SchemaError, obj
from kcut.transcribe.document import KEY, SCHEMA, from_document, to_document
from kcut.transcribe.model import Transcript

INDEX_NAME = "index.json"
MAX_INDEX_ENTRIES = 10_000  # clips an index may name; a bigger one is not an honest one
WAV16_RATE = 16000
_CLIP = re.compile(r"[a-z][0-9]{1,6}")
_HASH_BLOCK = 1 << 20


def engine_label() -> str:
    """`faster-whisper 1.2.1`, from the installed package."""
    try:
        return f"faster-whisper {metadata.version('faster-whisper')}"
    except metadata.PackageNotFoundError:
        return "faster-whisper unknown"


def build_params(cfg: TranscribeSection, prompt: str, engine: str) -> dict[str, object]:
    """Every setting that can change the words. `cpu_threads` is left out: it only changes speed."""
    return {
        "model": cfg.model,
        "compute_type": cfg.compute_type,
        "beam_size": cfg.beam_size,
        "language": None,
        "initial_prompt": prompt,
        "vad_filter": False,
        "condition_on_previous_text": False,
        "word_timestamps": True,
        "engine": engine,
    }


def cache_key(wav_sha256: str, params: Mapping[str, object]) -> str:
    """`sha256(wav16_sha256 + json.dumps(params, sort_keys=True))` as hex."""
    text = wav_sha256 + json.dumps(params, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """SHA-256 of a file, read in blocks."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while block := handle.read(_HASH_BLOCK):
                digest.update(block)
    except OSError as exc:
        raise ProjectError(f"no pude leer {path}: {exc}") from None
    return digest.hexdigest()


def wav16_length_ms(path: Path) -> int:
    """Length of a wav16 from its samples (`frames * 1000 // 16000`), not from the inventory.

    The inventory keeps the duration the container declared, and a container can lie (spec 001.7,
    point 10). The wav must be mono, 16-bit, 16 kHz, or this is a ProjectError, and the data its
    header declares must fit in the file (spec 001.14, point 4).
    """
    with open_wav(path, "wav16") as wav:
        shape = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
        frames = wav.getnframes()
    if shape != (1, 2, WAV16_RATE):
        raise ProjectError(
            f"{path}: se esperaba un wav mono de 16 bits a 16 kHz; corre kcut ingest"
        )
    return frames * 1000 // WAV16_RATE


def transcript_path(project: Project, key: str) -> Path:
    return project.layout.transcripts / f"{key}.json"


def save_transcript(
    project: Project,
    transcript: Transcript,
    wav_sha256: str,
    index: dict[str, str] | None = None,
) -> None:
    """Write `<key>.json` and point the index at it (both checked to stay inside `.kcut/`).

    `index` is the dict the command read once with `read_index`; it is updated in place.

    The document is read back through `from_document` before it is written: what the engine
    produces must always be readable (spec 001.12, point 6), so a failure here is a bug of kcut.
    """
    document = to_document(transcript, wav_sha256)
    try:
        from_document(
            document, transcript.clip_id, transcript.key, wav_sha256, transcript.duration_ms
        )
    except SchemaError as exc:
        raise InternalError(
            f"la transcripción de {transcript.clip_id} no se puede volver a leer ({exc.path}); "
            "es un error de kcut, no se guardó"
        ) from None
    path = transcript_path(project, transcript.key)
    workfiles._assert_in_cache(project, path)
    write_json_atomic(path, document)
    point_index(project, transcript.clip_id, transcript.key, index)


def point_index(
    project: Project, clip_id: str, key: str, index: dict[str, str] | None = None
) -> None:
    """Make the index say `key` is the transcript of `clip_id` (no write if it already does).

    A command reads the index once and passes it here, so a run over many clips does not read the
    file once per clip (spec 001.14, point 6). Without `index` the file is read.
    """
    current = index if index is not None else read_index(project, [])
    if current.get(clip_id) == key:
        return
    current[clip_id] = key
    index_path = project.layout.transcripts / INDEX_NAME
    workfiles._assert_in_cache(project, index_path)
    write_json_atomic(index_path, dict(sorted(current.items())))


def read_index(project: Project, notices: list[Notice]) -> dict[str, str]:
    """The clip -> key index; absent or invalid means empty (an invalid one is reported).

    Read it once per command. It weighs at most 1 MB and names at most 10 000 clips: a bigger one
    is ignored with the same fixed notice as any invalid index.
    """
    path = project.layout.transcripts / INDEX_NAME
    if not path.is_file():
        return {}
    try:
        data = obj(read_json(path, MAX_INDEX_BYTES), "")
        if len(data) > MAX_INDEX_ENTRIES:
            raise SchemaError("", "tiene demasiadas entradas")
        for clip_id, key in data.items():
            if _CLIP.fullmatch(clip_id) is None or not isinstance(key, str):
                raise SchemaError(clip_id, "no es una entrada válida (id de clip -> clave)")
            if KEY.fullmatch(key) is None:
                raise SchemaError(clip_id, "la clave debe ser un sha256 en hexadecimal")
    except ProjectError:
        notices.append(Notice("cache_rebuilt", f"{path.name}: el índice era inválido y se ignora"))
        return {}
    return {clip_id: str(key) for clip_id, key in data.items()}


def load_transcript(
    project: Project,
    clip_id: str,
    notices: list[Notice] | None = None,
    wav_ms: int | None = None,
    index: Mapping[str, str] | None = None,
    same_audio_as: str | None = None,
) -> Transcript | None:
    """The cached transcript of a clip through the index, or None if there is none or it does
    not validate. With `wav_ms`, the length of the clip's wav16, it must fit that audio too.

    `index` is the one the command read (without it the file is read). With `same_audio_as`, the
    sha256 of the clip's wav16, a transcript made from another audio is `CheckFailed`, and that is
    checked first: a changed wav16 is not a transcript that merely "does not fit".
    """
    found = notices if notices is not None else []
    key = (index if index is not None else read_index(project, found)).get(clip_id)
    if key is None:
        return None
    return _read(project, clip_id, key, found, wav_ms=wav_ms, same_audio_as=same_audio_as)


def load_matching(
    project: Project,
    clip_id: str,
    key: str,
    wav_sha256: str,
    params: Mapping[str, object],
    notices: list[Notice],
    wav_ms: int | None = None,
) -> Transcript | None:
    """The cached transcript for exactly this audio and these parameters, or None.

    The file must also say it was made from this wav16 and with these parameters: a file renamed
    to the right key is not enough. With `wav_ms`, its words must fit the audio.
    """
    path = transcript_path(project, key)
    if not path.is_file():
        return None
    transcript = _read(project, clip_id, key, notices, wav_sha256=wav_sha256, wav_ms=wav_ms)
    if transcript is None:
        return None
    if transcript.params != dict(params):
        notices.append(_invalid(path))
        return None
    return transcript


def _read(
    project: Project,
    clip_id: str,
    key: str,
    notices: list[Notice],
    wav_sha256: str | None = None,
    wav_ms: int | None = None,
    same_audio_as: str | None = None,
) -> Transcript | None:
    path = transcript_path(project, key)
    try:
        data = read_json(path)
        if same_audio_as is not None and isinstance(data, dict):
            made_from = data.get("wav_sha256")
            if isinstance(made_from, str) and made_from != same_audio_as:
                raise CheckFailed(
                    f"la transcripción de {clip_id} es de otro audio; corre kcut transcribe"
                )
        return from_document(data, clip_id, key, wav_sha256, wav_ms)
    except ProjectError:
        notices.append(_invalid(path))
        return None


def _invalid(path: Path) -> Notice:
    """The warning for a transcript that cannot be used: a fixed text, never the data."""
    return Notice(
        "transcript_invalid", f"{path.name}: la transcripción no es válida para su audio; se ignora"
    )


__all__ = [
    "INDEX_NAME",
    "SCHEMA",
    "WAV16_RATE",
    "build_params",
    "cache_key",
    "engine_label",
    "file_sha256",
    "from_document",
    "load_matching",
    "load_transcript",
    "point_index",
    "read_index",
    "save_transcript",
    "to_document",
    "transcript_path",
    "wav16_length_ms",
]
