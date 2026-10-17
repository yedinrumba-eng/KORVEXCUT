"""A child's stderr streams into the log in chunks; only its tail stays in memory (0.8, 0.11)."""

import re
import sys
import types
from pathlib import Path
from typing import IO, Any

import pytest

from kcut import childlog, proc
from kcut.errors import ToolError
from kcut.scrub import scrub_media_metadata

PY = getattr(sys, "_base_executable", sys.executable)
MB = 1024**2
LINE_BYTES = 100  # "%08d" + 91 "x" + "\n"


def _writer(lines: int, exit_code: int = 0) -> list[str]:
    """A child that writes `lines` numbered stderr lines of exactly 100 bytes, then exits.

    The code is one line, so the `$` header of the log is one line too.
    """
    code = (
        "import sys; w = sys.stderr.buffer.write; "
        f"[w(b'%08d' % i + b'x' * 91 + b'\\n') for i in range({lines})]; sys.exit({exit_code})"
    )
    return [PY, "-c", code]


def _line(i: int) -> str:
    return f"{i:08d}" + "x" * 91


def _block(log: Path) -> str:
    """The stderr block of the only child in `log`: between its `$` header and its footer."""
    text = log.read_text(encoding="utf-8")
    header, _, rest = text.partition("\n")
    assert header.startswith("$ ")
    body, _, footer = rest.rstrip("\n").rpartition("\n")
    assert footer.startswith("[exit ")
    return body + "\n"


def test_tail_is_capped_marked_and_the_log_gets_everything(tmp_path: Path) -> None:
    lines = 10 * MB // LINE_BYTES + 1
    log = tmp_path / "big.log"
    result = proc.run(_writer(lines), log=log, capture_stderr=True)
    marker, _, kept = result.stderr.partition("\n")
    # The cut lands mid-line: the partial line goes too, so the tail starts on a whole line.
    first_kept = (lines * LINE_BYTES - childlog.TAIL_CAP_BYTES) // LINE_BYTES + 1
    skipped_mb = first_kept * LINE_BYTES / MB
    assert marker == f"[... {skipped_mb:.1f} MB omitidos]"
    assert re.fullmatch(r"\[\.\.\. \d+\.\d MB omitidos\]", marker)
    assert len(kept.encode("utf-8")) <= childlog.TAIL_CAP_BYTES
    kept_lines = kept.splitlines()
    assert kept_lines[0] == _line(first_kept)
    assert kept_lines[-1] == _line(lines - 1)
    assert len(kept_lines) == lines - first_kept
    logged = _block(log).splitlines()
    assert len(logged) == lines
    assert logged[0] == _line(0)
    assert logged[-1] == _line(lines - 1)


def test_error_tail_is_the_last_20_lines_of_a_huge_stderr(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as info:
        proc.run(_writer(9 * MB // LINE_BYTES, exit_code=2), log=tmp_path / "e.log")
    tail = info.value.message_es.splitlines()[-20:]
    last = 9 * MB // LINE_BYTES - 1
    assert tail == [_line(i) for i in range(last - 19, last + 1)]
    assert "omitidos" not in info.value.message_es


class _ReadSpy:
    """Wraps the child's stderr temp file and records the size of every read."""

    def __init__(self, real: IO[bytes], sizes: list[int | None]) -> None:
        self._real = real
        self._sizes = sizes

    def read(self, size: int | None = None) -> bytes:
        self._sizes.append(size)
        return self._real.read(-1 if size is None else size)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def test_the_temp_file_is_never_read_whole(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(childlog, "CHUNK_BYTES", 4096)
    monkeypatch.setattr(childlog, "TAIL_CAP_BYTES", 16384)
    sizes: list[int | None] = []
    real_tempfile = proc.tempfile.TemporaryFile
    fake = types.SimpleNamespace(TemporaryFile=lambda: _ReadSpy(real_tempfile(), sizes))
    monkeypatch.setattr(proc, "tempfile", fake)
    result = proc.run(_writer(1000), log=tmp_path / "spy.log", capture_stderr=True)
    assert result.stderr.startswith("[... ")
    assert sizes
    assert all(size is not None and 0 <= size <= 16384 for size in sizes), sizes
    assert len(_block(tmp_path / "spy.log").splitlines()) == 1000


def test_tiny_chunks_scrub_exactly_like_the_whole_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Chunks cut lines and the Metadata block anywhere: the log must not leak a thing."""
    monkeypatch.setattr(childlog, "CHUNK_BYTES", 7)
    text = (
        "".join(f"relleno {i}\n" for i in range(30))
        + "  Metadata:\n    com.apple.quicktime.model: iPhone 15 Pro\n"
        + "    handler_name    : Core Media Video\n  Duration: 00:00:05.00\n"
        + "TAG:location=+18.4861-069.9312/\nreal problem ñ\n"
    )
    code = f"import sys; sys.stderr.buffer.write({text.encode('utf-8')!r})"
    proc.run([PY, "-c", code], log=tmp_path / "s.log")
    block = _block(tmp_path / "s.log")
    assert block == scrub_media_metadata(text)
    for secret in ("iPhone", "handler_name", "18.4861", "location"):
        assert secret not in block, secret
    assert "  Duration: 00:00:05.00\nreal problem ñ\n" in block


def test_a_tail_cut_inside_a_metadata_block_does_not_leak_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The cut can drop the block header: the indented lines after the cut go with it."""
    monkeypatch.setattr(childlog, "TAIL_CAP_BYTES", 200)
    text = "  Metadata:\n" + "    handler_name    : Core Media Video\n" * 20 + "boom\n"
    code = f"import sys; sys.stderr.buffer.write({text.encode('utf-8')!r}); sys.exit(1)"
    with pytest.raises(ToolError) as info:
        proc.run([PY, "-c", code], log=tmp_path / "m.log")
    message = info.value.message_es
    assert "handler_name" not in message
    assert message.endswith("[... 0.0 MB omitidos]\nboom")


def test_a_line_over_the_limit_keeps_its_start_and_the_block_stays_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(childlog, "CHUNK_BYTES", 7)
    monkeypatch.setattr(childlog, "LONG_LINE_CHARS", 1000)
    huge = "é" * 3000
    cases = {
        huge + "\nfin\n": "é" * 1000 + " [... 0.0 MB omitidos]\nfin\n",
        f"  Metadata:\n    title: {huge}\n    handler_name: x\nfin\n": "fin\n",
    }
    for number, (text, expected) in enumerate(cases.items()):
        code = f"import sys; sys.stderr.buffer.write({text.encode('utf-8')!r})"
        log = tmp_path / f"long{number}.log"
        proc.run([PY, "-c", code], log=log)
        assert _block(log) == expected


def test_one_huge_line_without_newline_is_split_safely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A line longer than a chunk is still streamed; a cut inside a UTF-8 character is safe."""
    monkeypatch.setattr(childlog, "CHUNK_BYTES", 7)
    monkeypatch.setattr(childlog, "TAIL_CAP_BYTES", 101)
    code = "import sys; sys.stderr.buffer.write('é'.encode('utf-8') * 3000)"
    result = proc.run([PY, "-c", code], log=tmp_path / "u.log", capture_stderr=True)
    assert _block(tmp_path / "u.log") == "é" * 3000 + "\n"
    marker, _, kept = result.stderr.partition("\n")
    assert marker == "[... 0.0 MB omitidos]"
    assert kept == "é" * 50
    assert "\ufffd" not in result.stderr
