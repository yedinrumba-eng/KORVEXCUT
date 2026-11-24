"""One formula for the time an `ffmpeg` on audio is given (spec 001.38, point 4; S1.9a row 14).

`audio/loudnorm.audio_timeout_s` is it: 10 s for each second of audio and never less than 60 s.
`mixer` and `music_file` used to carry their own copy of the two constants; now they call it. This
is the structural half (the constants are not defined there any more); the other half, a spy on
`proc.run` that sees the timeout of every call, is in `tests/integration/test_audio_timeout_shared`.
"""

import ast
from pathlib import Path

import pytest

from kcut.audio import loudnorm, mixer, music_file

SRC = Path(__file__).resolve().parents[2] / "src" / "kcut" / "audio"
CONSTANTS = ("_TIMEOUT_FLOOR_S", "_TIMEOUT_PER_AUDIO_S")


@pytest.mark.parametrize("module", [mixer, music_file], ids=["mixer", "music_file"])
def test_audio_timeout_shared_the_module_defines_no_constants_of_its_own(module: object) -> None:
    for name in CONSTANTS:
        assert not hasattr(module, name), name


@pytest.mark.parametrize("name", ["mixer.py", "music_file.py"])
def test_audio_timeout_shared_the_source_does_not_name_them_either(name: str) -> None:
    tree = ast.parse((SRC / name).read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not names & set(CONSTANTS), names & set(CONSTANTS)


@pytest.mark.parametrize("module", [mixer, music_file], ids=["mixer", "music_file"])
def test_audio_timeout_shared_the_module_uses_the_function_of_loudnorm(module: object) -> None:
    assert getattr(module, "audio_timeout_s") is loudnorm.audio_timeout_s  # noqa: B009


def test_audio_timeout_shared_the_formula() -> None:
    assert loudnorm.audio_timeout_s(0.0) == 60.0
    assert loudnorm.audio_timeout_s(11.5) == 175.0
    assert loudnorm.audio_timeout_s(3600.0) == 36060.0
