"""The ear takes at most the length of the EDL plus 2 s of audio (spec S1.9a row 27; 001.41,
point 7).

The declared duration of a file is not trusted: a `salida/v1.mp4` with 300 s of audio and an EDL of
11.5 s would have been transcribed whole. `wav_args` has `limit_s` (`-t`); `hear` passes it on and
the `transcript` step of `kcut qa` gives it `edl.frames / edl.fps + 2`.
"""

import inspect
from pathlib import Path
from typing import Any

import pytest

from kcut.audio.loudnorm import EburMeasure
from kcut.edl.kept import KeptWords
from kcut.edl.words import KeptWord
from kcut.project import Project
from kcut.qa import ear
from kcut.qa import run as qa_run
from kcut.qa.ear import Heard, hear
from kcut.transcribe.model import Transcript, Word
from tests.unit.edl_fakes import inventory, parsed
from tests.unit.gfx_resolve_fakes import make_project
from tests.unit.qa_fakes import fake_extraction, install_ear


@pytest.fixture
def project(tmp_path: Path, fake_tools: None) -> Project:
    project = make_project(tmp_path)
    (project.root / "salida").mkdir()
    (project.root / "salida" / "v1.mp4").write_bytes(b"not a video: the extraction is a fake")
    return project


def test_qa_ear_limit_the_extraction_is_capped_with_dash_t(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = fake_extraction(monkeypatch)
    install_ear(monkeypatch, [("Hola", 200, 600)])
    hear(project, project.root / "salida" / "v1.mp4", "es", log=None, limit_s=13.5)
    (args,) = seen
    assert args[args.index("-t") + 1] == "13.5"


def test_qa_ear_limit_the_limit_is_required_there_is_no_way_to_ask_for_no_cap(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 001.47: this was "without a limit there is no cap" (`hear(..., log=None)` and `"-t" not in
    # args`). `limit_s` is mandatory now, so that call is a TypeError and is what is asserted. The
    # no-cap case still exists one level down, in `wav_args`, and `test_ff_args.py` keeps it
    # (`test_without_a_cap_there_is_no_t`: `"-t" not in wav_args(FFMPEG, SRC, DST, 16000)`).
    for function in (hear, ear._extract):
        parameter = inspect.signature(function).parameters["limit_s"]
        assert parameter.default is inspect.Parameter.empty
        assert parameter.annotation in (float, "float")
    seen = fake_extraction(monkeypatch)
    install_ear(monkeypatch, [("Hola", 200, 600)])
    with pytest.raises(TypeError, match="limit_s"):
        hear(project, project.root / "salida" / "v1.mp4", "es", log=None)  # type: ignore[call-arg]
    assert seen == []  # nothing was extracted


def test_qa_ear_limit_the_transcript_step_asks_for_the_length_of_the_edl_plus_2_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    words = [KeptWord("a1:w0000", "Hola", 1, 30, 34, "a1", 0, 0)]
    kept = KeptWords(
        words=words, shown={"a1:w0000": "Hola"}, masked=True, missing=(), hidden=frozenset()
    )  # 001.49
    monkeypatch.setattr(qa_run, "kept_words", lambda *a, **k: kept)
    monkeypatch.setattr(qa_run.cache, "read_index", lambda *a, **k: {"a1": "k"})
    monkeypatch.setattr(
        qa_run.cache,
        "load_transcript",
        lambda *a, **k: Transcript("a1", "k", "es", 0.9, 1000, [], [], {}, 1.0),
    )
    given: list[Any] = []

    def fake_hear(_project: Any, _video: Path, _language: str, **kwargs: Any) -> Heard:
        given.append(kwargs.get("limit_s"))
        return Heard([Word("qa:w0000", 0, "Hola", 0, 0, 0.9)], "es")

    monkeypatch.setattr(qa_run, "hear", fake_hear)
    edl = parsed()  # 345 frames at 30 fps = 11.5 s
    made = make_project(tmp_path)
    (made.root / "salida").mkdir()  # 001.47: `_transcript` looks at the file again before the ear
    (made.root / "salida" / "v1.mp4").write_bytes(b"not a video: the ear is a fake")
    qa_run._transcript(
        made,
        inventory(),
        edl,
        "salida/v1.mp4",  # 001.47: the relative name (it was `tmp_path / "v1.mp4"`)
        EburMeasure(-14.0, -2.0, 3.0),
        [],
        None,
    )
    assert given == [13.5]
