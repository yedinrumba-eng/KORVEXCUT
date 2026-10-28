"""The chain of filters on the voice and the command lines of the mixer (spec S1.8b row 8, 001.15).

`denoise_nr == 0` leaves `afftdn` out (it does not take less than 0.01: `kcut.toml` refuses what is
between 0 and 0.01); 10 puts `afftdn=nr=10`. The threshold of the compressor is the linear factor of
`comp_threshold_db`. `kcut.toml` side of the same row: `tests/unit/test_config.py -k denoise`.
Pure: nothing is run here.
"""

import dataclasses
from pathlib import Path

import pytest

from kcut.audio.mixer import chain_args, graph_args, voice_chain
from kcut.config.load import parse_config
from kcut.config.model import VoiceChain

CFG = parse_config("", default_name="x").audio.voice
FFMPEG = Path("C:/tools/ffmpeg.exe")


def test_mixer_chain_denoise_with_zero_has_no_afftdn() -> None:
    chain = voice_chain(dataclasses.replace(CFG, denoise_nr=0.0))
    assert "afftdn" not in chain
    assert chain.startswith("highpass=f=80,acompressor=threshold=")


def test_mixer_chain_denoise_with_10_has_afftdn_nr_10() -> None:
    chain = voice_chain(dataclasses.replace(CFG, denoise_nr=10.0))
    assert "afftdn=nr=10" in chain
    assert chain.split(",")[:2] == ["highpass=f=80", "afftdn=nr=10:nf=-40"]


def test_mixer_chain_the_default_chain_is_the_one_of_the_spec() -> None:
    assert voice_chain(CFG) == (
        "highpass=f=80,afftdn=nr=10:nf=-40,"
        "acompressor=threshold=0.125893:ratio=3:attack=10:release=150:makeup=1"
    )


@pytest.mark.parametrize(
    ("db", "linear"), [(-18.0, "0.125893"), (-20.0, "0.1"), (0.0, "1"), (-40.0, "0.01")]
)
def test_mixer_chain_the_compressor_threshold_is_linear(db: float, linear: str) -> None:
    chain = voice_chain(dataclasses.replace(CFG, comp_threshold_db=db))
    assert f"acompressor=threshold={linear}:" in chain


def test_mixer_chain_every_number_comes_from_the_configuration() -> None:
    cfg = VoiceChain(
        highpass_hz=120, denoise_nr=22.5, denoise_nf=-55.0, comp_threshold_db=-10.0, comp_ratio=4.5
    )
    assert voice_chain(cfg) == (
        "highpass=f=120,afftdn=nr=22.5:nf=-55,"
        "acompressor=threshold=0.316228:ratio=4.5:attack=10:release=150:makeup=1"
    )


def test_mixer_chain_the_smallest_noise_reduction_that_afftdn_takes() -> None:
    assert "afftdn=nr=0.01:" in voice_chain(dataclasses.replace(CFG, denoise_nr=0.01))


def test_mixer_chain_args_have_the_chain_as_one_argument_and_the_files_as_paths() -> None:
    src, dst = Path("C:/p/voice_raw.f32"), Path("C:/p/voice_chain.f32.9.partial")
    args = chain_args(FFMPEG, src, dst, voice_chain(CFG))
    assert args[:5] == [str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error"]
    assert args[args.index("-i") + 1] == str(src) and args[-1] == str(dst)
    assert args[args.index("-af") + 1] == voice_chain(CFG)
    assert args[-7:-1] == ["-f", "f32le", "-ar", "48000", "-ac", "1"] and "-y" not in args


def test_mixer_chain_graph_args_read_each_input_as_raw_float32_and_map_the_mix() -> None:
    inputs = [Path("C:/p/voice.f32"), Path("C:/p/music.f32"), Path("C:/p/sfx.f32")]
    dst = Path("C:/p/mix_pre.f32.9.partial")
    args = graph_args(FFMPEG, inputs, "[0:a][1:a][2:a]amix=inputs=3[mix]", dst)
    assert args.count("-i") == 3 and args.count("f32le") == 4  # three inputs and the output
    assert [args[i + 1] for i, a in enumerate(args) if a == "-i"] == [str(p) for p in inputs]
    assert args[args.index("-filter_complex") + 1].endswith("[mix]")
    assert args[args.index("-map") + 1] == "[mix]" and args[-1] == str(dst)
    for path in inputs:  # a path is an argument of `-i`, never inside the graph
        assert str(path) not in args[args.index("-filter_complex") + 1]
