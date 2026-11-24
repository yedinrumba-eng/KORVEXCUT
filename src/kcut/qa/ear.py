"""The ear of `kcut qa`: what Whisper writes for the audio of the finished video (S1.9a, 001.15).

The audio of `salida/vN.mp4` goes to `.kcut/qa_ear/vN.partial.wav` and then to `vN.wav`; its sha256
and the parameters of the transcription (those of `kcut transcribe`, with the language forced to
the one of the clips that speak) make the key of `.kcut/qa_ear/<key>.json`, a transcript in the
format `kcut.transcript/1` under the clip id `qa`. The second time it is read, not made again. A
cache file that does not validate for this audio counts as absent: it is heard again, and the
notice `cache_rebuilt` says so. It is not in `.kcut/transcripts/`, whose ids are the ones of clips.

The model is the one on the machine: nothing is downloaded (`allow_download=False`). If it is not
there, `hear` gives `None` and the check is skipped. The words are raw (the diff masks what it
shows, T2) and are not in the `repr`: what was said can be a phone number.
"""

from dataclasses import dataclass, field
from pathlib import Path

from kcut import proc
from kcut.console import Progress
from kcut.errors import InternalError, MissingDependency, ProjectError
from kcut.ff.args import wav_args
from kcut.ingest.cache_guard import assert_in_cache, assert_own_folder
from kcut.ingest.inventory import Notice
from kcut.jsonio import read_json, write_json_atomic
from kcut.project import Project
from kcut.render.lock import atomic_replace, discard_partial, prepare_partial
from kcut.schema_util import SchemaError
from kcut.transcribe.cache import (
    build_params,
    cache_key,
    engine_label,
    file_sha256,
    wav16_length_ms,
)
from kcut.transcribe.document import from_document, to_document
from kcut.transcribe.engine import Engine, build_prompt
from kcut.transcribe.model import Transcript, Word, word_id

CLIP_ID = "qa"  # the id of the clip in the cache file: the render is not a clip of the project
EXTRACT_TIMEOUT_S = 600.0  # decoding the audio of a video is far faster than the real time
REBUILT_ES = "{name}: el oído guardado no era válido para este audio; se vuelve a oír"


@dataclass(frozen=True)
class Heard:
    """What was heard: its words (raw, `qa:w0000`...) and the language they were heard in."""

    words: list[Word] = field(repr=False)
    language: str


def hear(
    project: Project,
    video: Path,
    language: str,
    *,
    log: Path | None,
    notices: list[Notice] | None = None,
    limit_s: float | None = None,
) -> Heard | None:
    """The words in the audio of `video` (a `salida/vN.mp4`), heard in `language`. At most
    `limit_s` seconds of audio are taken (001.41, point 7): the declared length of the file is not
    trusted.

    `None` if the model of Whisper is not on this machine. A cache file that is not valid for the
    audio (`from_document` against the length of the wav, or other parameters) adds
    `cache_rebuilt` to `notices` and is made again."""
    cfg = project.config
    folder = assert_own_folder(project, project.layout.qa_ear)
    folder.mkdir(parents=True, exist_ok=True)
    wav = folder / f"{video.stem}.wav"
    _extract(project, video, folder / f"{video.stem}.partial.wav", wav, log, limit_s)
    sha = file_sha256(wav)
    length_ms = wav16_length_ms(wav)
    params = build_params(cfg.transcribe, build_prompt(cfg), engine_label())
    params["language"] = language
    key = cache_key(sha, params)
    path = folder / f"{key}.json"
    assert_in_cache(project, path)
    if path.is_file():
        found = _read(path, key, sha, length_ms, params)
        if found is not None:
            return Heard(found.words, found.language)
        if notices is not None:
            notices.append(Notice("cache_rebuilt", REBUILT_ES.format(name=path.name)))
    try:
        engine = Engine(cfg.transcribe, False)  # the model on disk: nothing is downloaded
    except MissingDependency:
        return None
    made = _listen(engine, wav, build_prompt(cfg), language, params, key, length_ms)
    document = to_document(made, sha)
    try:
        from_document(document, CLIP_ID, key, sha, length_ms)
    except SchemaError as exc:  # what the engine makes must always be readable: a bug of kcut
        raise InternalError(
            f"lo que oyó el oído de qa no se puede volver a leer ({exc.path}); "
            "es un error de kcut, no se guardó"
        ) from None
    assert_own_folder(project, folder)
    write_json_atomic(path, document)
    return Heard(made.words, made.language)


def _extract(
    project: Project, video: Path, partial: Path, wav: Path, log: Path | None, limit_s: float | None
) -> None:
    """The audio of `video` as a wav of 16 kHz, through a partial file. The folder is looked at
    again right before the move and the delete (001.38, point 2)."""

    def look() -> None:
        assert_own_folder(project, partial.parent)
        for target in (partial, wav):
            assert_in_cache(project, target)

    look()
    prepare_partial(partial)
    try:
        args = wav_args(proc.tool_path("ffmpeg"), video, partial, 16000, limit_s)
        proc.run(args, log=log, timeout_s=EXTRACT_TIMEOUT_S)
        look()
        atomic_replace(partial, wav)
    finally:
        discard_partial(partial, look)


def _read(
    path: Path, key: str, sha: str, length_ms: int, params: dict[str, object]
) -> Transcript | None:
    """The cached transcript if it is valid for this audio and these parameters, else `None`."""
    try:
        transcript = from_document(read_json(path), CLIP_ID, key, sha, length_ms)
    except ProjectError:  # not JSON, or it does not fit the schema (`SchemaError` is one)
        return None
    return transcript if transcript.params == params else None


def _listen(
    engine: Engine,
    wav: Path,
    prompt: str,
    language: str,
    params: dict[str, object],
    key: str,
    length_ms: int,
) -> Transcript:
    progress = Progress("oído de qa", 0, "s")
    try:
        raw = engine.transcribe(wav, prompt, language, progress)
    finally:
        progress.close()
    words = [Word(word_id(CLIP_ID, w.i), w.i, w.text, w.s_ms, w.e_ms, w.p) for w in raw.words]
    return Transcript(
        clip_id=CLIP_ID,
        key=key,
        language=raw.language,
        language_p=raw.language_p,
        duration_ms=length_ms,
        words=words,
        segments=raw.segments,
        params=params,
        elapsed_s=raw.elapsed_s,
    )
