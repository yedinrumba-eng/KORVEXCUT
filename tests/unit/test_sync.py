"""Camera sync on synthetic speech-like signals: offsets of both signs, rejection, drift."""

import dataclasses
import math
from pathlib import Path

import numpy as np
import pytest

from kcut.audio.wavio import write_wav_s16_mono
from kcut.config.load import parse_config
from kcut.config.model import SyncSection
from kcut.errors import ProjectError
from kcut.ingest import sync as sync_module
from kcut.ingest.sync import (
    HOP_MS,
    coarse_offset,
    drift,
    envelope,
    refine_offset,
    sync_arrays,
    sync_pair,
)
from kcut.ingest.sync_reasons import rejection_motive
from tests.unit.sync_signals import SR, Audio, speechlike, world


def _cfg(**changes: object) -> SyncSection:
    base = parse_config("", default_name="x").sync
    return dataclasses.replace(base, **changes)


def _pair(offset_samples: int, seed: int = 1) -> tuple[Audio, Audio]:
    """Master and member cut from one scene; member t=0 falls at master t=offset_samples."""
    scene = speechlike(60, seed)
    pad = SR * 5
    master = scene[pad : pad + 30 * SR]
    member = scene[pad + offset_samples : pad + offset_samples + 30 * SR]
    return master, member


