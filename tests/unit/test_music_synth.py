"""The synthetic music (spec S1.8b rows 1 and 2, 001.15): exact length, finite, the peak at 0.9,
the drums silent where `mute_drums` and `stop_drums_f` say, and the hi-hat of the pilot: it comes
from `default_rng(9)`, in the order of the hits, and a hit in a silent instant takes no numbers.
No ffmpeg. The port was compared with `piloto/music.py` (its wav, 120 bpm, `mute_drums` 7-9 s and
`stop_drums_f` at 10 s): the biggest difference was one step of 16 bits.
"""

import numpy as np
import pytest
from scipy.signal import butter, lfilter

from kcut.audio.music_model import SynthCfg
from kcut.audio.music_synth import synth_layers, synth_music

SR, FPS, SPF = 48000, 30, 1600
TOTAL = 552000  # the example EDL: 345 frames at 30 fps
PROGRESSION = ("Am", "F", "C", "G")


def _cfg(**changes: object) -> SynthCfg:
    base: dict[str, object] = {
        "bpm": 120.0,
        "progression": PROGRESSION,
        "drums": True,
        "mute_drums": (),
        "stop_drums_f": None,
        "origin_f": 0,
    }
    return SynthCfg(**(base | changes))  # type: ignore[arg-type]


def test_music_synth_the_length_is_exactly_total_and_it_is_finite() -> None:
    music = synth_music(_cfg(), TOTAL, FPS, SR)
    assert music.dtype == np.float32 and len(music) == TOTAL and np.isfinite(music).all()
    layers = synth_layers(_cfg(), TOTAL, FPS, SR)
    for layer in (layers.pad, layers.bass, layers.arp, layers.drums):
        assert layer.dtype == np.float32 and len(layer) == TOTAL


@pytest.mark.parametrize(
    ("total", "bpm", "origin_f"),
    [
        (552000, 60.0, 0),
        (552000, 180.0, 0),
        (100000, 120.0, 10),
        (20000, 120.0, 0),
        (1600, 90.0, 0),
    ],
)
def test_music_synth_any_length_tempo_or_origin_gives_the_exact_length(
    total: int, bpm: float, origin_f: int
) -> None:
    music = synth_music(_cfg(bpm=bpm, origin_f=origin_f), total, FPS, SR)
    assert len(music) == total and np.isfinite(music).all()


def test_music_synth_a_video_shorter_than_the_fade_is_fine() -> None:
    """The fade of the end is 1.2 s: a video of 0.4 s has it shorter, and not a shape error."""
    music = synth_music(_cfg(), 19200, FPS, SR)
    assert len(music) == 19200 and abs(float(music[-1])) < 0.05


def test_music_synth_the_peak_is_0_9_and_it_is_the_same_every_time() -> None:
    first = synth_music(_cfg(), TOTAL, FPS, SR)
    assert float(np.abs(first).max()) == pytest.approx(0.9, abs=1e-6)
    assert np.array_equal(first, synth_music(_cfg(), TOTAL, FPS, SR))  # no global chance


def test_music_synth_the_end_fades_to_silence() -> None:
    music = synth_music(_cfg(), TOTAL, FPS, SR)
    assert float(np.abs(music[-200:]).max()) < 0.02 < float(np.abs(music[:SR]).max())


def _energy(x: np.ndarray, start_f: int, end_f: int) -> float:
    """Mean of the squares of the samples of frames `[start_f, end_f)`."""
    return float(np.mean(x[start_f * SPF : end_f * SPF].astype(np.float64) ** 2))


def test_music_synth_the_drums_are_silent_in_mute_drums_and_play_outside() -> None:
    """Row 1: in the muted band the energy of the drums is under 5 % of the rest (here it is 0:
    no hit begins in `[start - 0.05, end)` and the ones before end before the window)."""
    layers = synth_layers(_cfg(mute_drums=((90, 210),)), TOTAL, FPS, SR)
    muted = _energy(layers.drums, 90, 210)
    outside = (_energy(layers.drums, 0, 90) * 90 + _energy(layers.drums, 210, 345) * 135) / 225
    assert outside > 0 and muted < 0.05 * outside
    assert muted == 0.0
    unmuted = synth_layers(_cfg(), TOTAL, FPS, SR).drums
    assert _energy(unmuted, 90, 210) > 0  # the same window has drums when it is not muted


