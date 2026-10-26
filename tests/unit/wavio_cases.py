"""`open_wav` and the errors of its body (spec 001.17, point 7). Collected from `test_wavio.py`."""

import wave
from pathlib import Path

import pytest

from kcut import cli
from kcut.audio.wavio import open_wav, wav_duration_ms, wav_peak
from kcut.commands import pack as pack_cmd
from kcut.commands.pack import _energy
from tests.unit.test_pack_command import _ready
from tests.unit.wav_fakes import HONEST, PCM, chunk, fmt, wav
from tests.unit.wav_fakes import outcome as _outcome
from tests.unit.wav_fakes import read_all as _read_all

__all__ = ["TestOpenWavBody"]


class TestOpenWavBody:
    """001.17 point 7: `open_wav` turns into ProjectError what `wave.open`, `readframes` and the
    extent check raise, and nothing that happens in the body of the `with`."""

    def _honest(self, tmp_path: Path) -> Path:
        path = tmp_path / "honest.wav"
        path.write_bytes(HONEST["plain"])
        return path

    def test_body_error_not_masked_a_bug_in_the_analysis_keeps_its_type(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def buggy(*args: object, **kwargs: object) -> None:
            raise ValueError("operands could not be broadcast together")

        monkeypatch.setattr(pack_cmd, "rms_db_stream", buggy)
        with pytest.raises(ValueError, match="broadcast"):
            _energy(self._honest(tmp_path))

    def test_body_error_not_masked_any_exception_raised_inside_the_with_passes_through(
        self, tmp_path: Path
    ) -> None:
        for exc in (ValueError("v"), RuntimeError("r"), EOFError("e"), KeyError("k")):
            with pytest.raises(type(exc)), open_wav(self._honest(tmp_path)):
                raise exc

    def test_body_error_not_masked_the_cli_exits_10_with_the_traceback_in_the_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch)

        def buggy(*args: object, **kwargs: object) -> None:
            raise ValueError("operands could not be broadcast together")

        monkeypatch.setattr(pack_cmd, "rms_db_stream", buggy)
        capsys.readouterr()
        assert cli.main(["pack", "--project", str(root)]) == 10
        (log,) = (root / ".kcut" / "logs").glob("pack-*.log")
        text = log.read_text(encoding="utf-8")
        assert "Traceback (most recent call last)" in text and "ValueError: operands" in text

    @pytest.mark.parametrize("raised", [RuntimeError("cannot seek"), EOFError(), ValueError("x")])
    def test_body_error_not_masked_readframes_failures_are_still_project_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raised: Exception
    ) -> None:
        def boom(self: object, count: int) -> bytes:
            raise raised

        monkeypatch.setattr(wave.Wave_read, "readframes", boom)
        path = self._honest(tmp_path)
        for reader in (_read_all, wav_peak, _energy):
            assert _outcome(reader, path) == "ProjectError", reader.__name__

    def test_body_error_not_masked_a_zero_sample_rate_is_a_project_error(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "rate0.wav"
        path.write_bytes(wav([chunk(b"fmt ", fmt(rate=0)), chunk(b"data", PCM)]))
        assert _outcome(wav_duration_ms, path) == "ProjectError"
