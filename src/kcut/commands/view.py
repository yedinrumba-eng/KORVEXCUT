"""kcut view: the level, the silences and the words of a stretch of a clip, as one picture.

Claude looks at it before it decides where to cut (lesson 8: Whisper's timestamps lie, the
energy does not). Times are of the source clock (spec 0.6). Words are the corrected ones and,
with `privacy.mask_pii`, masked (001.15, T2); with `--filmstrip N`, N frames of the proxy go on top.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from kcut.analysis.energy import Run, rms_db, silence_runs
from kcut.audio.wavio import read_wav_range
from kcut.config.model import AnalysisSection
from kcut.console import Out
from kcut.errors import ProjectError, UsageError
from kcut.ff.reader import PROXY_MISMATCH, grab, proxy_frame_count, proxy_index
from kcut.ingest import workfiles
from kcut.ingest.inventory import Clip, Inventory, Notice
from kcut.jsonio import write_bytes_atomic
from kcut.pack.assemble import HOP_MS, cover
from kcut.pack.pii import UNMASKED, mask_pii
from kcut.paths import resolve_in_project, to_rel
from kcut.project import Project, assert_writable, load_inventory, open_project, under_kcut
from kcut.schema_util import describe_value
from kcut.timebase import ms_to_f_ceil
from kcut.timeparse import parse_time
from kcut.transcribe.cache import WAV16_RATE, wav16_length_ms
from kcut.transcribe.document import MAX_WORD_MS
from kcut.transcribe.loaded import load_corrected, wav16_or_none
from kcut.transcribe.model import Word
from kcut.viz.timeline import MAX_BOXES, render_timeline, window_silences, window_words

NAME = "view"
HELP_ES = "Dibuja la onda, los silencios y las palabras de un tramo de un clip"
MAX_FILMSTRIP = 12
MAX_WINDOW_S = 60
NO_TRANSCRIPT = "sin transcripcion"
WORDS_CAPPED = f"hay más de {MAX_BOXES} palabras en la ventana; se dibujan las primeras {MAX_BOXES}"
_HOLE = np.array((46, 40, 40), dtype=np.uint8)  # (40, 40, 46) in BGR: a frame that is not there
_BLOCK = WAV16_RATE * HOP_MS // 1000  # samples in a block of 10 ms: where `pack` starts counting

Warnings = list[dict[str, str]]
Proxy = tuple[Path, tuple[int, int]]  # the file and its size (w, h)


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)
    sub.add_argument("clip", help="id del clip (a1, s1...)")
    sub.add_argument("start", help="inicio: frames (90), segundos (3s, 2.5s) o mm:ss (1:02)")
    sub.add_argument("end", help="fin, con el mismo formato (hasta 60 s después del inicio)")
    sub.add_argument(
        "--filmstrip",
        type=int,
        default=0,
        metavar="N",
        help=f"pone N frames del proxy arriba (0 a {MAX_FILMSTRIP}, por defecto 0)",
    )
    sub.add_argument(
        "--out", metavar="PNG", default=None, help="archivo de salida, relativo al proyecto (.png)"
    )
    sub.add_argument("--force", action="store_true", help="pisa el archivo de --out si ya existe")
    return sub


def run(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    log = getattr(args, "log", None)
    fps = project.config.output.fps
    start_f, end_f = parse_time(args.start, fps), parse_time(args.end, fps)
    _check_window(start_f, end_f, fps)
    if not 0 <= args.filmstrip <= MAX_FILMSTRIP:
        raise UsageError(f"--filmstrip va de 0 a {MAX_FILMSTRIP} (vino {args.filmstrip})")
    if args.out is not None and not str(args.out).lower().endswith(".png"):
        raise UsageError("--out tiene que ser un archivo .png")
    inventory = load_inventory(project, log)
    clip = inventory.by_id(args.clip)
    if clip is None:
        raise UsageError(f"no existe el clip {describe_value(args.clip)} en el inventario")
    wav = _wav16(project, clip, end_f, fps)
    proxy = proxy_of(project, clip) if args.filmstrip else None
    target = _target(project, clip, start_f, end_f, args.out, args.force)
    cfg = project.config.analysis
    s0, s1 = start_f * WAV16_RATE // fps, end_f * WAV16_RATE // fps
    window, _ = read_wav_range(wav, s0, s1 - s0)
    silences = _silences(wav, s0, s1, cfg)
    notices: list[Notice] = []
    words, notice, warnings = _words(project, inventory, clip, notices, log)
    shown = window_words(words, start_f, end_f, fps, cfg.low_prob, silences)
    if len(shown) > MAX_BOXES:  # the first ones are drawn, and the picture says so
        warnings.append({"code": "words_capped", "message_es": WORDS_CAPPED})
        shown = shown[:MAX_BOXES]
    strip = _filmstrip(clip, proxy, args.filmstrip, start_f, end_f, fps, log) if proxy else None
    db = rms_db(window, WAV16_RATE, HOP_MS)
    image = render_timeline(db, silences, shown, start_f, end_f, fps, cfg, strip, notice)
    write_bytes_atomic(target, png_bytes(image), replace=args.force or under_kcut(project, target))
    rel = to_rel(project.root, target)
    for warning in warnings:
        out.warn(f"{warning['code']}: {warning['message_es']}")
    for item in notices:
        out.warn(f"{item.code}: {item.detail}")
    out.line("OK", rel)
    bands = len(window_silences(silences, start_f, end_f, fps))
    out.result(
        {
            "ok": True,
            "png": rel,
            "words": len(shown),
            "silences": bands,
            "notice": notice,
            "warnings": warnings,
        }
    )
    return 0


def png_bytes(image: Image.Image) -> bytes:
    """The picture as PNG, encoded in memory (the file is written with `write_bytes_atomic`)."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def proxy_of(project: Project, clip: Clip) -> Proxy:
    """The clip's proxy file and its size `(w, h)`; a clip without video is a UsageError, a proxy
    that is not there (or not in the inventory) a ProjectError that says to run `kcut ingest`."""
    if clip.video is None:
        raise UsageError(f"{clip.id} no tiene video")
    work = clip.work
    if work is None or work.proxy is None or work.proxy_w is None or work.proxy_h is None:
        raise ProjectError(f"falta el proxy de {clip.id}; corre kcut ingest")
    if (work.proxy_w, work.proxy_h) != workfiles.proxy_size(clip.video):
        raise ProjectError(PROXY_MISMATCH)  # the inventory is not trusted (001.20, point 4)
    path = resolve_in_project(project.root, work.proxy)
    if not path.is_file():
        raise ProjectError(f"falta el proxy de {clip.id}; corre kcut ingest")
    return path, (work.proxy_w, work.proxy_h)


