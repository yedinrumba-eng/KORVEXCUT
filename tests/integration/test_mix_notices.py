"""The warnings of `kcut mix` (spec S1.8b round 1, 001.37 point 12; row 35).

The notices of a run (`cache_rebuilt` and the like, which `kept_words` collects while it reads the
transcripts) used to be printed only if the mix went through: with an error in `sfx.json` or in
`music.json` the command stopped and they were lost. Now they are printed before it stops. And
`pii_unmasked` is not printed by `kcut mix` at all: it says that the texts Claude reads are not
masked, and `mix` shows no text (the other commands that do keep saying it).
"""

import json
from pathlib import Path

import pytest

from kcut import cli
from tests.integration.mix_helpers import audio_project
from tests.integration.view_frames_helpers import project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
CACHE_REBUILT = "[AVISO] cache_rebuilt: index.json: el índice era inválido y se ignora"


def _break_the_index(root: Path) -> None:
    """A transcripts index that is not JSON: `kept_words` ignores it and makes `cache_rebuilt`."""
    folder = root / ".kcut" / "transcripts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.json").write_text("{", encoding="utf-8")


def _mask_pii_off(root: Path) -> None:
    path = root / "kcut.toml"
    text = path.read_text(encoding="utf-8")
    assert "mask_pii = true" in text
    path.write_text(text.replace("mask_pii = true", "mask_pii = false"), encoding="utf-8")


def test_mix_notices_an_error_of_sfx_json_and_a_notice_of_kept_words_are_both_printed(
    view_fresh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = audio_project(view_fresh, sfx=False, music=False)
    document = {"schema": "kcut.sfx/1", "events": [{"type": "pop", "at": "ahora"}]}
    (root / "edit" / "sfx.json").write_text(json.dumps(document), encoding="utf-8")
    _break_the_index(root)
    capsys.readouterr()
    code = cli.main(["mix", *project_args(root)])
    shown = capsys.readouterr()
    assert code == 1
    assert "[ERROR] A01 events[0].at: " in shown.out  # the error, as it always was
    assert CACHE_REBUILT in shown.err.splitlines()  # 001.37: and the notice, before it stops
    assert not (root / ".kcut" / "build" / "v1" / "mix.wav").exists()


def test_mix_notices_an_error_of_music_json_prints_the_notices_too(
    view_fresh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = audio_project(view_fresh, sfx=False, music=False)
    document = {"schema": "kcut.music/1", "mode": "loud"}
    (root / "edit" / "music.json").write_text(json.dumps(document), encoding="utf-8")
    _break_the_index(root)
    capsys.readouterr()
    assert cli.main(["mix", *project_args(root)]) == 1
    shown = capsys.readouterr()
    assert "[ERROR] M01 mode: " in shown.out and CACHE_REBUILT in shown.err.splitlines()


def test_mix_notices_a_mix_that_goes_through_prints_them_once(
    view_fresh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = audio_project(view_fresh, sfx=False, music=False)
    _break_the_index(root)
    capsys.readouterr()
    assert cli.main(["mix", *project_args(root)]) == 0
    assert capsys.readouterr().err.splitlines().count(CACHE_REBUILT) == 1


def test_mix_notices_pii_unmasked_is_not_shown_by_mix(
    view_fresh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = audio_project(view_fresh, sfx=False, music=False)
    _mask_pii_off(root)
    capsys.readouterr()
    assert cli.main(["mix", *project_args(root)]) == 0  # the mix goes through, and says nothing
    shown = capsys.readouterr()
    assert "pii_unmasked" not in shown.out + shown.err


def test_mix_notices_pii_unmasked_is_not_shown_when_the_plan_has_errors_either(
    view_fresh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = audio_project(view_fresh, sfx=False, music=False)
    document = {"schema": "kcut.sfx/1", "events": [{"type": "pop", "at": "ahora"}]}
    (root / "edit" / "sfx.json").write_text(json.dumps(document), encoding="utf-8")
    _mask_pii_off(root)
    _break_the_index(root)
    capsys.readouterr()
    assert cli.main(["mix", *project_args(root), "--json"]) == 1
    shown = capsys.readouterr()
    assert "pii_unmasked" not in shown.out + shown.err
    assert CACHE_REBUILT in shown.err.splitlines()  # the other notice does come out
