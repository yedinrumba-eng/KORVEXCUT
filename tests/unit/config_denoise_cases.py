"""`audio.voice.denoise_nr` of `kcut.toml` (spec S1.8b row 8, 001.15): 0, which leaves `afftdn` out
of the voice chain, or a value from 0.01 to 40, because `afftdn` does not take less than 0.01. A
value between 0 and 0.01 is a ProjectError (exit 3) that names the field. Collected from
`test_config.py`, which is at the 300-line limit.
"""

import json
from pathlib import Path

import pytest

from kcut import cli
from kcut.config.load import parse_config
from kcut.errors import ProjectError


def _fail(text: str) -> str:
    with pytest.raises(ProjectError) as info:
        parse_config(text, default_name="x")
    assert info.value.exit_code == 3
    return info.value.message_es


class TestDenoise:
    @pytest.mark.parametrize("value", ["0", "0.0", "0.01", "10", "40"])
    def test_denoise_nr_takes_zero_or_a_value_from_0_01_to_40(self, value: str) -> None:
        cfg = parse_config(f"[audio.voice]\ndenoise_nr = {value}\n", default_name="x")
        assert cfg.audio.voice.denoise_nr == float(value)

    @pytest.mark.parametrize("value", ["0.005", "0.0099", "1e-9"])
    def test_denoise_nr_between_0_and_0_01_is_refused_and_names_the_field(self, value: str) -> None:
        assert "audio.voice.denoise_nr" in _fail(f"[audio.voice]\ndenoise_nr = {value}\n")

    def test_denoise_nr_0_005_in_kcut_toml_is_exit_3_and_names_the_field(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "kcut.toml").write_text("[audio.voice]\ndenoise_nr = 0.005\n", encoding="utf-8")
        code = cli.main(["ingest", "--project", str(tmp_path), "--json"])
        error = json.loads(capsys.readouterr().out)["error"]
        assert code == 3 and "audio.voice.denoise_nr" in error["message"]