class TestEnvelope:
    def test_one_value_per_5_ms_and_z_normalized(self) -> None:
        env = envelope(speechlike(10, 1), SR)
        assert len(env) == 10 * 1000 // HOP_MS
        assert env.dtype == np.float32
        assert abs(float(env.mean())) < 1e-4
        assert abs(float(env.std()) - 1.0) < 1e-3

    def test_flat_signal_is_all_zeros(self) -> None:
        env = envelope(np.full(SR, 0.3, dtype=np.float32), SR)
        assert np.allclose(env, 0.0, atol=1e-6)

    def test_shorter_than_one_block_is_empty(self) -> None:
        assert len(envelope(np.zeros(10, dtype=np.float32), SR)) == 0

    def test_louder_means_higher(self) -> None:
        x = np.concatenate([np.zeros(SR // 2), np.full(SR // 2, 0.5)]).astype(np.float32)
        env = envelope(x, SR)
        assert env[:50].max() < env[-50:].min()


class TestCoarse:
    def test_recovers_a_known_lag_in_5_ms_steps(self) -> None:
        master, member = _pair(SR * 2)  # 2.000 s
        result = coarse_offset(envelope(master, SR), envelope(member, SR), HOP_MS)
        assert abs(result.offset_ms - 2000) <= HOP_MS
        assert result.score > 0.35
        assert result.ratio > 1.5

    def test_negative_lag(self) -> None:
        master, member = _pair(-SR * 3)
        result = coarse_offset(envelope(master, SR), envelope(member, SR), HOP_MS)
        assert abs(result.offset_ms + 3000) <= HOP_MS

    def test_unrelated_signals_have_a_low_peak(self) -> None:
        a, b = speechlike(30, 1), speechlike(30, 2)
        result = coarse_offset(envelope(a, SR), envelope(b, SR), HOP_MS)
        assert result.score < 0.35 or result.ratio < 1.5

    def test_ratio_is_infinite_when_there_is_no_second_peak(self) -> None:
        env = np.array([1.0, -1.0, 1.0], dtype=np.float32)
        result = coarse_offset(env, env, HOP_MS)
        assert math.isinf(result.ratio)
        assert result.second == 0.0

    def test_empty_envelopes_do_not_crash(self) -> None:
        empty = np.zeros(0, dtype=np.float32)
        assert coarse_offset(empty, empty, HOP_MS).score == 0.0


class TestRefine:
    @pytest.mark.parametrize("true_samples", [75557, -32011, 0, 1])
    def test_recovers_the_offset_to_a_quarter_millisecond(self, true_samples: int) -> None:
        master, member = _pair(true_samples)
        true_ms = true_samples * 1000 / SR
        offset, corr = refine_offset(master, member, SR, true_ms + 3.0)  # coarse was 3 ms off
        assert abs(offset - true_ms) <= 0.26
        assert corr > 0.99

    def test_no_overlap_returns_the_coarse_value(self) -> None:
        master = speechlike(1, 1)
        member = speechlike(1, 2)
        assert refine_offset(master, member, SR, 5000.0) == (5000.0, 0.0)


class TestDrift:
    def test_none_below_30_seconds_of_overlap(self) -> None:
        master, member = _pair(0)
        short = member[: 20 * SR]
        assert drift(master, short, SR, 0.0).drift_ms is None
        assert drift(master, short, SR, 0.0).windows == 0

    def test_same_clock_gives_zero(self) -> None:
        scene = speechlike(100, 5)
        result = drift(scene[: 90 * SR], scene[SR : 91 * SR], SR, 1000.0)
        assert result.drift_ms is not None
        assert result.drift_ms <= 1
        assert result.windows >= 7

    def test_a_clock_that_runs_fast_is_measured(self) -> None:
        scene = speechlike(130, 3)
        master = scene[: 120 * SR]
        positions = np.arange(110 * SR) * 1.0001 + 0.0
        member = np.interp(positions, np.arange(len(scene)), scene).astype(np.float32)
        result = drift(master, member, SR, 0.0)
        assert result.drift_ms is not None
        assert 8 <= result.drift_ms <= 12  # 110 s * 0.0001 = 11 ms across the windows
        assert result.windows >= 8


def _write(tmp_path: Path, name: str, audio: Audio) -> Path:
    path = tmp_path / name
    write_wav_s16_mono(path, audio, SR)
    return path


class TestSyncPair:
    @pytest.mark.parametrize(
        ("true_samples", "expected_ms"), [(75557, 4722), (-32011, -2001), (19200, 1200)]
    )
    def test_accepts_and_gets_the_offset_within_1_ms(
        self, tmp_path: Path, true_samples: int, expected_ms: int
    ) -> None:
        master, member = _pair(true_samples)
        result = sync_pair(
            _write(tmp_path, "m.wav", master), _write(tmp_path, "b.wav", member), _cfg()
        )
        assert result.accepted
        assert abs(result.offset_ms - expected_ms) <= 1
        assert result.reason is None
        assert result.score >= 0.35
        assert result.ratio >= 1.5

    def test_rejects_unrelated_audio_with_a_reason(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.wav", speechlike(30, 1))
        b = _write(tmp_path, "b.wav", speechlike(30, 2))
        result = sync_pair(a, b, _cfg())
        assert not result.accepted
        assert result.reason in {
            "pico de correlacion bajo",
            "pico ambiguo (hay otro casi igual de alto)",
        }
        assert result.drift_ms is None

    def test_the_thresholds_come_from_the_config(self, tmp_path: Path) -> None:
        master, member = _pair(SR)
        noisy = (member + speechlike(30, 99)).astype(np.float32)  # score drops to about 0.6
        paths = _write(tmp_path, "m.wav", master), _write(tmp_path, "b.wav", noisy)
        assert sync_pair(*paths, _cfg()).accepted
        assert not sync_pair(*paths, _cfg(min_score=0.8)).accepted
        assert not sync_pair(*paths, _cfg(min_ratio=1000.0)).accepted

    @pytest.mark.slow
    def test_drift_over_the_limit_is_flagged_not_rejected(self, tmp_path: Path) -> None:
        scene = speechlike(130, 3)
        master = scene[: 120 * SR]
        positions = np.arange(110 * SR) * 1.0001
        member = np.interp(positions, np.arange(len(scene)), scene).astype(np.float32)
        paths = _write(tmp_path, "m.wav", master), _write(tmp_path, "b.wav", member)
        loose = sync_pair(*paths, _cfg(max_drift_ms=20))
        strict = sync_pair(*paths, _cfg(max_drift_ms=5))
        assert loose.accepted and strict.accepted
        assert loose.drift_warning is False
        assert strict.drift_warning is True
        assert strict.drift_ms is not None and strict.drift_ms > 5

    def test_different_sample_rates_are_an_error(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.wav", speechlike(5, 1))
        other = tmp_path / "b.wav"
        write_wav_s16_mono(other, speechlike(5, 2), 8000)
        with pytest.raises(ProjectError, match="muestreo"):
            sync_pair(a, other, _cfg())


def test_partial_overlap_75s_accepted(tmp_path: Path) -> None:
    """Two 120 s speech-like clips that overlap for only 45 s (spec 001.4, point 8)."""
    scene = speechlike(200, 7)
    master = scene[: 120 * SR]
    member = scene[75 * SR : 195 * SR]
    result = sync_pair(_write(tmp_path, "m.wav", master), _write(tmp_path, "b.wav", member), _cfg())
    assert result.accepted, result.reason
    assert abs(result.offset_ms - 75000) <= 1
    assert result.score >= 0.35
    assert result.ratio >= 1.5


def test_weak_refine_rejects_a_12s_pair_shifted_5s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verifier's case: 12 s clips, B starts 5 s later. A wrong lag wins the envelope test
    (score and ratio pass) but its raw-audio refinement barely correlates (0.012-0.019)."""
    scene = speechlike(40, 11)
    master = scene[5 * SR : 17 * SR]
    member = scene[10 * SR : 22 * SR]  # B starts 5000 ms after A
    paths = _write(tmp_path, "m.wav", master), _write(tmp_path, "b.wav", member)

    strict = sync_pair(*paths, _cfg())
    assert not strict.accepted
    assert strict.reason is not None and strict.reason.startswith("sync_weak_refine")
    assert strict.refine_corr is not None and strict.refine_corr < 0.1
    assert strict.score >= 0.35 and strict.ratio >= 1.5  # the envelope alone would have passed

    monkeypatch.setattr(sync_module, "AMBIGUITY_LAG_MS", math.inf)  # 001.7: the 2nd net off too
    lenient = sync_pair(*paths, _cfg(min_refine_corr=0.0))
    assert lenient.accepted
    assert abs(lenient.offset_ms - 5000) > 2  # accepted, and wrong: what the rule prevents


@pytest.mark.slow
def test_short_batch_never_accepts_a_wrong_offset() -> None:
    """Seeded batch of short clips (8-12 s) with offsets of 3-6 s: no wrong offset gets in."""
    rng = np.random.default_rng(2026)
    cfg, no_rule = _cfg(), _cfg(min_refine_corr=0.0)
    wrong_without_the_rule = 0
    for i in range(60):
        length, offset = int(rng.uniform(8, 12) * SR), int(rng.uniform(3, 6) * SR)
        scene = speechlike(30, 100 + i)
        master, member = scene[2 * SR :][:length], scene[2 * SR + offset :][:length]
        true_ms = offset * 1000 / SR
        result = sync_arrays(master, member, SR, cfg)
        assert not result.accepted or abs(result.offset_ms - true_ms) <= 2, f"pair {i}"
        loose = sync_arrays(master, member, SR, no_rule)
        wrong_without_the_rule += loose.accepted and abs(loose.offset_ms - true_ms) > 2
    assert wrong_without_the_rule >= 1  # the batch really contains the failure mode


def test_synth_cam_b_is_accepted_at_1200ms(tmp_path: Path) -> None:
    """The spec's camera B (tones, beeps, a little noise) still syncs after the new rule."""
    master, member = world(0.0), world(1.2, noise=0.017)
    result = sync_arrays(master, member, SR, _cfg())
    assert result.accepted, result.reason
    assert abs(result.offset_ms - 1200) <= 1
    assert result.refine_corr is not None and result.refine_corr > 0.9


def test_warning_from_reason_each_real_rejection_maps_to_its_motive() -> None:
    """The motive comes from the `reason` text that `sync_arrays` really writes (001.7, point 6)."""
    master, member = _pair(SR)
    expected = {
        "score": sync_arrays(master, member, SR, _cfg(min_score=2.0)),
        "ratio": sync_arrays(master, member, SR, _cfg(min_ratio=1000.0)),
        "weak_refine": sync_arrays(master, member, SR, _cfg(min_refine_corr=1.5)),
        "ambiguous": sync_arrays(world(0.0), world(4.0), SR, _cfg()),
    }
    for motive, result in expected.items():
        assert not result.accepted and result.reason is not None, motive
        assert rejection_motive(result.reason) == motive
