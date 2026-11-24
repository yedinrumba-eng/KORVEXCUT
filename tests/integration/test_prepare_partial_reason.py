"""`prepare_partial` says the reason before the path (spec 001.38, point 3; S1.9a row 13).

`no pude borrar {ruta}: {exc}; ...` repeated the path (the text of an `OSError` holds it) and put
the reason after it, so `cli`, which cuts a message to 300 characters, took the reason away in a
project in a deep folder. Now: `no pude borrar ({motivo}) {ruta}`, with the `strerror` (or the name
of the class) as the reason. Here, a project in a folder of 200 characters or more, where a partial
file of the mix cannot be deleted (`unlink` fails with `PermissionError`).
"""

import errno
import shutil
from pathlib import Path

import pytest

from tests.integration.mix_helpers import BUILD, audio_project
from tests.integration.view_frames_helpers import Run, Synth, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
LONG_ROOT = 205  # characters of the project path: over the 200 that the row asks for, and under
# the 260 of Windows once the log and the partial file are added to it
REASON = "Acceso denegado"


def _deep_copy(synth: Synth, tmp_path: Path) -> Path:
    """The synthetic project in a path of `LONG_ROOT` characters (a folder of padding is added to
    whatever the temporary folder is, so it holds with any `--basetemp`)."""
    sep = len(str(tmp_path / "x")) - len(str(tmp_path))
    name = "proyecto ñandú"
    pad = max(1, LONG_ROOT - len(str(tmp_path)) - 2 * sep - len(name))
    root = tmp_path / ("p" * pad) / name
    shutil.copytree(synth[0], root)
    return root


def test_prepare_partial_reason_the_message_that_kcut_prints_in_a_deep_folder_has_it(
    synth_project: Synth, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = audio_project(_deep_copy(synth_project, tmp_path))
    assert len(str(root)) >= 200
    real = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name.startswith("voice_chain.f32."):  # the partial file of the first filter
            raise PermissionError(errno.EACCES, REASON, str(self))
        real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    code, doc, err = kcut_json("mix", *project_args(root))
    message = doc["error"]["message"]
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert len(message) <= 300  # what `kcut` prints, already cut
    assert message.startswith(f"no pude borrar ({REASON}) "), message
    assert not (root / BUILD / "mix.wav").exists()


def test_prepare_partial_reason_a_mix_with_nothing_in_the_way_is_exit_0(
    synth_project: Synth, tmp_path: Path, kcut_json: Run
) -> None:
    root = audio_project(_deep_copy(synth_project, tmp_path))
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0 and doc["ok"] is True, (doc, err)
