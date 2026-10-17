"""`kcut ingest` edge cases on small synthetic projects: flags, renames, failures, extra classes.

Most cases pass `--no-proxy` (see `_ingest`): the proxies have their own tests and cost ~7 s.
"""

import json
import math
import shutil
from pathlib import Path

import pytest

from kcut import cli
from kcut.audio.wavio import write_wav_s16_mono
from kcut.errors import ToolError
from kcut.ingest import sync as sync_module
from kcut.ingest import sync_stage, workfiles
from kcut.ingest.sync_reasons import ambiguity_message
from tests.conftest import run_kcut
from tests.fixtures.synth_media import MediaTruth
from tests.integration.ingest_helpers import edit_toml, ingest, inventory
from tests.unit.sync_signals import SR, speechlike, world

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]

Synth = tuple[Path, MediaTruth]


class TestFlags:
    def test_no_proxy_skips_proxies_but_keeps_audio(self, two_cameras: Path) -> None:
        assert ingest(two_cameras)[0] == 0
        assert not list((two_cameras / ".kcut" / "proxy").glob("*.mp4"))
        assert len(list((two_cameras / ".kcut" / "wav16").glob("*.wav"))) == 2
        a1 = inventory(two_cameras).by_id("a1")
        assert a1 is not None and a1.work is not None
        assert a1.work.proxy is None
        assert (a1.work.proxy_w, a1.work.proxy_h) == (540, 960)
        assert a1.work.wav16 == ".kcut/wav16/a1_cam-a.wav"
        assert inventory(two_cameras).sync.members[0].id == "a2"

    def test_a_later_full_ingest_adds_the_proxies_and_keeps_the_audio(
        self, two_cameras: Path
    ) -> None:
        ingest(two_cameras)
        wav = two_cameras / ".kcut" / "wav16" / "a1_cam-a.wav"
        stamp = wav.stat().st_mtime_ns
        assert ingest(two_cameras, proxies=True)[0] == 0
        assert len(list((two_cameras / ".kcut" / "proxy").glob("*.mp4"))) == 2
        assert wav.stat().st_mtime_ns == stamp

    def test_a_proxy_already_built_is_kept_by_no_proxy(self, two_cameras: Path) -> None:
        ingest(two_cameras, proxies=True)
        assert ingest(two_cameras)[0] == 0
        a1 = inventory(two_cameras).by_id("a1")
        assert a1 is not None and a1.work is not None
        assert a1.work.proxy == ".kcut/proxy/a1_cam-a.mp4"

    def test_a_stale_sidecar_regenerates_the_work_file(self, two_cameras: Path) -> None:
        ingest(two_cameras, proxies=True)
        proxy = two_cameras / ".kcut" / "proxy" / "a1_cam-a.mp4"
        sidecar = workfiles.sidecar_path(proxy)
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        data["params"]["crf"] = 99
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        stamp = proxy.stat().st_mtime_ns
        assert ingest(two_cameras, proxies=True)[0] == 0
        assert proxy.stat().st_mtime_ns != stamp
        assert json.loads(sidecar.read_text(encoding="utf-8"))["params"]["crf"] == 23


class TestRenameAndNewFiles:
    def test_a_renamed_file_keeps_its_id_and_moves_its_wav(self, two_cameras: Path) -> None:
        ingest(two_cameras)
        shutil.move(two_cameras / "crudo" / "cam b.mov", two_cameras / "crudo" / "zeta nueva.mov")
        assert ingest(two_cameras)[0] == 0
        inv = inventory(two_cameras)
        assert {c.file: c.id for c in inv.clips} == {
            "crudo/cam a.mp4": "a1",
            "crudo/zeta nueva.mov": "a2",
        }
        a2 = inv.by_id("a2")
        assert a2 is not None and a2.work is not None
        assert a2.work.wav16 == ".kcut/wav16/a2_zeta-nueva.wav"
        assert (two_cameras / a2.work.wav16).is_file()
        assert not (two_cameras / ".kcut" / "wav16" / "a2_cam-b.wav").exists()
        assert inv.sync.members[0].id == "a2"

    def test_a_new_file_gets_the_next_number(self, two_cameras: Path, synth_project: Synth) -> None:
        ingest(two_cameras)
        shutil.copy2(
            synth_project[0] / "crudo" / "pantalla.mp4", two_cameras / "crudo" / "otra pantalla.mp4"
        )
        assert ingest(two_cameras)[0] == 0
        ids = {c.file: c.id for c in inventory(two_cameras).clips}
        assert ids["crudo/otra pantalla.mp4"] == "b1"
        assert ids["crudo/cam a.mp4"] == "a1"
        assert ids["crudo/cam b.mov"] == "a2"

    def test_an_identical_copy_gets_its_own_id_and_its_own_wav(self, two_cameras: Path) -> None:
        ingest(two_cameras)
        (two_cameras / "crudo" / "cam b.mov").unlink()
        shutil.copy2(two_cameras / "crudo" / "cam a.mp4", two_cameras / "crudo" / "cam b.mov")
        assert ingest(two_cameras)[0] == 0
        inv = inventory(two_cameras)
        assert {c.file: c.id for c in inv.clips} == {
            "crudo/cam a.mp4": "a1",
            "crudo/cam b.mov": "a3",
        }
        wavs = {c.id: c.work.wav16 for c in inv.clips if c.work is not None}
        assert wavs == {"a1": ".kcut/wav16/a1_cam-a.wav", "a3": ".kcut/wav16/a3_cam-b.wav"}
        assert all((two_cameras / rel).is_file() for rel in wavs.values() if rel is not None)
        assert not list((two_cameras / ".kcut" / "wav16").glob("stage-*"))
        member = inv.sync.members[0]
        assert (member.id, abs(member.offset_ms) <= 1) == ("a3", True)


