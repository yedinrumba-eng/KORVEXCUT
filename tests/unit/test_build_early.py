"""`kcut build` looks at what it can before the work (spec 001.52, rows 38, 39 and 42).

- `build_folder_early`: a folder where a file of `.kcut/build/vN/` goes is exit 3 at once, as in
  `kcut render`, and not after the mezzanines.
- `build_space`: the disk is asked once, for everything, with one GiB of margin.
- `build_qa_early`: a link in what `qa/vN/` is going to receive is exit 3 before the work.

The heavy steps are doubles (`early_build`); `Reached` says the picture was started.
"""

import hashlib
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from kcut.audio.voice_track import MIX_BYTES_PER_SAMPLE, SPARE_BYTES
from kcut.errors import ProjectError
from kcut.pipeline import build as build_module
from kcut.pipeline.destinations import build_destinations
from kcut.pipeline.snapshot import stale_rels
from tests.unit.build_early_helpers import Reached, early_build, run

FOLDER = ("video.mp4", "video.partial.mp4", "mix.wav", "voice_raw.f32", "mix.f32")
SAMPLES = 250 * (48000 // 25)  # 250 frames at 25 fps


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_build_folder_early_without_a_folder_the_picture_is_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    early = early_build(tmp_path, monkeypatch)
    with pytest.raises(Reached):
        run(early)
    assert early.reached == ["make_video"]  # the doubles work: this is what the rest compare to


@pytest.mark.parametrize("name", FOLDER)
def test_build_folder_early_a_folder_in_a_destination_is_exit_3_before_the_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    early = early_build(tmp_path, monkeypatch)
    (early.project.layout.build_dir(1) / name).mkdir(parents=True)
    with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo") as e:
        run(early)
    assert e.value.exit_code == 3
    assert early.reached == []  # neither the mezzanines nor the picture were started


def test_build_folder_early_the_partial_of_the_mix_of_this_process_is_a_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    early = early_build(tmp_path, monkeypatch)
    name = f"mix.wav.{os.getpid()}.partial"
    assert name in build_destinations()
    (early.project.layout.build_dir(1) / name).mkdir(parents=True)
    with pytest.raises(ProjectError) as e:
        run(early)
    assert e.value.exit_code == 3 and early.reached == []


def _needed(layer: int) -> int:
    return SAMPLES * MIX_BYTES_PER_SAMPLE + layer + SPARE_BYTES


def _free(monkeypatch: pytest.MonkeyPatch, free: int) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: SimpleNamespace(free=free))


def test_build_space_one_byte_short_is_exit_3_and_nothing_is_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layer = 5_000_000
    early = early_build(tmp_path, monkeypatch, layer=layer)
    _free(monkeypatch, _needed(layer) - 1)
    with pytest.raises(ProjectError, match="la mezcla, la capa de gráficos y 1 GiB libre") as e:
        run(early)
    assert e.value.exit_code == 3 and "faltan 1 bytes" in str(e.value)
    assert early.reached == []  # `make_video` was not called


def test_build_space_exactly_what_it_asks_passes_the_look(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layer = 5_000_000
    early = early_build(tmp_path, monkeypatch, layer=layer)
    _free(monkeypatch, _needed(layer))
    with pytest.raises(Reached):
        run(early)
    assert early.reached == ["make_video"]


def test_build_space_without_a_layer_it_names_only_the_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    early = early_build(tmp_path, monkeypatch, layer=0)
    _free(monkeypatch, _needed(0) - 1)
    with pytest.raises(ProjectError, match="la mezcla y 1 GiB libre") as e:
        run(early)
    assert "gráficos" not in str(e.value) and early.reached == []


def test_build_qa_early_a_hard_link_in_the_snapshot_is_exit_3_before_the_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    early = early_build(tmp_path, monkeypatch)
    root = early.project.root
    (root / "salida" / "v1.mp4").write_bytes(b"the old video")
    inputs = root / "qa" / "v1" / "inputs"
    inputs.mkdir(parents=True)
    try:
        os.link(root / "crudo" / "brief.txt", inputs / "inputs.json")
    except OSError:
        pytest.skip("no se puede crear un hard link aquí")
    brief, video = _sha(root / "crudo" / "brief.txt"), _sha(root / "salida" / "v1.mp4")
    with pytest.raises(ProjectError) as e:
        run(early)
    assert e.value.exit_code == 3
    assert early.reached == []  # `make_video` was not called
    assert _sha(root / "crudo" / "brief.txt") == brief
    assert _sha(root / "salida" / "v1.mp4") == video


def test_build_qa_early_the_checked_list_is_the_one_clear_stale_deletes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    early = early_build(tmp_path, monkeypatch)
    seen: list[str] = []
    real = build_module.assert_writable

    def spy(project: object, rel: str) -> Path:
        seen.append(rel)
        return real(project, rel)  # type: ignore[arg-type]

    monkeypatch.setattr(build_module, "assert_writable", spy)
    with pytest.raises(Reached):
        run(early)
    assert set(stale_rels(1, "edit/edl-v1.json")) <= set(seen)
