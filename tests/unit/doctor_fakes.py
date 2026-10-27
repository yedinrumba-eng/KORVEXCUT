"""Canned ffmpeg answers shared by the doctor unit tests."""

from pathlib import Path

from kcut.doctor import checks
from kcut.proc import RunResult
from tests.unit.test_ffmpeg_caps import ENCODERS_811, VERSION_811

FAKE_FFMPEG = Path("C:/fake/ffmpeg.exe")
FAKE_FFPROBE = Path("C:/fake/ffprobe.exe")
LOOKS_FRAME = bytes(64 * 64 * 3)  # S1.5b: what a look gives back in the reader


def filters_text(names: tuple[str, ...]) -> str:
    lines = ["Filters:", "  T.. = Timeline support", "  ------"]
    lines += [f" .. {name:<17} V->V       Fake filter." for name in names]
    return "\r\n".join(lines) + "\r\n"


class FakeFfmpeg:
    """Stands in for `proc.run`: answers -version, -filters and -encoders from canned text.

    Any other call (the synthetic lavfi probes of `tonemap_chain`, `soxr` and `looks`, which
    end in `-`) exits with `probe_exit` and prints `probe_stderr`.
    """

    def __init__(
        self,
        filters: tuple[str, ...] = checks.REQUIRED_FILTERS + checks.OPTIONAL_FILTERS,
        encoders: str = ENCODERS_811,
        version: str = VERSION_811,
        probe_exit: int = 0,
        probe_stderr: str = "",
    ) -> None:
        self.filters_text = filters_text(filters)
        self.encoders_text = encoders
        self.version_text = version
        self.probe_exit = probe_exit
        self.probe_stderr = probe_stderr
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **_kwargs: object) -> RunResult:
        self.calls.append(args)
        canned = {
            "-version": self.version_text,
            "-filters": self.filters_text,
            "-encoders": self.encoders_text,
        }
        if args[-1] in canned:
            return RunResult(0, canned[args[-1]].encode("utf-8"), "")
        # a probe that works gives the 12 288 bytes of the one 64x64 frame of `looks`
        frame = LOOKS_FRAME if self.probe_exit == 0 else b""
        return RunResult(self.probe_exit, frame, self.probe_stderr)
