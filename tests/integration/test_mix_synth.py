"""`kcut mix` on the synthetic project (spec S1.8b row 5, 001.15): the example EDL of 345 frames,
the `sfx.json` and the `music.json` of the spec. `mix.wav` has 552 000 samples, 16 bits, mono,
48 kHz; the `ebur128` of the wav gives I between -14.5 and -13.5 LUFS and a true peak of at most
-1.0 dBTP;
every intermediate file of `.kcut/build/v1/` is exactly that long. The strategy does not have to
be approved (`mix` does not ask for the gate), and nothing of `crudo/` is touched.
"""

import json
import shutil
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from tests.conftest import run_kcut
from tests.integration.graphics_helpers import tree_hash
from tests.integration.mix_helpers import (
    BUILD,
    SAMPLES,
    SPF,
    audio_project,
    measure,
    read_f32,
    read_wav,
)
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
F32_FILES = (
    "voice_raw.f32", "voice_chain.f32", "voice.f32", "music.f32", "sfx.f32",
    "mix_pre.f32", "mix.f32",
)  # fmt: skip


SAME_FILES = (  # 001.37: what the second run of `kcut mix` has to repeat to the byte
    "voice_raw.f32", "voice_chain.f32", "voice.f32", "music.f32", "sfx.f32",
    "mix_pre.f32", "mix.f32",
)  # fmt: skip


class Mixed(NamedTuple):
    root: Path
    code: int
    doc: dict[str, Any]
    err: str
    crudo_before: str


@pytest.fixture(scope="module")
def mixed(tmp_path_factory: pytest.TempPathFactory, view_shared: Path) -> Mixed:
    """The synthetic project mixed once for the module; the tests read `.kcut/build/v1/`, and
    none of them changes it."""
    root = tmp_path_factory.mktemp("mixed") / "proyecto ñandú"
    shutil.copytree(view_shared, root)
    audio_project(root)
    before = tree_hash(root / "crudo")
    done = run_kcut("mix", "--json", "--project", str(root))
    return Mixed(root, done.returncode, json.loads(done.stdout), done.stderr, before)


def test_mix_synth_the_wav_has_552000_samples_in_16_bits_mono_at_48_khz(mixed: Mixed) -> None:
    assert mixed.code == 0 and mixed.doc["ok"] is True, (mixed.doc, mixed.err)
    assert mixed.doc["mix"] == f"{BUILD}/mix.wav" and mixed.doc["samples"] == SAMPLES == 552000
    samples, channels, width, rate = read_wav(mixed.root / BUILD / "mix.wav")
    assert (len(samples), channels, width, rate) == (552000, 1, 2, 48000)


def test_mix_synth_the_loudness_of_the_wav_is_the_target_and_the_peak_is_under_the_ceiling(
    mixed: Mixed,
) -> None:
    found = measure(mixed.root / BUILD / "mix.wav")
    assert found.I is not None and -14.5 <= found.I <= -13.5, found
    assert found.TP is not None and found.TP <= -1.0, found


def test_mix_synth_the_json_says_what_was_measured(mixed: Mixed) -> None:
    doc = mixed.doc
    assert doc["music"] == "synth" and doc["sfx_events"] == 13
    assert doc["errors"] == [] and doc["errors_total"] == 0 and doc["truncated"] is False
    assert doc["warnings"] == [] and doc["warnings_total"] == 0, doc["warnings"]
    wav = measure(mixed.root / BUILD / "mix.wav")
    assert wav.I is not None and wav.TP is not None
    assert doc["mix_I"] == pytest.approx(wav.I, abs=0.06)
    assert doc["mix_TP"] == pytest.approx(wav.TP, abs=0.06)
    voice = measure(mixed.root / BUILD / "voice.f32", raw=True)
    assert voice.I is not None and doc["voice_lufs"] == pytest.approx(voice.I, abs=0.06)
    assert -16.5 <= doc["voice_lufs"] <= -15.5  # `voice_lufs` of kcut.toml is -16


def test_mix_synth_every_intermediate_file_is_exactly_frames_times_spf_samples(
    mixed: Mixed,
) -> None:
    for name in F32_FILES:
        assert (mixed.root / BUILD / name).stat().st_size == SAMPLES * 4, name
    assert SAMPLES == 345 * SPF


def test_mix_synth_the_mix_has_the_voice_the_music_and_the_effects_in_it(mixed: Mixed) -> None:
    build = mixed.root / BUILD
    voice, mix, sfx, music = (
        read_f32(build / n) for n in ("voice.f32", "mix.f32", "sfx.f32", "music.f32")
    )
    assert sfx.any() and music.any() and voice.any()
    assert abs(sfx[: SPF * 5]).max() > 0  # the boom of frame 0 is in the first frames
    assert not (mix == voice).all()  # the music and the effects are in it
    assert len(sfx) == len(music) == len(voice) == len(mix) == SAMPLES


def test_mix_synth_nothing_is_left_half_done_and_crudo_is_untouched(mixed: Mixed) -> None:
    assert not list((mixed.root / BUILD).glob("*.partial*"))
    assert tree_hash(mixed.root / "crudo") == mixed.crudo_before
    assert not list((mixed.root / "salida").glob("*.mp4"))  # `mix` does not make a video


def test_mix_synth_the_gate_is_not_asked_and_a_second_run_gives_the_same_mix(
    view_fresh: Path, kcut_json: Run, tmp_path: Path
) -> None:
    """`mix` does not ask for the gate of the strategy (`render` would say exit 5), and it can be
    run again over its own files. 001.37: the second run gives the same files as the first one, to
    the byte and over the whole length (no tolerance, no tail left out): `voice_raw`, `music`,
    `sfx`, `voice_chain`, `voice`, `mix_pre` and `mix`. `mix_pre` is the graph with ducking, which
    used to lose the tail of the music at a different sample in each run (`apad` on both inputs of
    the compressor fixed it)."""
    root = audio_project(view_fresh)
    strategy = root / "edit" / "estrategia.md"
    text = strategy.read_text(encoding="utf-8").replace("aprobado: si", "aprobado: no")
    strategy.write_text(text, encoding="utf-8", newline="\n")
    code, first, err = kcut_json("mix", *project_args(root))
    assert code == 0 and first["samples"] == SAMPLES, (first, err)
    shutil.copytree(root / BUILD, tmp_path / "primera")
    code, second, err = kcut_json("mix", *project_args(root))
    assert code == 0 and second["samples"] == SAMPLES, err
    for name in SAME_FILES:  # 001.37: exact, every file, the whole length
        assert (root / BUILD / name).read_bytes() == (tmp_path / "primera" / name).read_bytes(), (
            name
        )
    assert second["mix_I"] == first["mix_I"]  # 001.37: was approx(abs=0.11)
    assert second["voice_lufs"] == first["voice_lufs"]  # 001.37: was approx(abs=0.11)
