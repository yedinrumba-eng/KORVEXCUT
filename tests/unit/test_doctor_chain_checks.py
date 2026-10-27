"""`tonemap_chain`, `soxr` (S1.2) and `looks` (S1.5b) doctor checks, ffmpeg simulated."""

from pathlib import Path

import pytest

from kcut import proc
from kcut.doctor import checks
from kcut.doctor.chain_checks import check_looks, check_soxr, check_tonemap_chain
from kcut.errors import MissingDependency, ToolError
from kcut.ff.color import HDR_TO_SDR
from kcut.render.looks import LOOKS
from tests.unit.doctor_fakes import FAKE_FFMPEG, LOOKS_FRAME, FakeFfmpeg

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
        assert failed == ["tonemap_chain", "soxr", "looks"]  # S1.5b (001.15): `looks` is one more


class TestLooks:
    """Row 15 (S1.5b, 001.15): every look runs in the reader over a 64x64 lavfi source and gives
    back one frame of 12 288 bytes."""

    def test_runs_each_look_through_reader_args_on_a_lavfi_source(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        fake = FakeFfmpeg()
        monkeypatch.setattr(proc, "run", fake)
        result = check_looks()
        assert (result.id, result.required, result.ok) == ("looks", True, True)
        assert result.detail == f"{len(LOOKS)}/{len(LOOKS)}" and result.fix_es is None
        assert len(fake.calls) == len(LOOKS) == 6
        for args in fake.calls:
            assert args[0] == str(FAKE_FFMPEG) and args[-1] == "-"
            assert args[args.index("-f") + 1] == "lavfi"
            assert args[args.index("-i") + 1] == "color=c=gray:s=64x64:d=0.04"
            assert args[args.index("-frames:v") + 1] == "1"
            assert "format=rgb24" in args[args.index("-vf") + 1]

    def test_the_chains_are_the_ones_of_the_looks_with_the_accent_of_the_template(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        fake = FakeFfmpeg()
        monkeypatch.setattr(proc, "run", fake)
        check_looks()
        chains = [args[args.index("-vf") + 1] for args in fake.calls]
        assert any("colorhold=color=0xE5FF1F:" in chain for chain in chains)
        assert any("vignette=angle=0.5" in chain for chain in chains)
        start = "scale=in_color_matrix=bt709:in_range=tv,format=rgb24,"
        assert any(chain.startswith(start) for chain in chains)

    def test_a_timeout_of_30_s_is_given_to_each_run(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        timeouts: list[object] = []

        def run(args: list[str], **kwargs: object) -> proc.RunResult:
            timeouts.append(kwargs.get("timeout_s"))
            return proc.RunResult(0, LOOKS_FRAME, "")

        monkeypatch.setattr(proc, "run", run)
        assert check_looks().ok is True and timeouts == [30.0] * 6

    def test_a_look_that_gives_back_the_wrong_number_of_bytes_fails_and_is_named(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        def run(args: list[str], **_kwargs: object) -> proc.RunResult:
            broken = "colorhold" in args[args.index("-vf") + 1]
            return proc.RunResult(0, bytes(100) if broken else LOOKS_FRAME, "")

        monkeypatch.setattr(proc, "run", run)
        result = check_looks()
        assert result.ok is False and result.detail == "5/6 fallan: bn-acento"
        assert result.fix_es is not None

    def test_an_ffmpeg_that_exits_with_an_error_fails_every_look(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg(probe_exit=1, probe_stderr="nope"))
        result = check_looks()
        assert result.ok is False and result.detail.startswith("0/6 fallan: neutro, contraste")

    def test_a_tool_error_from_run_counts_as_a_failure_and_not_a_crash(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        def run(args: list[str], **_kwargs: object) -> proc.RunResult:
            raise ToolError("ffmpeg terminó con error")

        monkeypatch.setattr(proc, "run", run)
        assert check_looks().ok is False

    def test_ffmpeg_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def missing(_name: str) -> Path:
            raise MissingDependency("no encuentro ffmpeg")

        monkeypatch.setattr(proc, "tool_path", missing)
        result = check_looks()
        assert result.ok is False and "no encuentro ffmpeg" in result.detail

    def test_it_is_in_run_all_after_soxr_and_before_the_libs(
        self, monkeypatch: pytest.MonkeyPatch, light_checks: None
    ) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg())
        ids = [r.id for r in checks.run_all("medium")]
        assert ids[ids.index("soxr") + 1 : ids.index("soxr") + 3] == ["looks", "libs"]
