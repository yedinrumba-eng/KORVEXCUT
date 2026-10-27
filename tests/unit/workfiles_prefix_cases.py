"""`_copy` and the extended-length prefix of Windows (spec 001.28, point 1; row 22).

`_copy(src, dst)` compared `src.resolve() == dst.resolve()` to know it was the same file. With the
`\\\\?\\` prefix on one of the two (what `Path.resolve` does on a file that another process is
replacing at that moment) the answer was "different", and the copy deleted the destination first:
that is, the source. It was the only comparison that failed open.

Collected from `test_workfiles.py`.
"""

import hashlib
import sys
from pathlib import Path

import pytest

from kcut.ingest.workfiles import _copy

__all__ = ["TestExtendedPrefixCopy"]
PREFIX = "\\\\?\\"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(sys.platform != "win32", reason="the prefix is how Windows resolves a path")
class TestExtendedPrefixCopy:
    @pytest.mark.parametrize("wide", [{1}, {2}, {1, 2}], ids=["on-src", "on-dst", "on-both"])
    def test_extended_prefix_copy_of_a_file_over_itself_keeps_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wide: set[int]
    ) -> None:
        x = tmp_path / "a1_x.wav"
        x.write_bytes(b"the only copy of the audio")
        before, calls = _sha(x), [0]
        real = Path.resolve

        def resolve(self: Path, strict: bool = False) -> Path:
            out = real(self, strict=strict)
            calls[0] += 1  # `_copy` resolves the source first and the destination second
            return Path(PREFIX + str(out)) if calls[0] in wide else out

        with monkeypatch.context() as patch:
            patch.setattr(Path, "resolve", resolve)
            _copy(x, x)
        assert calls[0] == 2  # it looked at the two sides, and only there
        assert x.is_file() and _sha(x) == before

    def test_extended_prefix_copy_of_a_file_over_another_still_copies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src, dst = tmp_path / "a.wav", tmp_path / "b.wav"
        src.write_bytes(b"new")
        dst.write_bytes(b"the old one, longer")
        real = Path.resolve

        def resolve(self: Path, strict: bool = False) -> Path:
            return Path(PREFIX + str(real(self, strict=strict)))

        with monkeypatch.context() as patch:
            patch.setattr(Path, "resolve", resolve)
            _copy(src, dst)
        assert dst.read_bytes() == b"new" and src.read_bytes() == b"new"
