"""The overlap floor of the sync score (spec 001.5) and the acceptance of the spec's camera B."""

import math
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.audio.wavio import write_wav_s16_mono
from kcut.config.load import parse_config
from kcut.config.model import SyncSection
from kcut.ingest import sync as sync_module
from kcut.ingest.sync import HOP_MS, coarse_offset, envelope, sync_arrays, sync_pair
from tests.unit.sync_signals import SR, Audio, speechlike, world


def test_the_floor_is_three_quarters_of_the_shorter_clip() -> None:
    assert sync_module.MIN_OVERLAP_FRACTION == 0.75


def test_a_match_below_the_floor_is_ignored_and_one_above_it_counts() -> None:
    # two 12 s envelopes: the floor is 0.75 * 12 s = 9 s = 1800 samples of 5 ms
    rng = np.random.default_rng(3)
    master = rng.standard_normal(2400).astype(np.float32)
    below = rng.standard_normal(2400).astype(np.float32)
    below[:1700] = master[-1700:]  # 8.5 s of perfect overlap: under the floor
    assert coarse_offset(master, below, HOP_MS).score < 0.5
    above = rng.standard_normal(2400).astype(np.float32)
    above[:1900] = master[-1900:]  # 9.5 s of perfect overlap: counts
    found = coarse_offset(master, above, HOP_MS)
    assert found.score > 0.9
    assert found.offset_ms == (2400 - 1900) * HOP_MS


def test_the_floor_never_exceeds_ten_seconds() -> None:
    rng = np.random.default_rng(4)
    master = rng.standard_normal(24000).astype(np.float32)  # 120 s
    member = rng.standard_normal(24000).astype(np.float32)
    member[:2100] = master[-2100:]  # 10.5 s of overlap: above the 10 s cap, so it counts
    found = coarse_offset(master, member, HOP_MS)
    assert found.score > 0.9
    assert found.offset_ms == (24000 - 2100) * HOP_MS


def test_the_spec_camera_b_is_accepted_with_a_ratio_above_the_minimum(tmp_path: Path) -> None:
    """Camera B starts 1.2 s after camera A, hears the same tones plus a little noise."""
    master, member = world(0.0), world(1.2, noise=0.017)
    coarse = coarse_offset(envelope(master, SR), envelope(member, SR), HOP_MS)
    assert coarse.offset_ms == 1200
    assert coarse.ratio >= 1.5

    write_wav_s16_mono(tmp_path / "a.wav", master, SR)
    write_wav_s16_mono(tmp_path / "b.wav", member, SR)
    cfg = parse_config("", default_name="x").sync
    result = sync_pair(tmp_path / "a.wav", tmp_path / "b.wav", cfg)
    assert result.accepted, result.reason
    assert abs(result.offset_ms - 1200) <= 1
    assert result.score >= cfg.min_score
    assert result.ratio >= cfg.min_ratio


