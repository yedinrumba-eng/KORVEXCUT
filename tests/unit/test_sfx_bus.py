"""The bus of sound effects (spec S1.8a row 2, 001.15): an event at frame `f` starts at sample
`f * 1600` (30 fps) when it is aligned to the `start`, at `f * 1600 - n // 2` at the `center` and at
`f * 1600 - (n - 1)` at the `end`; what falls outside `[0, total)` is cut; the sum is float32 and is
**not** normalized (lesson 10: the level is `gain`, `bus_gain_db` and the windows).
"""

from typing import Literal

import numpy as np
import pytest

from kcut.audio.sfx_bus import build_sfx_bus
from kcut.audio.sfx_events import SfxEvent
from kcut.audio.sfx_library import SFX
from kcut.errors import InternalError

SR = 48000
SPF = 1600
FRAMES = 345
TOTAL = FRAMES * SPF


def _event(
    kind: str,
    at_f: int,
    align: Literal["start", "center", "end"] = "start",
    dur_f: int | None = None,
    gain: float | None = None,
    **params: float,
) -> SfxEvent:
    seed, freq, rate = (params.get(name) for name in ("seed", "freq", "rate"))
    default = SFX[kind].default_gain
    gain = default if gain is None else gain
    return SfxEvent(kind, at_f, align, dur_f, gain, seed, freq, rate)


def _sound(event: SfxEvent) -> np.ndarray:
    """What the event is, alone and whole: `fn(n, sr, **params) * gain`."""
    sfx = SFX[event.type]
    n = sfx.fixed_n if sfx.fixed_n is not None else (event.dur_f or 0) * SPF
    named = {"seed": event.seed, "freq": event.freq, "rate": event.rate}
    params = {k: v for k, v in named.items() if v is not None}
    return sfx.fn(n, SR, **params) * event.gain


def _only_there(bus: np.ndarray, first: int, n: int) -> bool:
    """Everything outside `[first, first + n)` is silence."""
    return not bus[:first].any() and not bus[first + n :].any()


@pytest.mark.parametrize("frame", [0, 1, 10, 100, 200, 300])
def test_sfx_bus_start_begins_at_the_sample_of_the_frame(frame: int) -> None:
    event = _event("kick", frame)
    sound = _sound(event)
    bus = build_sfx_bus([event], TOTAL, SPF, SR)
    first, n = frame * 1600, SFX["kick"].fixed_n
    assert n == 15360 and bus.shape == (TOTAL,) and bus.dtype == np.float32
    assert np.array_equal(bus[first : first + n], sound)
    assert _only_there(bus, first, n)


