"""The disk and `kcut mix` (spec S1.8b round 1, 001.37 points 4 and 10; rows 27 and 33).

Row 27: the mix leaves about 30 bytes per sample in its final files (eight of them) and about 34
with the partial in progress (`MIX_BYTES_PER_SAMPLE = 34`): a video of 10 minutes takes almost 1 GB.
`kcut mix` asks the disk for that and `SPARE_BYTES` (1 GiB) more before it mixes anything; if the
room is not there it is a ProjectError (exit 3) that says how many bytes are missing, with the
figures before the path, and nothing is written in `build/vN`. The disk is `shutil.disk_usage`.

Row 33: the message of a failed write has the reason before the path, `no pude escribir ({motivo})
en {ruta}`. `cli` cuts a message to 300 characters, and in a project in a deep folder the old
`no pude escribir {ruta}: {motivo}` lost the "No space left on device" to the cut.
"""

import errno
import os
import shutil
from collections import namedtuple
from pathlib import Path
from typing import Any

import pytest

from kcut.audio.voice_track import MIX_BYTES_PER_SAMPLE, SPARE_BYTES
from tests.integration.mix_helpers import BUILD, SAMPLES, audio_project
from tests.integration.view_frames_helpers import Run, Synth, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
NEEDED = SAMPLES * 34 + SPARE_BYTES
LONG_ROOT = 205  # characters of the project path: over the 200 that the row asks for, and under
# the 260 of Windows once `.kcut/logs/mix-<date>-<pid>.log` is added to it


def _disk(monkeypatch: pytest.MonkeyPatch, free: int) -> None:
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: usage(10**12, 10**12 - free, free))


def test_mix_disk_space_the_mix_asks_34_bytes_for_each_sample_and_a_gib_more() -> None:
    assert MIX_BYTES_PER_SAMPLE == 34 and SPARE_BYTES == 1 << 30
    assert NEEDED == 552000 * 34 + 2**30


def test_mix_disk_space_less_than_it_asks_is_exit_3_with_the_missing_bytes_and_nothing_written(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = audio_project(view_fresh)
    free = NEEDED - 12345
    _disk(monkeypatch, free)
    code, doc, err = kcut_json("mix", *project_args(root))
    message = doc["error"]["message"]
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert message.startswith(
        f"no hay espacio en el disco: faltan 12345 bytes (la mezcla y 1 GiB libre piden {NEEDED}, "
        f"hay {free}) en "
    ), message
    assert message.endswith("v1")  # the folder of the mix goes after the figures
    assert list((root / BUILD).iterdir()) == []  # asked before anything was written
    assert not (root / BUILD / "mix.wav").exists()


def test_mix_disk_space_exactly_what_it_asks_is_enough(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = audio_project(view_fresh)
    _disk(monkeypatch, NEEDED)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0 and doc["ok"] is True, (doc, err)
    assert (root / BUILD / "mix.wav").is_file()


def _deep_copy(synth: Synth, tmp_path: Path) -> Path:
    """The synthetic project in a path of `LONG_ROOT` characters (a folder of padding is added to
    whatever the temporary folder is, so it holds with any `--basetemp`)."""
    sep = len(str(tmp_path / "x")) - len(str(tmp_path))
    name = "proyecto ñandú"
    pad = max(1, LONG_ROOT - len(str(tmp_path)) - 2 * sep - len(name))
    root = tmp_path / ("p" * pad) / name
    shutil.copytree(synth[0], root)
    return root


def test_mix_disk_full_long_path_the_message_that_kcut_prints_keeps_the_reason(
    synth_project: Synth, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = audio_project(_deep_copy(synth_project, tmp_path))
    assert len(str(root)) >= 200
    real = os.replace

    def replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
        if Path(dst).name == "music.f32":  # the disk is full when the music is written
            raise OSError(errno.ENOSPC, "No space left on device", str(dst))  # with its file
        real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)
    code, doc, err = kcut_json("mix", *project_args(root))
    message = doc["error"]["message"]
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert len(message) <= 300  # what `kcut` prints, already cut
    assert message.startswith("no pude escribir (No space left on device) en "), message
    assert not (root / BUILD / "mix.wav").exists()
    assert not list((root / BUILD).glob("*.partial*"))
