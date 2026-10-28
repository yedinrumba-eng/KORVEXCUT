"""Loudness: `loudnorm` in two passes and the `ebur128` measurement (spec S1.8b, 001.15 T3).

Everything here is an `ffmpeg` that reads raw float32 (DS4: `.f32`, mono, 48 kHz) and none writes
a path in a filter graph (spec 0.8). The two filters of measurement, `loudnorm` with
`print_format=json` and `ebur128`, print their result at the `info` level, so they go **without**
`-loglevel error` and with `-hide_banner -nostdin -nostats`; the raw stderr is read only by the
parser, and nothing of it is shown. They run on intermediates of `.kcut/` or on `salida/vN.mp4`,
never on a file of `crudo/` or of `recursos/`. The second pass of `loudnorm` is not a measurement
and keeps `-loglevel error`.
"""

import json
import math
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from kcut import proc
from kcut.errors import ProjectError, ToolError
from kcut.ff.args import fnum
from kcut.ingest.cache_guard import assert_in_cache, assert_own_folder
from kcut.ingest.inventory import Notice
from kcut.project import Project
from kcut.render.lock import atomic_replace, discard_partial, prepare_partial

LRA = 11.0  # the range of loudness that `loudnorm` is asked for
SILENCE_LUFS = -60.0  # a measured input under this is silence: it is not normalized
SAMPLE_RATE = 48000
_F32_INPUT = ["-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", "1"]
_JSON_BLOCK = re.compile(r"\{[^{}]*\}")
_SUMMARY = "Summary:"
_I_LINE = re.compile(r"^\s*I:\s+(\S+)\s+LUFS", re.MULTILINE)
_LRA_LINE = re.compile(r"^\s*LRA:\s+(\S+)\s+LU\b", re.MULTILINE)
_PEAK_LINE = re.compile(r"^\s*Peak:\s+(\S+)\s+dBFS", re.MULTILINE)
_TIMEOUT_FLOOR_S = 60.0
_TIMEOUT_PER_AUDIO_S = 10.0  # seconds allowed for each second of audio, besides the floor


@dataclass(frozen=True)
class LoudnormMeasure:
    """What the first pass of `loudnorm` measured, as the second pass wants it back."""

    input_i: float
    input_tp: float
    input_lra: float
    input_thresh: float
    target_offset: float


@dataclass(frozen=True)
class EburMeasure:
    """The `Summary` of `ebur128`: integrated loudness (LUFS), true peak (dBFS) and the range of
    loudness (LU). A value that the filter gives as `-inf` or `nan` is `None`."""

    I: float | None  # noqa: E741 (the name of the measure)
    TP: float | None
    LRA: float | None


def pass1_args(ffmpeg: Path, src_f32: Path, I: float, TP: float, LRA: float) -> list[str]:  # noqa: E741
    """First pass: measure `src_f32` against the targets `I` (LUFS), `TP` (dBTP) and `LRA` (LU)."""
    spec = f"loudnorm=I={fnum(I)}:TP={fnum(TP)}:LRA={fnum(LRA)}:print_format=json"
    return [
        str(ffmpeg), "-hide_banner", "-nostdin", "-nostats",
        *_F32_INPUT, "-i", str(src_f32), "-af", spec, "-f", "null", "-",
    ]  # fmt: skip


def pass2_args(
    ffmpeg: Path,
    src: Path,
    dst: Path,
    I: float,  # noqa: E741
    TP: float,
    LRA: float,
    m: LoudnormMeasure,
) -> list[str]:
    """Second pass: `src` to raw float32 at `dst`, in linear mode with what the first measured.
    `dst` must not exist (there is no `-y`): the caller writes a partial file and moves it."""
    spec = (
        f"loudnorm=I={fnum(I)}:TP={fnum(TP)}:LRA={fnum(LRA)}"
        f":measured_I={fnum(m.input_i)}:measured_TP={fnum(m.input_tp)}"
        f":measured_LRA={fnum(m.input_lra)}:measured_thresh={fnum(m.input_thresh)}"
        f":offset={fnum(m.target_offset)}:linear=true:print_format=summary,aresample={SAMPLE_RATE}"
    )
    return [
        str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error",
        *_F32_INPUT, "-i", str(src), "-af", spec, "-f", "f32le",
        "-ar", str(SAMPLE_RATE), "-ac", "1", str(dst),
    ]  # fmt: skip