def test_with_the_old_half_floor_camera_b_would_be_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Documents why 001.5 exists: at 0.5 the secondary peak at a small overlap wins."""
    master, member = world(0.0), world(1.2, noise=0.017)
    monkeypatch.setattr(sync_module, "MIN_OVERLAP_FRACTION", 0.5)
    half = coarse_offset(envelope(master, SR), envelope(member, SR), HOP_MS)
    monkeypatch.setattr(sync_module, "MIN_OVERLAP_FRACTION", 0.75)
    three_quarters = coarse_offset(envelope(master, SR), envelope(member, SR), HOP_MS)
    assert half.ratio < 1.5 <= three_quarters.ratio


def _env(x: Audio) -> NDArray[np.float32]:
    return envelope(x, SR)


class TestOverlapNormalization:
    def test_a_partial_overlap_scores_about_as_high_as_a_full_one(self) -> None:
        scene = speechlike(200, 7)
        full = coarse_offset(_env(scene[: 60 * SR]), _env(scene[: 60 * SR]), HOP_MS)
        partial = coarse_offset(_env(scene[: 120 * SR]), _env(scene[75 * SR : 195 * SR]), HOP_MS)
        assert full.score > 0.95
        assert partial.score > 0.8
        assert abs(partial.offset_ms - 75000) <= HOP_MS

    def test_a_tiny_matching_overlap_is_ignored_for_short_clips(self) -> None:
        # 12 s of envelope each; the last second of one equals the first second of the other.
        # Normalized by its own 1 s overlap that match would be perfect, so it must not count.
        rng = np.random.default_rng(1)
        master = rng.standard_normal(2400).astype(np.float32)
        member = rng.standard_normal(2400).astype(np.float32)
        member[:200] = master[-200:]
        result = coarse_offset(master, member, HOP_MS)
        assert result.score < 0.5

    def test_the_floor_is_10_seconds_for_long_clips(self) -> None:
        rng = np.random.default_rng(2)
        master = rng.standard_normal(24000).astype(np.float32)  # 120 s
        short_match = rng.standard_normal(24000).astype(np.float32)
        short_match[:1500] = master[-1500:]  # 7.5 s of overlap: below the 10 s floor
        assert coarse_offset(master, short_match, HOP_MS).score < 0.5
        long_match = rng.standard_normal(24000).astype(np.float32)
        long_match[:2400] = master[-2400:]  # 12 s of overlap: counts
        found = coarse_offset(master, long_match, HOP_MS)
        assert found.score > 0.9
        assert found.offset_ms == (24000 - 2400) * HOP_MS

    def test_scores_can_slightly_exceed_one_and_that_is_fine(self) -> None:
        env = _env(speechlike(30, 4))
        assert coarse_offset(env, env, HOP_MS).score >= 0.99


def _cfg() -> SyncSection:
    return parse_config("", default_name="x").sync


@pytest.mark.parametrize(("shift", "lags"), [(4.0, (-2800, 4000)), (6.0, (-800, 6000))])
def test_ambiguous_tones_12s_are_rejected_with_their_two_lags(
    shift: float, lags: tuple[int, int]
) -> None:
    """Periodic audio, 12 s, B starting 4 s / 6 s later: the wrong lag used to be accepted (-2800
    / -800, refine 0.85). Now both candidate lags are kept and the pair is rejected (001.7)."""
    result = sync_arrays(world(0.0), world(shift), SR, _cfg())
    assert not result.accepted
    assert result.reason is not None and result.reason.startswith("sync_ambiguous")
    assert result.lag_a_ms is not None and result.lag_b_ms is not None
    assert abs(result.lag_a_ms - lags[0]) <= 10  # the best lag at the 0.75 floor (the wrong one)
    assert abs(result.lag_b_ms - lags[1]) <= 10  # at the 0.5 floor: the real offset
    assert abs(result.lag_b_ms - shift * 1000) <= 10
    assert result.refine_corr is not None and result.refine_corr > 0.8  # why it used to pass


def test_ambiguous_check_runs_after_the_weak_refine_check() -> None:
    """The verifier's 12 s pair (B +5 s) is still rejected for its weak refine, not as ambiguous."""
    scene = speechlike(40, 11)
    result = sync_arrays(scene[5 * SR : 17 * SR], scene[10 * SR : 22 * SR], SR, _cfg())
    assert result.reason is not None and result.reason.startswith("sync_weak_refine")
    assert (result.lag_a_ms, result.lag_b_ms) == (None, None)


@pytest.mark.parametrize(
    ("seconds", "computed"), [(12.0, True), (13.3, True), (13.4, False), (14.0, False)]
)
def test_ambiguous_second_lag_is_only_computed_when_the_fraction_sets_the_floor(
    seconds: float, computed: bool
) -> None:
    clip = speechlike(seconds, 3)
    found = coarse_offset(envelope(clip, SR), envelope(clip, SR), HOP_MS)
    assert (found.loose_offset_ms is not None) is computed


def test_ambiguous_threshold_and_floor_are_named_constants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (sync_module.AMBIGUITY_FLOOR_FRACTION, sync_module.AMBIGUITY_LAG_MS) == (0.5, 2000)
    monkeypatch.setattr(sync_module, "AMBIGUITY_LAG_MS", math.inf)
    assert sync_arrays(world(0.0), world(4.0), SR, _cfg()).accepted  # the check is what rejects
