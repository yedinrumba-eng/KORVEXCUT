"""`apad` is a required filter of `kcut doctor` (spec 001.38, point 5; S1.9a row 15; §1.1).

The ducking graph of the mix pads both inputs of the compressor with `apad` (001.37): an ffmpeg
without it passed `kcut doctor` and failed later in `kcut mix`. The list of the filters that the
fake ffmpeg answers is written here out of the spec, name by name, not derived from
`REQUIRED_FILTERS`: a list derived from the constant would always agree with it.
"""

import json

import pytest

from kcut import cli, proc
from kcut.doctor import checks
from tests.unit.doctor_fakes import FakeFfmpeg

SPEC_FILTERS = (  # §1.1, in the order it lists them
    "zscale", "tonemap", "loudnorm", "ebur128", "sidechaincompress", "afftdn", "blackdetect",
    "freezedetect", "overlay", "acompressor", "highpass", "asplit", "apad", "anullsink", "amix",
    "aresample", "scale", "fps", "colorbalance", "curves", "vibrance", "vignette", "colorhold",
)  # fmt: skip


def test_doctor_apad_is_in_the_required_filters() -> None:
    assert checks.REQUIRED_FILTERS == SPEC_FILTERS


def test_doctor_apad_missing_is_named_as_missing(
    monkeypatch: pytest.MonkeyPatch,
    light_checks: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    without = tuple(name for name in SPEC_FILTERS if name != "apad")
    monkeypatch.setattr(proc, "run", FakeFfmpeg(filters=(*without, *checks.OPTIONAL_FILTERS)))
    assert cli.main(["doctor", "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    found = next(item for item in doc["checks"] if item["id"] == "filters")
    assert doc["ok"] is False and found["ok"] is False
    assert found["detail"] == "22/23 faltan: apad"


def test_doctor_apad_all_the_filters_of_the_spec_pass(
    monkeypatch: pytest.MonkeyPatch,
    light_checks: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(proc, "run", FakeFfmpeg(filters=(*SPEC_FILTERS, *checks.OPTIONAL_FILTERS)))
    assert cli.main(["doctor", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    found = next(item for item in doc["checks"] if item["id"] == "filters")
    assert found["ok"] is True and found["detail"] == "23/23"