def parse_pass1(stderr: str) -> LoudnormMeasure | None:
    """The measure of the last `{...}` block of the stderr of the first pass. `None` is silence
    (`input_i` is `-inf`, `nan` or under -60 LUFS): it is not normalized, and the caller says so.
    No block, or one that cannot be read, is a ToolError (it does not repeat the stderr)."""
    blocks = _JSON_BLOCK.findall(stderr)
    if not blocks:
        raise ToolError("loudnorm no dio medición")
    try:
        data = json.loads(blocks[-1])
        loudness = _number(data["input_i"])
        if not math.isfinite(loudness) or loudness < SILENCE_LUFS:
            return None
        return LoudnormMeasure(
            loudness,
            _number(data["input_tp"]),
            _number(data["input_lra"]),
            _number(data["input_thresh"]),
            _number(data["target_offset"]),
        )
    except (ValueError, KeyError, TypeError):
        raise ToolError("loudnorm dio una medición que no se puede leer") from None


def audio_timeout_s(seconds: float) -> float:
    """What an `ffmpeg` over `seconds` of audio is given to finish (001.37, point 3): 10 s for each
    second of audio, and never less than 60 s. A hung `ffmpeg` is killed instead of holding the lock
    of the output for ever."""
    return _TIMEOUT_PER_AUDIO_S * seconds + _TIMEOUT_FLOOR_S


def _number(value: object) -> float:
    """A measure as `loudnorm` prints it (a string like `"-23.54"`, `"-inf"`)."""
    if not isinstance(value, str | int | float) or isinstance(value, bool):
        raise TypeError("medición que no es un número")
    return float(value)


def ebur128_args(ffmpeg: Path, inputs: list[str]) -> list[str]:
    """`ebur128` with the true peak over the first audio stream of `inputs` (`-i` and what goes
    before it). `framelog=quiet`: without it it prints a line every 100 ms; the `Summary` comes
    out all the same."""
    return [
        str(ffmpeg), "-hide_banner", "-nostdin", "-nostats", *inputs,
        "-map", "0:a:0", "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-",
    ]  # fmt: skip


def parse_ebur128(stderr: str) -> EburMeasure:
    """`I`, `TP` and `LRA` from the last `Summary:` block. A value of `-inf` or `nan`, or one
    that is not there, is `None`. No `Summary:` at all is a ToolError."""
    if _SUMMARY not in stderr:
        raise ToolError("ebur128 no dio resumen")
    block = stderr.rsplit(_SUMMARY, 1)[1]
    return EburMeasure(_first(_I_LINE, block), _first(_PEAK_LINE, block), _first(_LRA_LINE, block))


def _first(pattern: re.Pattern[str], block: str) -> float | None:
    found = pattern.search(block)
    if found is None:
        return None
    try:
        value = float(found.group(1))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def normalize(
    project: Project,
    src: Path,
    dst: Path,
    I: float,  # noqa: E741
    TP: float,
    *,
    log: Path | None = None,
    notices: list[Notice] | None = None,
    label: str = "el audio",
) -> None:
    """`src` normalized to `I` LUFS and `TP` dBTP in two passes, to `dst` (raw float32). Silent
    audio is copied as it is and `notices` gets `loudnorm_silence` naming `label`: there is
    nothing to bring to a level. The result goes to a partial file and is moved over `dst`."""
    ffmpeg = proc.tool_path("ffmpeg")
    timeout = audio_timeout_s(src.stat().st_size / 4 / SAMPLE_RATE)
    first = proc.run(
        pass1_args(ffmpeg, src, I, TP, LRA), log=log, timeout_s=timeout, capture_stderr=True
    )
    measure = parse_pass1(first.stderr)
    partial = dst.with_name(f"{dst.name}.{os.getpid()}.partial")
    # 001.37, point 2: the folder is looked at again right before the write, after the first pass
    # (the folder of `dst` can be changed for a link while `ffmpeg` runs), as `render` does
    assert_own_folder(project, dst.parent)
    for path in (dst, partial):
        assert_in_cache(project, path)
    prepare_partial(partial)
    try:
        if measure is None:
            if notices is not None:
                text = f"{label} está en silencio: no se normaliza"
                notices.append(Notice("loudnorm_silence", text))
            try:
                shutil.copyfile(src, partial)
            except OSError as exc:
                raise ProjectError(f"no pude escribir {label}: {exc.strerror}") from None
        else:
            args = pass2_args(ffmpeg, src, partial, I, TP, LRA, measure)
            proc.run(args, log=log, timeout_s=timeout)
        atomic_replace(partial, dst)
    finally:
        discard_partial(partial)
