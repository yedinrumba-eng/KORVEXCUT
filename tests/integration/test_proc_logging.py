"""Concurrent children share one command log without overwriting each other (spec 0.11)."""

import itertools
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from kcut import proc
from kcut.errors import ToolError

LINES = 200


def _spammer(tag: str, exit_code: int = 0) -> list[str]:
    """A child that writes 200 numbered stderr lines (slowly enough to overlap) and exits."""
    code = (
        "import sys, time\n"
        f"for i in range({LINES}):\n"
        f"    print('{tag}-%03d' % i, file=sys.stderr, flush=True)\n"
        "    if i % 50 == 0:\n"
        "        time.sleep(0.05)\n"
        f"sys.exit({exit_code})\n"
    )
    return [sys.executable, "-c", code]


def _log_lines(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines()


def test_two_popen_children_keep_all_400_lines_and_both_headers(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "build-20261016-040000.log"
    with (
        proc.popen(_spammer("A"), log=log) as first,
        proc.popen(_spammer("B"), log=log) as second,
    ):
        assert first.wait(timeout_s=60) == 0
        assert second.wait(timeout_s=60) == 0
    lines = _log_lines(log)
    for tag in ("A", "B"):
        found = [ln for ln in lines if ln.startswith(f"{tag}-")]
        assert found == [f"{tag}-{i:03d}" for i in range(LINES)]
    assert sum(1 for ln in lines if ln.startswith("A-") or ln.startswith("B-")) == 2 * LINES
    assert sum(1 for ln in lines if ln.startswith("$ ")) == 2
    assert sum(1 for ln in lines if ln.startswith("[exit 0 en ")) == 2


def test_stderr_of_each_child_is_one_contiguous_block(tmp_path: Path) -> None:
    log = tmp_path / "cmd.log"
    with proc.popen(_spammer("A"), log=log) as a, proc.popen(_spammer("B"), log=log) as b:
        a.wait(timeout_s=60)
        b.wait(timeout_s=60)
    tags = [ln[0] for ln in _log_lines(log) if ln[:2] in ("A-", "B-")]
    changes = sum(1 for prev, cur in itertools.pairwise(tags) if prev != cur)
    assert changes == 1


def test_many_threads_calling_run_never_lose_a_line(tmp_path: Path) -> None:
    log = tmp_path / "threads.log"
    tags = ["T0", "T1", "T2", "T3"]
    with ThreadPoolExecutor(max_workers=len(tags)) as pool:
        results = list(pool.map(lambda t: proc.run(_spammer(t), log=log, timeout_s=60), tags))
    assert all(r.returncode == 0 for r in results)
    lines = _log_lines(log)
    for tag in tags:
        assert [ln for ln in lines if ln.startswith(f"{tag}-")] == [
            f"{tag}-{i:03d}" for i in range(LINES)
        ]
    assert sum(1 for ln in lines if ln.startswith("$ ")) == len(tags)


def test_error_tail_comes_only_from_the_child_that_failed(tmp_path: Path) -> None:
    log = tmp_path / "mixed.log"
    with ThreadPoolExecutor(max_workers=2) as pool:
        noisy = pool.submit(lambda: proc.run(_spammer("OK"), log=log, timeout_s=60))
        failing = pool.submit(lambda: proc.run(_spammer("BAD", exit_code=3), log=log, timeout_s=60))
        with pytest.raises(ToolError) as info:
            failing.result()
        assert noisy.result().returncode == 0
    message = info.value.message_es
    assert "BAD-199" in message
    assert "BAD-180" in message
    assert "BAD-179" not in message
    assert "OK-" not in message
    assert "código 3" in message


def test_popen_stderr_tail_is_only_this_child(tmp_path: Path) -> None:
    log = tmp_path / "tail.log"
    with proc.popen(_spammer("X"), log=log) as x, proc.popen(_spammer("Y", 2), log=log) as y:
        assert x.wait(timeout_s=60) == 0
        assert y.wait(timeout_s=60) == 2
        assert x.stderr_tail(3).splitlines() == ["X-197", "X-198", "X-199"]
        assert y.stderr_tail().splitlines()[-1] == "Y-199"
        assert len(y.stderr_tail().splitlines()) == 20
        assert "X-" not in y.stderr_tail()


def test_log_block_has_header_stderr_and_exit_footer(tmp_path: Path) -> None:
    log = tmp_path / "one.log"
    proc.run([sys.executable, "-c", "import sys; print('boom', file=sys.stderr)"], log=log)
    lines = _log_lines(log)
    assert lines[0].startswith("$ ")
    assert lines[1] == "boom"
    assert lines[2].startswith("[exit 0 en ") and lines[2].endswith(" s]")


def test_scrubbed_before_reaching_the_log_and_the_error(tmp_path: Path) -> None:
    log = tmp_path / "scrub.log"
    code = (
        "import sys\n"
        "print('  Metadata:', file=sys.stderr)\n"
        "print('    com.apple.quicktime.model: iPh' + 'one 15', file=sys.stderr)\n"
        "print('real problem', file=sys.stderr)\n"
        "sys.exit(1)\n"
    )
    with pytest.raises(ToolError) as info:
        proc.run([sys.executable, "-c", code], log=log)
    assert "iPhone" not in info.value.message_es
    assert "real problem" in info.value.message_es
    assert "iPhone" not in log.read_text(encoding="utf-8")
    assert "real problem" in log.read_text(encoding="utf-8")


def test_capture_stderr_returns_the_raw_text_even_with_metadata(tmp_path: Path) -> None:
    code = "import sys; print('    com.apple.quicktime.model: iPh' + 'one', file=sys.stderr)"
    result = proc.run([sys.executable, "-c", code], capture_stderr=True)
    assert "iPhone" in result.stderr
