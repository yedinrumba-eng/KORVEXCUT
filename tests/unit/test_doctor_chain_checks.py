"""`tonemap_chain` and `soxr` doctor checks (S1.2), with ffmpeg simulated."""

from pathlib import Path

import pytest

from kcut import proc
from kcut.doctor import checks
from kcut.doctor.chain_checks import check_soxr, check_tonemap_chain
from kcut.errors import MissingDependency
from kcut.ff.color import HDR_TO_SDR
from tests.unit.doctor_fakes import FAKE_FFMPEG, FakeFfmpeg

HDR_INPUT = (
    "testsrc2=s=64x64:d=0.04,"
    "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc,"
    "format=yuv420p10le"
)


class TestTonemapChain:
    def test_runs_the_approved_chain_on_one_hlg_frame(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        fake = FakeFfmpeg()
        monkeypatch.setattr(proc, "run", fake)
        result = check_tonemap_chain()
        assert (result.id, result.required, result.ok) == ("tonemap_chain", True, True)
        assert result.fix_es is None
        (args,) = fake.calls
        assert args[0] == str(FAKE_FFMPEG)
        assert args[1:4] == ["-hide_banner", "-nostdin", "-loglevel"]
        assert args[args.index("-i") + 1] == HDR_INPUT
        assert args[args.index("-vf") + 1] == HDR_TO_SDR
        assert args[-5:] == ["-frames:v", "1", "-f", "null", "-"]

    def test_a_failing_chain_is_reported_with_the_last_stderr_line(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        stderr = "[Parsed_zscale_0] code 3074: no path between colorspaces\r\nError: boom\r\n"
        monkeypatch.setattr(proc, "run", FakeFfmpeg(probe_exit=1, probe_stderr=stderr))
        result = check_tonemap_chain()
        assert result.ok is False
        assert result.required is True
        assert result.detail == "Error: boom"
        assert result.fix_es is not None
        assert "gyan.dev" in result.fix_es

    def test_a_failure_without_stderr_still_says_something(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg(probe_exit=3))
        assert "código 3" in check_tonemap_chain().detail

    def test_media_metadata_is_scrubbed_from_the_detail(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        stderr = "com.apple.quicktime.model: iPhone15\nfallo real\n"
        monkeypatch.setattr(proc, "run", FakeFfmpeg(probe_exit=1, probe_stderr=stderr))
        assert check_tonemap_chain().detail == "fallo real"

    def test_ffmpeg_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def missing(_name: str) -> Path:
            raise MissingDependency("no encuentro ffmpeg")

        monkeypatch.setattr(proc, "tool_path", missing)
        result = check_tonemap_chain()
        assert result.ok is False
        assert "no encuentro ffmpeg" in result.detail


class TestSoxr:
    def test_resamples_with_soxr(self, monkeypatch: pytest.MonkeyPatch, fake_tools: None) -> None:
        fake = FakeFfmpeg()
        monkeypatch.setattr(proc, "run", fake)
        result = check_soxr()
        assert (result.id, result.required, result.ok) == ("soxr", True, True)
        (args,) = fake.calls
        assert args[args.index("-i") + 1] == "sine=d=0.1"
        assert args[args.index("-af") + 1] == "aresample=16000:resampler=soxr"
        assert args[-3:] == ["-f", "null", "-"]

    def test_a_build_without_soxr_fails(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        monkeypatch.setattr(
            proc, "run", FakeFfmpeg(probe_exit=1, probe_stderr="Unknown resampler soxr\n")
        )
        result = check_soxr()
        assert result.ok is False
        assert result.detail == "Unknown resampler soxr"


class TestInRunAll:
    def test_they_sit_right_after_encoders(
        self, monkeypatch: pytest.MonkeyPatch, light_checks: None
    ) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg())
        ids = [r.id for r in checks.run_all("medium")]
        assert ids[ids.index("encoders") + 1 : ids.index("encoders") + 3] == [
            "tonemap_chain",
            "soxr",
        ]

    def test_a_failing_chain_makes_doctor_fail(
        self, monkeypatch: pytest.MonkeyPatch, light_checks: None
    ) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg(probe_exit=1, probe_stderr="nope"))
        results = checks.run_all("medium")
        failed = [r.id for r in results if r.required and not r.ok]
        assert failed == ["tonemap_chain", "soxr"]
