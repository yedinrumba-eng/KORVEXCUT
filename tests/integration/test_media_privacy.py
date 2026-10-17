"""Privacy: GPS and device model of an iPhone-style clip never reach any output (spec 0.8)."""

import json
import subprocess
from pathlib import Path

import pytest

from kcut import proc
from kcut.errors import ToolError
from kcut.ff.args import wav_args
from tests.conftest import run_kcut
from tests.fixtures.synth_media import make_tagged_mov

pytestmark = pytest.mark.ffmpeg

LEAKS = ("18.4861", "069.9312", "iPhone15", "Metadata:")


@pytest.fixture(scope="module")
def tagged(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("privacy") / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    make_tagged_mov(root / "crudo" / "iphone.mov")
    return root


@pytest.fixture(scope="module")
def ingested(tagged: Path) -> subprocess.CompletedProcess[str]:
    result = run_kcut("ingest", "--project", str(tagged), "--json")
    assert result.returncode == 0, result.stderr
    return result


def _raw_ffprobe(path: Path) -> str:
    done = subprocess.run(
        [str(proc.tool_path("ffprobe")), "-v", "error", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return done.stdout


def _assert_clean(label: str, text: str) -> None:
    for leak in LEAKS:
        assert leak not in text, f"{label} filtra {leak!r}"


def test_precondition_the_raw_ffprobe_does_show_both_values(tagged: Path) -> None:
    raw = _raw_ffprobe(tagged / "crudo" / "iphone.mov")
    assert "18.4861" in raw
    assert "iPhone15" in raw


def test_precondition_ffmpeg_at_info_level_prints_a_metadata_block(tagged: Path) -> None:
    done = subprocess.run(
        [
            str(proc.tool_path("ffmpeg")),
            "-hide_banner",
            "-nostdin",
            "-i",
            str(tagged / "crudo" / "iphone.mov"),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert "Metadata:" in done.stderr
    assert "18.4861" in done.stderr


def test_ingest_json_output_is_clean(ingested: subprocess.CompletedProcess[str]) -> None:
    _assert_clean("kcut ingest --json (stdout)", ingested.stdout)
    _assert_clean("kcut ingest --json (stderr)", ingested.stderr)
    assert json.loads(ingested.stdout)["clips"] == 1


def test_ingest_human_output_is_clean(
    tagged: Path, ingested: subprocess.CompletedProcess[str]
) -> None:
    result = run_kcut("ingest", "--project", str(tagged))
    assert result.returncode == 0
    _assert_clean("kcut ingest (stdout)", result.stdout)
    _assert_clean("kcut ingest (stderr)", result.stderr)


def test_inventory_is_clean(tagged: Path, ingested: subprocess.CompletedProcess[str]) -> None:
    text = (tagged / ".kcut" / "inventory.json").read_text(encoding="utf-8")
    _assert_clean("inventory.json", text)
    assert '"class": "video_voz"' in text


def test_intermediates_carry_no_metadata(
    tagged: Path, ingested: subprocess.CompletedProcess[str]
) -> None:
    wav = tagged / ".kcut" / "wav16" / "a1_iphone.wav"
    proxy = tagged / ".kcut" / "proxy" / "a1_iphone.mp4"
    for path in (wav, proxy):
        assert path.is_file(), path
        _assert_clean(path.name, _raw_ffprobe(path))
        assert "com.apple" not in _raw_ffprobe(path)


def test_logs_are_clean(tagged: Path, ingested: subprocess.CompletedProcess[str]) -> None:
    logs = sorted((tagged / ".kcut" / "logs").glob("*.log"))
    assert logs
    for log in logs:
        text = log.read_text(encoding="utf-8")
        _assert_clean(log.name, text)
        assert "$ " in text


def test_work_file_sidecars_are_clean(
    tagged: Path, ingested: subprocess.CompletedProcess[str]
) -> None:
    for sidecar in (tagged / ".kcut").rglob("*.json"):
        _assert_clean(sidecar.name, sidecar.read_text(encoding="utf-8"))


def test_a_tool_error_on_that_file_is_scrubbed(tagged: Path, tmp_path: Path) -> None:
    """Even at the default log level (which does print metadata), the error message is clean."""
    log = tmp_path / "privacy.log"
    args = [
        str(proc.tool_path("ffmpeg")),
        "-hide_banner",
        "-nostdin",
        "-i",
        str(tagged / "crudo" / "iphone.mov"),
        "-map",
        "0:a:9",
        "-f",
        "null",
        "-",
    ]
    raw = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace", check=False)
    assert raw.returncode != 0
    assert "iPhone15" in raw.stderr  # the child really did print it
    with pytest.raises(ToolError) as info:
        proc.run(args, log=log)
    _assert_clean("ToolError.message_es", info.value.message_es)
    _assert_clean("proc.run log", log.read_text(encoding="utf-8"))


def test_a_kcut_command_that_fails_on_that_file_is_scrubbed(tagged: Path, tmp_path: Path) -> None:
    log = tmp_path / "wav.log"
    missing_dir = tmp_path / "no existe" / "x.partial.wav"
    args = wav_args(proc.tool_path("ffmpeg"), tagged / "crudo" / "iphone.mov", missing_dir, 16000)
    with pytest.raises(ToolError) as info:
        proc.run(args, log=log)
    _assert_clean("ToolError.message_es", info.value.message_es)
    _assert_clean("log", log.read_text(encoding="utf-8"))
