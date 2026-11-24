"""`kcut qa`, in order (spec S1.9a): probe, loudness, black and freeze, the transcript, the sheet.

`run_qa` audits `salida/vN.mp4` against the EDL it was built from and writes `qa/vN/report.json` and
`qa/vN/contact.jpg`. Both targets pass through `assert_writable` (T4) before anything is measured.
The sheet is not written, and the report says `contact_sheet: null` and `contact_skipped`, if a
frame with graphics cannot be made (`qa/contact_gfx.py`, 001.40): the report comes out all the same.
Only `salida/vN.mp4` is accepted (T3): the measurement filters print metadata at the `info` level,
so they run on what kcut made and never on a file of the user. The EDL is `--edl`, or
`qa/vN/inputs/edl-vN.json` (what `build` snapshotted) if it exists, or `edit/edl-vN.json`.

The transcript check compares ALL the words the cut keeps with what Whisper hears in the render.
It is skipped, with its reason, if the cut keeps no words, if the render is silent (I under -50
LUFS), or if the model of Whisper is not on the machine (nothing is downloaded).
"""

import os
import re
import time
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath

from kcut.audio.loudnorm import EburMeasure
from kcut.console import Out, Progress
from kcut.edl.check import check_edl_file
from kcut.edl.files import find_edl
from kcut.edl.kept import kept_words
from kcut.edl.model import Edl, VoiceClip
from kcut.edl.refuse import refuse_edl
from kcut.errors import CheckFailed, ProjectError, UsageError
from kcut.ingest.inventory import Inventory, Notice
from kcut.pack.pii import mask_pii
from kcut.paths import resolve_in_project, same_path
from kcut.project import Project, assert_writable, load_inventory
from kcut.qa.contact_gfx import contact_sheet
from kcut.qa.detect import run_detect
from kcut.qa.ear import hear
from kcut.qa.loudness import check_loudness, measure_video
from kcut.qa.outputs import write_report, write_sheet
from kcut.qa.report import Check, QaReport, skipped
from kcut.qa.streams import Facts, checks_of, facts_of, measure_timeout_s, run_probe
from kcut.qa.transcript_diff import diff_transcript, transcript_check
from kcut.timebase import fmt_tc
from kcut.transcribe import cache
from kcut.transcribe.model import Word

VIDEO_NAME = re.compile(r"salida/v([1-9][0-9]{0,3})\.mp4")
EAR_MARGIN_S = 2.0  # audio the ear takes beyond the length of the EDL (001.41)
SILENT_LUFS = -50.0  # a render under this has nothing to listen to
STEPS = 5  # what `progress` counts: probe, loudness, detect, transcript, contact
NO_WORDS_ES = "el EDL no conserva ninguna palabra con transcripción: no hay qué comparar"
SILENT_ES = "el audio del render está en silencio (menos de -50 LUFS): no hay qué oír"
NO_MODEL_ES = (
    "el modelo de Whisper no está en esta máquina; kcut transcribe --allow-download lo baja"
)
NO_AUDIO_ES = "el video no tiene audio"
EDL_VERSION_ES = (
    "el EDL es de la versión {edl} y el video de la {video}; usa el EDL de la misma versión"
)


def run_qa(
    project: Project,
    video_rel: str,
    edl_rel: str | None,
    progress: Progress,
    *,
    out: Out,
    log: Path | None = None,
) -> QaReport:
    """Audit `video_rel` (which must be `salida/vN.mp4`) and write its report and contact sheet."""
    version = _version_of(video_rel)
    video = _video_path(project, video_rel)
    report_rel, contact_rel = f"qa/v{version}/report.json", f"qa/v{version}/contact.jpg"
    assert_writable(project, report_rel)  # both before anything is measured, and again right
    assert_writable(project, contact_rel)  # before each is written (`qa/outputs.py`, 001.41)
    inventory = load_inventory(project, log)
    rel = _edl_rel(project, edl_rel, version)
    checked = check_edl_file(project, inventory, rel)  # 001.43: as render, mix and graphics do,
    errors = [issue for issue in checked.issues if issue.level == "error"]  # before any tool runs
    if errors or checked.edl is None:
        refuse_edl(out, rel, errors)
    edl = checked.edl
    notices: list[Notice] = []
    timings: dict[str, float] = {}
    started = time.monotonic()

    limit = measure_timeout_s(edl.frames / edl.fps)
    facts = facts_of(run_probe(video, log, limit))
    if facts.video is None:
        raise CheckFailed(f"{video_rel} no tiene video: no hay qué auditar")
    checks = checks_of(facts, edl, project.config.qa)
    timings["probe"] = time.monotonic() - started
    progress.update(1)

    mark = time.monotonic()
    measure = measure_video(video, log, limit) if facts.audio is not None else None
    checks.append(_loudness(measure, project))
    timings["loudness"] = time.monotonic() - mark
    progress.update(2)

    mark = time.monotonic()
    frames = facts.video.frames or edl.frames
    checks.append(run_detect("black", video, edl, frames, log, limit))
    checks.append(run_detect("freeze", video, edl, frames, log, limit))
    timings["detect"] = time.monotonic() - mark
    progress.update(3)

    mark = time.monotonic()
    checks.append(_transcript(project, inventory, edl, video, measure, notices, log))
    timings["transcript"] = time.monotonic() - mark
    progress.update(4)

    mark = time.monotonic()
    size = _size(facts, edl)
    sheet = contact_sheet(project, edl, version, inventory, video, frames, size, notices, log)
    write_sheet(project, contact_rel, sheet)  # None (`contact_skipped`): the old sheet goes
    timings["contact"] = time.monotonic() - mark
    progress.update(5)

    report = QaReport(
        video=video_rel,
        edl=rel,
        generated=datetime.now().isoformat(timespec="seconds"),
        checks=tuple(checks),
        file_mb=round(video.stat().st_size / 2**20, 1),
        duration_display=fmt_tc(frames, edl.fps),
        contact_sheet=None if sheet is None else contact_rel,
        timings_s={name: round(seconds, 1) for name, seconds in timings.items()},
        warnings=_warnings(notices),
    )
    write_report(project, report_rel, report)
    return report


