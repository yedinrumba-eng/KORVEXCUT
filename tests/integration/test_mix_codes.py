"""The refusals of `kcut mix` and the mix with neither effects nor music (spec S1.8b, 001.15).

Before anything is made the command checks the EDL (exit 1), the words that the cut keeps,
`edit/sfx.json` (A01-A08) and `edit/music.json` (M01-M05); with an error in any of them the exit is
the one of `exit_code` (1; 5 for an M04) and no file is written. The lock of the output
(`build-vN`) is the one of `render`: held, exit 6. A project with no EDL is exit 3. Last, a mix
with no plan files: no effects (`sfx_events` 0), no music (`music` is `none`), the warning of an
event that falls partly before the start (A08) does not change the exit, and the human output.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut import cli
from kcut.render.lock import OutputLock
from tests.integration.mix_helpers import BUILD, SAMPLES, audio_project, measure, read_f32
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]


def _sfx(root: Path, *events: dict[str, Any]) -> None:
    document = {"schema": "kcut.sfx/1", "events": list(events)}
    (root / "edit" / "sfx.json").write_text(json.dumps(document), encoding="utf-8")


def _music(root: Path, document: dict[str, Any]) -> None:
    (root / "edit" / "music.json").write_text(json.dumps(document), encoding="utf-8")


def _nothing_was_made(root: Path) -> None:
    assert not (root / BUILD / "mix.wav").exists()
    assert not list((root / BUILD).glob("*.f32*")) if (root / BUILD).exists() else True


@pytest.fixture
def root(view_fresh: Path) -> Path:
    return audio_project(view_fresh, sfx=False, music=False)


@pytest.mark.parametrize(
    ("event", "code", "path"),
    [
        ({"type": "no-existe", "at": 1}, "A02", "events[0].type"),
        ({"type": "boom", "at": 1, "seed": -1}, "A03", "events[0].seed"),
        ({"type": "pop", "at": {"word": "a1:w0001", "edge": "start"}}, "A04", "events[0].at"),
        ({"type": "pop", "at": {"src": "a1", "f": 5}}, "A05", "events[0].at"),
        ({"type": "pop", "at": 345}, "A07", "events[0].at"),
        ({"type": "pop", "at": "ahora"}, "A01", "events[0].at"),
    ],
)
def test_mix_codes_an_error_of_sfx_json_is_exit_1_and_nothing_is_mixed(
    root: Path, kcut_json: Run, event: dict[str, Any], code: str, path: str
) -> None:
    _sfx(root, event)
    exit_, doc, err = kcut_json("mix", *project_args(root))
    assert exit_ == 1 and doc["ok"] is False, (doc, err)
    assert [(e["code"], e["path"]) for e in doc["errors"]] == [(code, path)]
    assert doc["mix"] is None and doc["errors_total"] == 1
    _nothing_was_made(root)


@pytest.mark.parametrize(
    ("document", "code", "path"),
    [
        ({"schema": "kcut.music/1", "mode": "loud"}, "M01", "mode"),
        (
            {
                "schema": "kcut.music/1",
                "mode": "synth",
                "synth": {"progression": ["Am"], "bpm": 200},
            },
            "M02",
            "synth.bpm",
        ),
        (
            {"schema": "kcut.music/1", "mode": "file", "file": {"path": "edit/tema.wav"}},
            "M03",
            "file.path",
        ),
        (
            {
                "schema": "kcut.music/1",
                "mode": "none",
                "windows": [{"start": 5, "end": 999, "gain_db": 1}],
            },
            "M05",
            "windows[0]",
        ),
    ],
)
def test_mix_codes_an_error_of_music_json_is_exit_1_and_nothing_is_mixed(
    root: Path, kcut_json: Run, document: dict[str, Any], code: str, path: str
) -> None:
    _music(root, document)
    exit_, doc, err = kcut_json("mix", *project_args(root))
    assert exit_ == 1 and [(e["code"], e["path"]) for e in doc["errors"]] == [(code, path)], err
    _nothing_was_made(root)


def test_mix_codes_the_errors_of_both_files_come_together(root: Path, kcut_json: Run) -> None:
    _sfx(root, {"type": "no-existe", "at": 1})
    _music(root, {"schema": "kcut.music/1", "mode": "loud"})
    exit_, doc, _ = kcut_json("mix", *project_args(root))
    assert exit_ == 1 and [e["code"] for e in doc["errors"]] == ["A02", "M01"]


def test_mix_codes_a_file_that_is_not_json_is_exit_3(root: Path, kcut_json: Run) -> None:
    (root / "edit" / "sfx.json").write_text(
        '{"schema": "kcut.sfx/1", "events": [', encoding="utf-8"
    )
    exit_, doc, _ = kcut_json("mix", *project_args(root))
    assert exit_ == 3 and "JSON mal formado" in doc["error"]["message"]


def test_mix_codes_an_edl_with_errors_is_exit_1_with_its_codes(root: Path, kcut_json: Run) -> None:
    path = root / "edit" / "edl-v1.json"
    edl = json.loads(path.read_text(encoding="utf-8"))
    edl["frames"] = 61
    path.write_text(json.dumps(edl), encoding="utf-8")
    exit_, doc, _ = kcut_json("mix", *project_args(root))
    assert exit_ == 1 and doc["error"]["kind"] == "CheckFailed" and "E08" in doc["error"]["message"]
    _nothing_was_made(root)


def test_mix_codes_the_lock_of_the_output_is_the_one_of_render(root: Path, kcut_json: Run) -> None:
    with OutputLock(root / ".kcut" / "locks", "build-v1"):
        exit_, doc, _ = kcut_json("mix", *project_args(root))
    assert exit_ == 6 and doc["error"]["kind"] == "LockedError"
    _nothing_was_made(root)


def test_mix_codes_a_project_with_no_edl_is_exit_3(view_fresh: Path, kcut_json: Run) -> None:
    exit_, doc, _ = kcut_json("mix", *project_args(view_fresh))  # ingested, but no edl-vN.json
    assert exit_ == 3 and "edl-vN.json" in doc["error"]["message"]


def test_mix_codes_a_project_that_was_not_ingested_is_exit_3(blank: Path, kcut_json: Run) -> None:
    exit_, doc, _ = kcut_json("mix", *project_args(blank))
    assert exit_ == 3 and "kcut ingest" in doc["error"]["message"]


def test_mix_codes_without_plan_files_there_are_no_effects_and_no_music(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `sfx.json`, no `music.json`: the mix is the voice alone, at the level of the delivery.
    An event that falls partly before the start is a warning (A08), not a reason to stop."""
    _sfx(root, {"type": "boom", "at": 0, "align": "end"})  # its end at frame 0: all before 0
    capsys.readouterr()
    code = cli.main(["mix", *project_args(root), "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert code == 0 and doc["ok"] is True and doc["music"] == "none", doc
    assert doc["sfx_events"] == 1 and doc["samples"] == SAMPLES
    assert [(w["code"], w["path"]) for w in doc["warnings"]] == [("A08", "events[0]")]
    found = measure(root / BUILD / "mix.wav")
    assert found.I is not None and -14.5 <= found.I <= -13.5, found  # only the voice, up to -14
    assert found.TP is not None and found.TP <= -1.0
    sfx = read_f32(root / BUILD / "sfx.f32")
    assert len(sfx) == SAMPLES and np.count_nonzero(sfx) <= 1  # the boom is cut to one sample
    assert not (root / BUILD / "music.f32").exists()


def test_mix_codes_the_human_output_says_where_the_mix_is_and_lists_the_warnings(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _sfx(root, {"type": "boom", "at": 0, "align": "end"})
    capsys.readouterr()
    assert cli.main(["mix", *project_args(root)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("[OK] .kcut/build/v1/mix.wav: 552000 muestras, ")
    assert any(line.startswith("[AVISO] A08 events[0]: ") for line in lines)
    assert all(line.isascii() or "ó" in line or "ñ" in line for line in lines)
