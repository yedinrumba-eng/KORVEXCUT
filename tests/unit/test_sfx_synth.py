"""The synthesized sound effects (spec S1.8a rows 1 and 5, 001.15): the 13 functions of the pilot as
functions of the number of samples, `(n, sr, **params) -> float32[n]`.

Row 1: the same call gives the same bytes (and nothing depends on the global state of `numpy`), the
length is exactly `n` (the fixed ones of the table, in samples at 48 kHz; `whoosh` and `shimmer`
with no `dur_f` last 14 and 33 frames at 30 fps), every sample is finite and the peak is at most 1.
The peak is that of the sound as the library gives it, with its default gain (the pilot's `gain`
is what it is for: the raw `whoosh` of the pilot peaks at 1.41). Row 5: the seeds are parameters
with the defaults of the pilot.
"""

import numpy as np
import pytest
from scipy.signal import lfilter

from kcut.audio import sfx_synth as synth
from kcut.audio.sfx_library import SFX
from kcut.timebase import ms_to_f_round

SR = 48000
SPF = 1600  # samples per frame at 30 fps
FIXED = {
    "boom": 43200,
    "pop": 5760,
    "key": 2400,
    "click": 2880,
    "kick": 15360,
    "hat": 2160,
    "blip8": 10560,
    "powerup": 26400,
}
DURATION = {
    "whoosh": 14 * SPF,
    "shimmer": 33 * SPF,
    "pad": 40 * SPF,
    "typing": 25 * SPF,
    "riser": 15 * SPF,
}


def _n(name: str) -> int:
    return FIXED[name] if name in FIXED else DURATION[name]


def _make(name: str, **params: float) -> np.ndarray:
    return SFX[name].fn(_n(name), SR, **params)


def test_sfx_synth_the_library_has_the_13_types_and_the_lengths_of_the_table() -> None:
    assert sorted(SFX) == sorted([*FIXED, *DURATION])
    assert len(SFX) == 13
    for name, n in FIXED.items():
        assert SFX[name].fixed_n == n and SFX[name].default_dur_ms is None, name
    assert SFX["whoosh"].default_dur_ms == 450 and SFX["shimmer"].default_dur_ms == 1100
    assert ms_to_f_round(450, 30) == 14 and ms_to_f_round(1100, 30) == 33  # frames at 30 fps
    for name in ("pad", "typing", "riser"):
        assert SFX[name].requires_dur and SFX[name].fixed_n is None, name


@pytest.mark.parametrize("name", sorted(SFX))
def test_sfx_synth_exact_length_float32_finite_and_a_peak_of_at_most_1(name: str) -> None:
    y = _make(name)
    assert y.shape == (_n(name),) and y.dtype == np.float32
    assert bool(np.isfinite(y).all())
    peak = float(np.abs(y).max())
    assert 0.0 < peak * SFX[name].default_gain <= 1.0, (name, peak)


@pytest.mark.parametrize("name", sorted(SFX))
def test_sfx_synth_the_same_call_is_the_same_bytes_whatever_numpy_global_state_is(
    name: str,
) -> None:
    np.random.seed(1)
    first = _make(name).tobytes()
    np.random.seed(2)
    np.random.random(1000)  # the global generator is not the one the effects use
    assert _make(name).tobytes() == first


@pytest.mark.parametrize(
    ("name", "param", "a", "b"),
    [
        ("whoosh", "seed", 1, 2),
        ("boom", "seed", 7, 8),
        ("key", "seed", 0, 1),
        ("hat", "seed", 0, 1),
        ("typing", "seed", 55, 56),
        ("riser", "seed", 77, 78),
        ("pop", "freq", 820.0, 700.0),
        ("typing", "rate", 13.0, 8.0),
    ],
)
def test_sfx_synth_another_seed_or_parameter_is_another_sound(
    name: str, param: str, a: float, b: float
) -> None:
    assert _make(name, **{param: a}).tobytes() != _make(name, **{param: b}).tobytes()
    assert _make(name, **{param: a}).tobytes() == _make(name, **{param: a}).tobytes()