def test_music_synth_a_hit_just_before_a_window_is_muted_with_it() -> None:
    """A window mutes from 0.05 s before its `start`. This one begins at frame 91 (3.0333 s), so
    it mutes from 2.9833 s: the kick of 3.0 s is inside the margin and is silent, and the hat of
    2.75 s, before it, still sounds."""
    layers = synth_layers(_cfg(mute_drums=((91, 150),)), TOTAL, FPS, SR)
    assert float(np.abs(layers.drums[144000 : 144000 + 2000]).max()) == 0.0  # the kick of 3.0 s
    assert float(np.abs(layers.drums[132000 : 132000 + 1900]).max()) > 0.0  # the hat of 2.75 s


def test_music_synth_stop_drums_f_silences_them_for_good() -> None:
    layers = synth_layers(_cfg(stop_drums_f=150), TOTAL, FPS, SR)
    assert _energy(layers.drums, 0, 150) > 0
    assert _energy(layers.drums, 160, 345) == 0.0  # 5.33 s: the last kick ended at 5.25 s
    assert not synth_layers(_cfg(drums=False), TOTAL, FPS, SR).drums.any()


def test_music_synth_nothing_sounds_before_the_origin() -> None:
    layers = synth_layers(_cfg(origin_f=60), TOTAL, FPS, SR)  # the grid begins at 2.0 s
    for layer in (layers.pad, layers.bass, layers.arp, layers.drums):
        assert not layer[: 60 * SPF].any()
    assert layers.bass[60 * SPF : 62 * SPF].any()  # the first bass note is on the downbeat
    assert layers.pad[60 * SPF : 62 * SPF].any()


def test_music_synth_the_progression_goes_round_with_the_bars() -> None:
    """Bar 0 is `Am` (bass A2 = 110 Hz) and bar 1 is `F` (F2 = 87.3 Hz): the bass note at the
    start of each bar has that pitch."""
    bass = synth_layers(_cfg(), TOTAL, FPS, SR).bass
    for bar, expected in ((0, 110.0), (1, 87.307), (2, 130.813), (3, 98.0), (4, 110.0)):
        start = bar * 2 * SR + 2400  # 0.05 s into the note
        spectrum = np.abs(np.fft.rfft(bass[start : start + 16384] * np.hanning(16384)))
        peak = np.argmax(spectrum) * SR / 16384
        assert peak == pytest.approx(expected, abs=SR / 16384 * 1.5), bar


def _first_hat(first_draw: int, count: int = 1) -> np.ndarray:
    """The hat made from draws `first_draw` ... of `default_rng(9)` (counting from 0): through the
    high-pass at 7500 Hz and the envelope `exp(-120 t) * 0.05`, as the rule of the spec says."""
    rng = np.random.default_rng(9)
    for _ in range(first_draw):
        rng.standard_normal(1920)
    noise = rng.standard_normal(1920).astype(np.float32)
    b, a = butter(2, 7500.0 / (SR / 2), "high")
    filtered = lfilter(b, a, noise).astype(np.float32)
    envelope = np.exp(-np.arange(1920) / SR * 120)
    return (filtered * envelope * 0.05).astype(np.float32)


def test_music_synth_hat_rng_the_first_hat_that_sounds_is_the_first_draw_of_default_rng_9() -> None:
    """Row 2: `mute_drums` over the first bar and a little more (frames 0-61, up to 2.033 s): the
    hits of 0 to 2.0 s do not sound and take no numbers, so the first hat that sounds, the one at
    2.25 s, is exactly the first `standard_normal(1920)` of `default_rng(9)`."""
    drums = synth_layers(_cfg(mute_drums=((0, 61),)), TOTAL, FPS, SR).drums
    first = 108000  # round(2.25 * 48000)
    assert not drums[:first].any()
    np.testing.assert_array_equal(drums[first : first + 1920], _first_hat(0))
    # and the next hat that sounds, at 2.75 s, is the second draw: the muted ones took none
    np.testing.assert_array_equal(drums[132000 : 132000 + 1920], _first_hat(1))


def test_music_synth_without_mute_the_first_hat_is_also_the_first_draw() -> None:
    drums = synth_layers(_cfg(), TOTAL, FPS, SR).drums
    np.testing.assert_array_equal(drums[12000 : 12000 + 1920], _first_hat(0))  # k = 1, 0.25 s