def _version_of(video_rel: str) -> int:
    """N of `salida/vN.mp4`; anything else is a UsageError (T3), whose text does not repeat it."""
    found = VIDEO_NAME.fullmatch(video_rel)
    if found is None:
        raise UsageError("kcut qa solo audita salida/vN.mp4 (N de 1 a 9999)")
    return int(found.group(1))


def _video_path(project: Project, video_rel: str) -> Path:
    """The file, if it is there and is a plain file of the folder `salida/`: a link or a hard link
    could lead to a file of the user, and the filters would print its metadata (T3).

    The links are looked at BEFORE the path is resolved (001.41, point 1): `resolve()` turns a
    symlink or a junction into its target, and a `salida/` that is a junction to `crudo/` gives a
    path that is a plain file. So `salida/` and the file are not links, the file has one name, and
    the resolved path is `<resolved root>/salida/<name>` and nothing else."""
    path = project.root / video_rel
    if not os.path.lexists(path):
        raise ProjectError(f"no existe {video_rel}; corre kcut build")
    linked = f"{video_rel} es un enlace; kcut qa no lo mide"
    for step in (project.root / "salida", path):
        if os.path.islink(step) or os.path.isjunction(step):
            raise ProjectError(linked)
    if os.lstat(path).st_nlink != 1:
        raise ProjectError(linked)
    target = resolve_in_project(project.root, video_rel)
    if not same_path(target, project.root.resolve() / "salida" / PurePosixPath(video_rel).name):
        raise ProjectError(linked)
    if not target.is_file():
        raise ProjectError(f"{video_rel} no es un archivo")
    return target


def _edl_rel(project: Project, explicit: str | None, version: int) -> str:
    """`--edl`, or the snapshot of the build if there is one, or `edit/edl-vN.json`. An `--edl` of
    another version than the video is a UsageError (001.41, point 3): it is another cut, and the
    report would mix the two."""
    if explicit is not None:
        rel, found = find_edl(project, explicit)
        if found != version:
            raise UsageError(EDL_VERSION_ES.format(edl=found, video=version))
        return rel
    snapshot = f"qa/v{version}/inputs/edl-v{version}.json"
    if os.path.lexists(resolve_in_project(project.root, snapshot)):
        return snapshot
    return find_edl(project, f"edit/edl-v{version}.json")[0]


def _loudness(measure: EburMeasure | None, project: Project) -> Check:
    if measure is None:
        return skipped("loudness", NO_AUDIO_ES)
    return check_loudness(measure, project.config.qa, project.config.audio.target_lufs)


def _size(facts: Facts, edl: Edl) -> tuple[int, int]:
    """The `(width, height)` of the video as the file says it, or the one of the EDL."""
    video = facts.video
    if video is not None and video.width and video.height:
        return video.width, video.height
    return edl.out_w, edl.out_h


def _transcript(
    project: Project,
    inventory: Inventory,
    edl: Edl,
    video: Path,
    measure: EburMeasure | None,
    notices: list[Notice],
    log: Path | None,
) -> Check:
    """The check `transcript`, or `skipped` with its reason (see the module)."""
    kept = kept_words(project, edl, inventory, notices=notices, log=log)
    if not kept.words:
        return skipped("transcript", NO_WORDS_ES)
    if measure is None:
        return skipped("transcript", NO_AUDIO_ES)
    if measure.I is None or measure.I < SILENT_LUFS:
        return skipped("transcript", SILENT_ES)
    language = _language(project, edl)
    if language is None:
        return skipped("transcript", NO_WORDS_ES)
    limit_s = edl.frames / edl.fps + EAR_MARGIN_S  # 001.41: the audio of the cut, not the file's
    heard = hear(project, video, language, log=log, notices=notices, limit_s=limit_s)
    if heard is None:
        return skipped("transcript", NO_MODEL_ES)
    diff = diff_transcript(kept.words, kept.shown, heard.words, _heard_shown(project, heard.words))
    return transcript_check(diff, project.config.qa.min_transcript_match, heard.language, edl.fps)


def _heard_shown(project: Project, heard: Sequence[Word]) -> list[str]:
    """What Claude may read of the heard words (T2): `mask_pii` over the WHOLE list, in order,
    unless `privacy.mask_pii` is off."""
    if not project.config.privacy.mask_pii:
        return [w.text for w in heard]
    return [w.text for w in mask_pii(heard, project.config.transcribe.fillers)[0]]


def _language(project: Project, edl: Edl) -> str | None:
    """The language most voice clips of the EDL are in (ties go to the first in the alphabet), from
    the cached transcript of each source; `None` if no source has one."""
    index = cache.read_index(project, [])  # the notices of an invalid index come from kept_words
    found: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for clip in edl.clips:
        if not isinstance(clip, VoiceClip):
            continue
        if clip.src not in found:
            transcript = cache.load_transcript(project, clip.src, [], None, index)
            if transcript is None:
                continue
            found[clip.src] = transcript.language
        counts[found[clip.src]] += 1
    if not counts:
        return None
    return min(counts, key=lambda language: (-counts[language], language))


def _warnings(notices: list[Notice]) -> tuple[dict[str, str], ...]:
    """The notices of the run as the report lists them, without repeats."""
    unique = dict.fromkeys((n.code, n.detail) for n in notices)
    return tuple({"code": code, "message_es": detail} for code, detail in unique)
