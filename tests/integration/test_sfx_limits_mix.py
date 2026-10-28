"""What `kcut mix` does with the limits of `sfx.json` and `music.json` (spec S1.8b step 0, 001.36
point 1; row 12). The plan files are read with a cap of 1 MiB: one byte over is the size error of
`read_json`, exit 3, before anything is parsed. The findings are listed `MAX_SHOWN` at a time (50
errors and 50 warnings) with their totals, as `graphics check` does, and 2001 events are one A01.
The schema side (`MAX_EVENTS`, `MAX_WINDOWS`, 4000 anchors in under a second) is in
`tests/unit/test_sfx_limits.py`.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from kcut.issues import MAX_SHOWN
from tests.integration.mix_helpers import BUILD, audio_project
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
MIB = 1024 * 1024


def _padded(document: dict[str, Any], size: int) -> bytes:
    """The JSON of `document` followed by spaces up to exactly `size` bytes."""
    text = json.dumps(document).encode("utf-8")
    return text + b" " * (size - len(text))


def _write_sfx(root: Path, document: object) -> None:
    (root / "edit" / "sfx.json").write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def root(view_fresh: Path) -> Path:
    return audio_project(view_fresh, sfx=False, music=False)


def test_sfx_limits_mix_a_sfx_json_of_1_mib_and_a_byte_is_exit_3_and_is_not_parsed(
    root: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "edit" / "sfx.json").write_bytes(
        _padded({"schema": "kcut.sfx/1", "events": []}, MIB + 1)
    )

    def refuse(*_a: Any, **_k: Any) -> None:
        pytest.fail("parse_sfx ran on a file over the cap")

    monkeypatch.setattr("kcut.commands.mix.parse_sfx", refuse)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert "pesa más de 1 MB" in doc["error"]["message"] and "events" not in doc["error"]["message"]
    assert not (root / BUILD / "mix.wav").exists()


def test_sfx_limits_mix_a_music_json_of_1_mib_and_a_byte_is_exit_3_too(
    root: Path, kcut_json: Run
) -> None:
    (root / "edit" / "music.json").write_bytes(
        _padded({"schema": "kcut.music/1", "mode": "none"}, MIB + 1)
    )
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 3 and "pesa más de 1 MB" in doc["error"]["message"], (doc, err)


def test_sfx_limits_mix_a_file_of_exactly_1_mib_is_read(root: Path, kcut_json: Run) -> None:
    """At the cap it is read: here it has an event of a type that does not exist, so it ends in an
    A02 (exit 1) and not in the size error (exit 3)."""
    document = {"schema": "kcut.sfx/1", "events": [{"type": "no-existe", "at": 1}]}
    (root / "edit" / "sfx.json").write_bytes(_padded(document, MIB))
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 1 and [e["code"] for e in doc["errors"]] == ["A02"], (doc, err)


def test_sfx_limits_mix_2001_events_are_one_a01_in_events_and_exit_1(
    root: Path, kcut_json: Run
) -> None:
    _write_sfx(root, {"schema": "kcut.sfx/1", "events": [{"type": "kick", "at": 3}] * 2001})
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 1 and doc["ok"] is False, (doc, err)
    assert [(e["code"], e["path"]) for e in doc["errors"]] == [("A01", "events")]
    assert doc["errors_total"] == 1 and doc["truncated"] is False


def _many_findings(root: Path) -> None:
    """120 errors (a pop outside the video: A07) and 60 warnings (a boom whose end is at frame 0:
    part of it falls before the start, A08)."""
    events: list[dict[str, Any]] = [{"type": "pop", "at": 99999}] * 120
    events += [{"type": "boom", "at": 0, "align": "end"}] * 60
    _write_sfx(root, {"schema": "kcut.sfx/1", "events": events})


def test_sfx_limits_mix_json_lists_50_errors_and_50_warnings_with_their_totals(
    root: Path, kcut_json: Run
) -> None:
    _many_findings(root)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 1 and doc["ok"] is False, (doc, err)
    assert len(doc["errors"]) == MAX_SHOWN == 50 and len(doc["warnings"]) == 50
    assert (doc["errors_total"], doc["warnings_total"], doc["truncated"]) == (120, 60, True)
    assert {e["code"] for e in doc["errors"]} == {"A07"}
    assert {w["code"] for w in doc["warnings"]} == {"A08"}
    assert doc["errors"][0]["path"] == "events[0].at"


def test_sfx_limits_mix_the_human_output_lists_50_and_says_how_many_more(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _many_findings(root)
    code = cli.main(["mix", *project_args(root)])
    out = capsys.readouterr().out
    assert code == 1
    lines = out.splitlines()
    assert sum(line.startswith("[ERROR] A07") for line in lines) == 50
    assert sum(line.startswith("[AVISO] A08") for line in lines) == 50
    assert "[ERROR] ... y 70 más" in lines and "[AVISO] ... y 10 más" in lines


def test_sfx_limits_mix_a_few_findings_are_all_listed_and_not_truncated(
    root: Path, kcut_json: Run
) -> None:
    _write_sfx(root, {"schema": "kcut.sfx/1", "events": [{"type": "pop", "at": 99999}] * 3})
    code, doc, _ = kcut_json("mix", *project_args(root))
    assert code == 1 and (doc["errors_total"], doc["truncated"]) == (3, False)
    assert len(doc["errors"]) == 3 and doc["warnings"] == [] and doc["warnings_total"] == 0