@pytest.mark.parametrize("frame", [20, 100, 250])
def test_sfx_bus_center_puts_the_middle_sample_at_the_frame(frame: int) -> None:
    event = _event("boom", frame, "center")
    sound = _sound(event)
    n = len(sound)
    bus = build_sfx_bus([event], TOTAL, SPF, SR)
    first = frame * 1600 - n // 2
    assert np.array_equal(bus[first : first + n], sound)
    assert _only_there(bus, first, n)
    assert bus[frame * 1600] == sound[n // 2]


@pytest.mark.parametrize("frame", [30, 100, 250])
def test_sfx_bus_end_puts_the_last_sample_at_the_frame(frame: int) -> None:
    event = _event("riser", frame, "end", dur_f=15)
    sound = _sound(event)
    n = len(sound)
    assert n == 15 * 1600
    bus = build_sfx_bus([event], TOTAL, SPF, SR)
    first = frame * 1600 - (n - 1)
    assert np.array_equal(bus[first : first + n], sound)
    assert _only_there(bus, first, n)
    assert bus[frame * 1600] == sound[-1]


def test_sfx_bus_what_falls_before_sample_0_or_after_the_end_is_cut() -> None:
    center = _event("boom", 0, "center")  # half of it is before 0
    sound = _sound(center)
    n = len(sound)
    bus = build_sfx_bus([center], TOTAL, SPF, SR)
    assert np.array_equal(bus[: n - n // 2], sound[n // 2 :])
    assert not bus[n - n // 2 :].any()
    late = _event("boom", FRAMES - 1)  # 27 frames long, with 1 left
    bus = build_sfx_bus([late], TOTAL, SPF, SR)
    assert bus.shape == (TOTAL,)
    assert np.array_equal(bus[(FRAMES - 1) * 1600 :], _sound(late)[:1600])
    early_end = _event("kick", 3, "end")  # ends at frame 3, begins before 0
    bus = build_sfx_bus([early_end], TOTAL, SPF, SR)
    sound = _sound(early_end)
    last = 3 * 1600
    assert np.array_equal(bus[: last + 1], sound[len(sound) - last - 1 :])


def test_sfx_bus_a_sound_completely_outside_adds_nothing_and_does_not_fail() -> None:
    far = _event("kick", FRAMES + 50)
    before = _event("kick", 0, "end", gain=0.0)
    bus = build_sfx_bus([far, before], TOTAL, SPF, SR)
    assert bus.shape == (TOTAL,) and not bus.any()


def test_sfx_bus_the_sum_is_not_normalized() -> None:
    """Two sounds on the same samples add up as they are, and a loud one stays loud (lesson 10)."""
    a, b = _event("boom", 10, gain=2.0), _event("kick", 10)
    bus = build_sfx_bus([a, b], TOTAL, SPF, SR)
    first = 10 * 1600
    both = np.zeros(TOTAL, dtype=np.float32)
    both[first : first + len(_sound(a))] += _sound(a)
    both[first : first + len(_sound(b))] += _sound(b)
    assert np.array_equal(bus, both)
    assert float(np.abs(bus).max()) > 1.0  # nothing brought it back down to 0.9 or to 1
    quiet = _event("pop", 5, gain=0.5)
    assert float(np.abs(build_sfx_bus([quiet], TOTAL, SPF, SR)).max()) == pytest.approx(
        float(np.abs(_sound(quiet)).max())
    )  # and a quiet one is not brought up


def test_sfx_bus_an_empty_plan_is_silence_of_the_length_of_the_video() -> None:
    bus = build_sfx_bus([], TOTAL, SPF, SR)
    assert bus.shape == (TOTAL,) and bus.dtype == np.float32 and not bus.any()


def test_sfx_bus_the_gain_scales_the_sound() -> None:
    quiet, loud = _event("hat", 40, gain=0.25), _event("hat", 40, gain=1.0)
    a = build_sfx_bus([quiet], TOTAL, SPF, SR)
    b = build_sfx_bus([loud], TOTAL, SPF, SR)
    assert np.allclose(a * 4, b, atol=1e-7)
    assert float(np.abs(b).max()) > 0


def test_sfx_bus_the_seed_freq_and_rate_of_the_event_reach_the_function() -> None:
    typed = _event("typing", 20, dur_f=25, rate=8.0, seed=3)
    bus = build_sfx_bus([typed], TOTAL, SPF, SR)
    direct = SFX["typing"].fn(25 * SPF, SR, rate=8.0, seed=3) * typed.gain
    assert np.array_equal(bus[20 * 1600 : 20 * 1600 + 25 * SPF], direct)
    popped = _event("pop", 20, freq=700.0)
    bus = build_sfx_bus([popped], TOTAL, SPF, SR)
    assert np.array_equal(
        bus[20 * 1600 : 20 * 1600 + 5760], SFX["pop"].fn(5760, SR, freq=700.0) * 0.6
    )


def test_sfx_bus_seed_default_an_event_with_no_seed_is_the_default_seed() -> None:
    """Row 5, through the bus: a `boom`, a `typing` and a `riser` with no seed are the sound of
    their default seed (7, 55, 77), and with another seed they are another sound."""
    for kind, seed, dur in (("boom", 7, None), ("typing", 55, 20), ("riser", 77, 15)):
        plain = build_sfx_bus([_event(kind, 30, dur_f=dur)], TOTAL, SPF, SR)
        named = build_sfx_bus([_event(kind, 30, dur_f=dur, seed=seed)], TOTAL, SPF, SR)
        other = build_sfx_bus([_event(kind, 30, dur_f=dur, seed=seed + 1)], TOTAL, SPF, SR)
        assert plain.tobytes() == named.tobytes() and plain.tobytes() != other.tobytes(), kind


def test_sfx_bus_a_type_that_needs_a_duration_and_has_none_is_an_internal_error() -> None:
    with pytest.raises(InternalError, match="dur_f"):
        build_sfx_bus([_event("pad", 10)], TOTAL, SPF, SR)


def test_sfx_bus_works_at_other_frame_rates() -> None:
    """`spf` is what a frame is worth in samples: at 60 fps frame 10 is sample 8000."""
    event = _event("click", 10)
    bus = build_sfx_bus([event], 120 * 800, 800, SR)
    assert np.array_equal(bus[8000 : 8000 + 2880], _sound(event))
    assert not bus[:8000].any()