def _check_window(start_f: int, end_f: int, fps: int) -> None:
    if end_f <= start_f:
        raise UsageError("el fin tiene que ir después del inicio")
    if end_f - start_f > MAX_WINDOW_S * fps:
        raise UsageError(f"el tramo pasa de {MAX_WINDOW_S} s; pide uno más corto")


def _wav16(project: Project, clip: Clip, end_f: int, fps: int) -> Path:
    """The clip's wav16, after checking it has audio and that the window fits in it."""
    if clip.audio is None:
        raise UsageError(f"{clip.id} no tiene audio; usa kcut frames")
    wav = wav16_or_none(project, clip)
    if wav is None:
        raise ProjectError(f"falta el wav16 de {clip.id}; corre kcut ingest")
    if end_f > ms_to_f_ceil(wav16_length_ms(wav), fps):  # the audio's own length (001.7)
        raise UsageError(f"el fin pasa del final del audio de {clip.id}")
    return wav


def _target(
    project: Project, clip: Clip, start_f: int, end_f: int, out: str | None, force: bool
) -> Path:
    """Where the PNG goes: `--out` (checked by `assert_writable`, which does not replace a file
    that is there unless `--force`) or `.kcut/view/`."""
    if out is not None:
        return assert_writable(project, out, replace=force)
    path = project.layout.view / f"{clip.id}_{start_f}-{end_f}.png"
    return workfiles._assert_in_cache(project, path)


def _silences(wav: Path, s0: int, s1: int, cfg: AnalysisSection) -> list[Run]:
    """The silences around the window `[s0, s1)` (samples), in ms of the clip.

    Measured over the window plus `MAX_WORD_MS` on each side (bounded by the wav16), starting on
    a block of 10 ms like `pack` does, so a silence is cut where `pack` cuts it.
    """
    pad = MAX_WORD_MS * WAV16_RATE // 1000
    r0 = (max(0, s0 - pad) // _BLOCK) * _BLOCK
    region, _ = read_wav_range(wav, r0, s1 + pad - r0)
    runs = silence_runs(
        rms_db(region, WAV16_RATE, HOP_MS), HOP_MS, cfg.silence_db, cfg.min_silence_ms
    )
    offset = r0 * 1000 // WAV16_RATE
    return [(a + offset, b + offset) for a, b in runs]


def _words(
    project: Project, inventory: Inventory, clip: Clip, notices: list[Notice], log: Path | None
) -> tuple[list[Word], str | None, Warnings]:
    """The corrected words of the whole clip, the notice (a clip with no transcript) and the
    warnings. With `privacy.mask_pii` the words are masked as a whole, before the window is cut
    out: a number is PII only in its context. With it off they are raw, with a warning."""
    loaded = load_corrected(project, inventory, notices, log, [clip.id])
    if clip.id not in loaded.transcripts:
        return [], NO_TRANSCRIPT, []
    cfg = project.config
    words = loaded.words[clip.id]
    if not cfg.privacy.mask_pii:
        return words, None, [{"code": "pii_unmasked", "message_es": UNMASKED}]
    shown = mask_pii(words, cfg.transcribe.fillers)[0]
    # a word under a number another camera masked is `*` too, as `pack` does (001.19, point 2)
    return cover(shown, loaded.covered.get(clip.id, ()))[0], None, []


def _filmstrip(
    clip: Clip, proxy: Proxy, count: int, start_f: int, end_f: int, fps: int, log: Path | None
) -> list[NDArray[np.uint8]]:
    """`count` frames of the proxy, the middle of each of `count` equal parts of the window; one
    that is not in the clip is a gray hole: the proxy holds `[0, min(frames - vs_f, the frames
    the proxy really has))`, and the container may be longer than the video (001.20, point 3)."""
    path, (width, height) = proxy
    if clip.frames is None:
        raise ProjectError(f"falta el número de frames de {clip.id}; corre kcut ingest")
    limit = min(
        clip.frames + proxy_index(clip, 0, fps), proxy_frame_count(path, (width, height), log)
    )
    strip: list[NDArray[np.uint8]] = []
    for k in range(count):
        index = proxy_index(clip, start_f + ((2 * k + 1) * (end_f - start_f)) // (2 * count), fps)
        if 0 <= index < limit:
            strip.append(grab(path, index, fps, (width, height), log=log))
        else:
            strip.append(np.full((height, width, 3), _HOLE, dtype=np.uint8))
    return strip