@pytest.mark.parametrize(
    ("name", "default"),
    [("whoosh", 1), ("boom", 7), ("key", 0), ("hat", 0), ("typing", 55), ("riser", 77)],
)
def test_sfx_synth_seed_default_is_the_one_of_the_pilot(name: str, default: int) -> None:
    """Row 5: with no `seed` the bytes are those of the default seed; another seed, others."""
    assert _make(name).tobytes() == _make(name, seed=default).tobytes()
    assert _make(name).tobytes() != _make(name, seed=default + 1).tobytes()
    spec = next(p for p in SFX[name].params if p.name == "seed")
    assert spec.default == default  # the library says the same: it is where the schema reads it


def test_sfx_synth_seed_default_only_the_types_with_chance_have_a_seed() -> None:
    with_seed = {n for n in SFX if any(p.name == "seed" for p in SFX[n].params)}
    assert with_seed == {"whoosh", "boom", "key", "hat", "typing", "riser"}
    assert [p.name for p in SFX["typing"].params] == ["rate", "seed"]
    assert [p.name for p in SFX["pop"].params] == ["freq"]
    for name in set(SFX) - with_seed - {"pop"}:
        assert SFX[name].params == (), name


def test_sfx_synth_the_functions_take_no_parameter_they_do_not_have() -> None:
    with pytest.raises(TypeError):
        synth.kick(15360, SR, seed=1)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        synth.pop(5760, SR, seed=1)  # type: ignore[call-arg]


def test_sfx_synth_click_is_a_pop_at_1900_hz_times_08_and_powerup_carries_a_shimmer() -> None:
    assert np.array_equal(synth.click(2880, SR), synth.pop(2880, SR, freq=1900.0) * 0.8)
    up = synth.powerup(26400, SR)
    assert up.shape == (26400,)
    ramp = up - synth.shimmer(26400, SR) * 0.8  # what is left is the sweep, with no shimmer
    assert float(np.abs(ramp).max()) <= 0.28 + 1e-4


def test_sfx_synth_the_first_key_of_typing_is_key_0_scaled_by_the_chance_of_the_rhythm() -> None:
    """`typing` uses `default_rng(seed)` for the rhythm and `key(2400, sr, seed=k)` for key `k`."""
    n, seed = 25 * SPF, 55
    typed = synth.typing(n, SR, seed=seed)
    strength = 0.7 + 0.3 * np.random.default_rng(seed).random()
    first = synth.key(2400, SR, seed=0) * strength
    assert np.allclose(typed[:2400], first, atol=1e-6)  # a second key starts later than sample 0


def test_sfx_synth_typing_a_faster_rate_has_more_keys() -> None:
    n = 25 * SPF
    slow, fast = synth.typing(n, SR, rate=4.0), synth.typing(n, SR, rate=25.0)
    assert float(np.abs(fast).sum()) > 2 * float(np.abs(slow).sum())


def test_sfx_synth_a_duration_that_is_one_frame_is_still_exact() -> None:
    for name in ("whoosh", "shimmer", "pad", "typing", "riser"):
        y = SFX[name].fn(SPF, SR)
        assert y.shape == (SPF,) and bool(np.isfinite(y).all()), name


def _one_pole(x: np.ndarray, hz: float) -> np.ndarray:
    """The low pass of the pilot for a cutoff that does not change, by `scipy` and not a loop."""
    alpha = 1.0 - np.exp(-2 * np.pi * hz / SR)
    return lfilter([alpha], [1.0, alpha - 1.0], x)


@pytest.mark.parametrize("seed", [0, 3])
def test_sfx_synth_key_is_the_formula_of_the_pilot_with_the_rng_of_100_plus_seed(
    seed: int,
) -> None:
    n = 2400
    t = np.arange(n) / SR
    noise = np.random.default_rng(100 + seed).standard_normal(n)
    thump = np.sin(2 * np.pi * 180 * t) * np.exp(-t * 90) * 0.25
    expected = (noise - _one_pole(noise, 2500.0)) * np.exp(-t * 140) * 0.5 + thump
    assert np.allclose(synth.key(n, SR, seed=seed), expected, atol=1e-4)


@pytest.mark.parametrize("seed", [0, 3])
def test_sfx_synth_hat_is_the_formula_of_the_pilot_with_the_rng_of_300_plus_seed(
    seed: int,
) -> None:
    n = 2160
    t = np.arange(n) / SR
    noise = np.random.default_rng(300 + seed).standard_normal(n)
    expected = (noise - _one_pole(noise, 7000.0)) * np.exp(-t * 110) * 0.32
    assert np.allclose(synth.hat(n, SR, seed=seed), expected, atol=1e-4)
