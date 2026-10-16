"""Canned ffmpeg answers shared by the doctor unit tests."""

from pathlib import Path

from kcut.doctor import checks
from kcut.proc import RunResult
from tests.unit.test_ffmpeg_caps import ENCODERS_811, VERSION_811

FAKE_FFMPEG = Path("C:/fake/ffmpeg.exe")
FAKE_FFPROBE = Path("C:/fake/ffprobe.exe")


def filters_text(names: tuple[str, ...]) -> str:
    lines = ["Filters:", "  T.. = Timeline support", "  ------"]
    lines += [f" .. {name:<17} V->V       Fake filter." for name in names]
    return "\r\n".join(lines) + "\r\n"


class FakeFfmpeg:
    """Stands in for `proc.run`: answers -version, -filters and -encoders from canned text."""

    def __init__(
        self,
        filters: tuple[str, ...] = checks.REQUIRED_FILTERS + checks.OPTIONAL_FILTERS,
        encoders: str = ENCODERS_811,
        version: str = VERSION_811,
    ) -> None:
        self.filters_text = filters_text(filters)
        self.encoders_text = encoders
        self.version_text = version
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **_kwargs: object) -> RunResult:
        self.calls.append(args)
        flag = args[-1]
        text = {
            "-version": self.version_text,
            "-filters": self.filters_text,
            "-encoders": self.encoders_text,
        }[flag]
        return RunResult(0, text.encode("utf-8"), "")