class TestSyncOptions:
    def test_master_from_the_config_flips_the_sign(self, two_cameras: Path) -> None:
        edit_toml(two_cameras, 'master = ""', 'master = "a2"')
        assert ingest(two_cameras)[0] == 0
        sync = inventory(two_cameras).sync
        assert (sync.master, sync.members[0].id) == ("a2", "a1")
        assert -1201 <= sync.members[0].offset_ms <= -1199

    def test_unknown_master_is_a_project_error(self, two_cameras: Path) -> None:
        edit_toml(two_cameras, 'master = ""', 'master = "a9"')
        code, doc = ingest(two_cameras)
        assert code == 3
        assert "a9" in str(doc["error"])

    def test_manual_offsets_are_used_as_given(self, two_cameras: Path) -> None:
        edit_toml(two_cameras, "[sync.manual]", "[sync.manual]\na2 = 777")
        assert ingest(two_cameras)[0] == 0
        (member,) = inventory(two_cameras).sync.members
        assert (member.id, member.offset_ms, member.method) == ("a2", 777, "manual")

    def test_a_previous_result_is_reused_unless_resync(
        self, two_cameras: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert ingest(two_cameras)[0] == 0
        calls: list[int] = []

        def boom(*_args: object, **_kwargs: object) -> object:
            calls.append(1)
            raise ToolError("no se debia recalcular")

        monkeypatch.setattr(sync_stage, "sync_pair", boom)
        argv = ["ingest", "--project", str(two_cameras), "--json", "--no-proxy"]
        assert cli.main(argv) == 0
        assert calls == []
        assert cli.main([*argv, "--resync"]) == 4
        assert calls == [1]

    def test_a_manual_entry_overrides_a_stored_result(self, two_cameras: Path) -> None:
        ingest(two_cameras)
        edit_toml(two_cameras, "[sync.manual]", "[sync.manual]\na2 = 500")
        assert ingest(two_cameras)[0] == 0
        assert inventory(two_cameras).sync.members[0].offset_ms == 500
        edit_toml(two_cameras, "a2 = 500\n", "")
        assert ingest(two_cameras)[0] == 0
        member = inventory(two_cameras).sync.members[0]
        assert (member.method, 1199 <= member.offset_ms <= 1201) == ("envelope+raw", True)


class TestWeakRefine:
    """`min_refine_corr` through the whole command: the inventory, the warnings, reuse."""

    @pytest.fixture
    def shifted_pair(self, blank: Path) -> Path:
        """Two 12 s speech-like recordings, the second starting 5 s after the first (S1.2-29)."""
        scene = speechlike(40, 11)
        write_wav_s16_mono(blank / "crudo" / "a.wav", scene[5 * SR : 17 * SR], SR)
        write_wav_s16_mono(blank / "crudo" / "b.wav", scene[10 * SR : 22 * SR], SR)
        toml = blank / "kcut.toml"
        toml.write_text(toml.read_text(encoding="utf-8").replace('master = ""', 'master = "s1"'))
        return blank

    def test_a_weak_refine_is_rejected_and_recorded(self, shifted_pair: Path) -> None:
        code, doc = ingest(shifted_pair)
        assert code == 0
        inv = inventory(shifted_pair)
        assert inv.sync.master == "s1" and inv.sync.members == ()
        (rejected,) = inv.sync.rejected
        assert rejected.id == "s2"
        assert rejected.refine_corr is not None and rejected.refine_corr < 0.1
        assert rejected.reason.startswith("sync_weak_refine")
        clip = inv.by_id("s2")
        assert clip is not None and clip.warnings == ("sync_rejected", "sync_weak_refine")
        assert {"id": "s2", "code": "sync_weak_refine"} in doc["warnings"]  # type: ignore[operator]

    def test_the_threshold_can_be_lowered_in_the_config(
        self, shifted_pair: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sync_module, "AMBIGUITY_LAG_MS", math.inf)  # 001.7: 2nd net off too
        toml = shifted_pair / "kcut.toml"
        text = toml.read_text(encoding="utf-8")
        toml.write_text(text.replace("min_refine_corr = 0.1", "min_refine_corr = 0.0"))
        argv = ["ingest", "--project", str(shifted_pair), "--json", "--no-proxy"]
        assert cli.main(argv) == 0  # in-process: the patched constant has to be the one in use
        (member,) = inventory(shifted_pair).sync.members
        assert member.id == "s2" and abs(member.offset_ms - 5000) > 2  # accepted and wrong

    def test_accepted_pairs_record_their_refine_correlation(self, two_cameras: Path) -> None:
        assert ingest(two_cameras)[0] == 0
        (member,) = inventory(two_cameras).sync.members
        assert member.refine_corr is not None and member.refine_corr > 0.9

    def test_an_old_accepted_result_without_refine_corr_is_measured_again(
        self, two_cameras: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert ingest(two_cameras)[0] == 0
        path = two_cameras / ".kcut" / "inventory.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["sync"]["members"][0]["refine_corr"]
        path.write_text(json.dumps(data), encoding="utf-8")
        calls: list[int] = []
        real = sync_stage.sync_pair

        def counting(*args: object, **kwargs: object) -> object:
            calls.append(1)
            return real(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(sync_stage, "sync_pair", counting)
        assert cli.main(["ingest", "--project", str(two_cameras), "--json", "--no-proxy"]) == 0
        assert calls == [1]
        (member,) = inventory(two_cameras).sync.members
        assert member.refine_corr is not None

    def test_a_raised_threshold_re_evaluates_a_stored_result(
        self, two_cameras: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert ingest(two_cameras)[0] == 0
        toml = two_cameras / "kcut.toml"
        text = toml.read_text(encoding="utf-8")
        toml.write_text(text.replace("min_refine_corr = 0.1", "min_refine_corr = 1.0"))
        calls: list[int] = []
        real = sync_stage.sync_pair
        monkeypatch.setattr(
            sync_stage, "sync_pair", lambda *a, **k: calls.append(1) or real(*a, **k)
        )
        assert cli.main(["ingest", "--project", str(two_cameras), "--json", "--no-proxy"]) == 0
        assert calls == [1]


class TestAmbiguous:
    """Periodic audio, 12 s clips, B 4 s later: the wrong lag used to be accepted (001.7)."""

    @pytest.fixture
    def tones_pair(self, blank: Path) -> Path:
        write_wav_s16_mono(blank / "crudo" / "a.wav", world(0.0), SR)
        write_wav_s16_mono(blank / "crudo" / "b.wav", world(4.0), SR)
        toml = blank / "kcut.toml"
        toml.write_text(toml.read_text(encoding="utf-8").replace('master = ""', 'master = "s1"'))
        return blank

    def test_an_ambiguous_pair_is_rejected_with_its_lags_and_a_message(
        self, tones_pair: Path
    ) -> None:
        code, doc = ingest(tones_pair)
        assert code == 0
        inv = inventory(tones_pair)
        assert inv.sync.members == ()
        (rejected,) = inv.sync.rejected
        assert rejected.id == "s2" and rejected.reason.startswith("sync_ambiguous")
        assert rejected.lag_a_ms is not None and abs(rejected.lag_a_ms + 2800) <= 10
        assert rejected.lag_b_ms is not None and abs(rejected.lag_b_ms - 4000) <= 10
        clip = inv.by_id("s2")
        assert clip is not None and clip.warnings == ("sync_rejected", "sync_ambiguous")
        message = ambiguity_message(rejected.lag_a_ms, rejected.lag_b_ms)
        assert message.startswith("sincronía ambigua: clip corto con dos desfases posibles (")
        assert {"id": "s2", "code": "sync_ambiguous", "message_es": message} in doc["warnings"]  # type: ignore[operator]

    def test_the_human_output_says_the_two_lags(self, tones_pair: Path) -> None:
        result = run_kcut("ingest", "--project", str(tones_pair), "--no-proxy")
        assert result.returncode == 0, result.stderr
        (rejected,) = inventory(tones_pair).sync.rejected
        assert rejected.lag_a_ms is not None and rejected.lag_b_ms is not None
        message = ambiguity_message(rejected.lag_a_ms, rejected.lag_b_ms)
        assert f"[AVISO] s2: sin sincronía - {message}" in result.stdout
        assert message.endswith("; revísalo a mano")
