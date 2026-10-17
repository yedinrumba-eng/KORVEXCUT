"""`kcut doctor` inside a project reads `transcribe.model`; a broken kcut.toml is reported."""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import run_kcut

pytestmark = pytest.mark.slow


def _project(tmp_path: Path, toml: str) -> Path:
    root = tmp_path / "proyecto ñandú"
    root.mkdir()
    (root / "kcut.toml").write_text(toml, encoding="utf-8")
    return root


def _doctor(*args: str, cwd: Path | None = None) -> tuple[int, dict[str, Any]]:
    result = run_kcut("doctor", "--json", *args, cwd=cwd)
    return result.returncode, json.loads(result.stdout)


def _check(doc: dict[str, Any], check_id: str) -> dict[str, Any]:
    return next(c for c in doc["checks"] if c["id"] == check_id)


def test_the_model_comes_from_the_project(tmp_path: Path) -> None:
    root = _project(tmp_path, '[transcribe]\nmodel = "base"\n')
    _, doc = _doctor("--project", str(root))
    assert _check(doc, "whisper_model")["detail"].startswith("base")
    assert "project_config" not in [c["id"] for c in doc["checks"]]


def test_the_project_is_found_from_a_subfolder(tmp_path: Path) -> None:
    root = _project(tmp_path, '[transcribe]\nmodel = "small"\n')
    (root / "crudo").mkdir()
    _, doc = _doctor(cwd=root / "crudo")
    assert _check(doc, "whisper_model")["detail"].startswith("small")


def test_outside_a_project_the_model_is_medium(tmp_path: Path) -> None:
    folder = tmp_path / "sin proyecto"
    folder.mkdir()
    _, doc = _doctor(cwd=folder)
    assert _check(doc, "whisper_model")["detail"].startswith("medium")
    assert "project_config" not in [c["id"] for c in doc["checks"]]


def test_a_broken_toml_falls_back_to_medium_and_adds_project_config(tmp_path: Path) -> None:
    root = _project(tmp_path, "[transcribe\nmodel = ")
    code, doc = _doctor("--project", str(root))
    config = _check(doc, "project_config")
    assert (config["required"], config["ok"]) == (False, False)
    assert "kcut.toml" in config["detail"]
    assert config["fix_es"]
    assert _check(doc, "whisper_model")["detail"].startswith("medium")
    assert code in (0, 1)
    assert doc["ok"] == all(c["ok"] for c in doc["checks"] if c["required"])


def test_an_invalid_value_names_the_key(tmp_path: Path) -> None:
    root = _project(tmp_path, '[transcribe]\nmodel = "gigante"\n')
    _, doc = _doctor("--project", str(root))
    config = _check(doc, "project_config")
    assert config["ok"] is False
    assert "transcribe.model" in config["detail"]
    assert _check(doc, "whisper_model")["detail"].startswith("medium")


def test_project_config_does_not_make_doctor_fail_by_itself(tmp_path: Path) -> None:
    good_code, _ = _doctor()
    root = _project(tmp_path, "esto no es toml [")
    code, doc = _doctor("--project", str(root))
    assert code == good_code
    assert _check(doc, "project_config")["required"] is False


def test_it_goes_last_so_the_documented_order_is_kept(tmp_path: Path) -> None:
    root = _project(tmp_path, "[[")
    _, doc = _doctor("--project", str(root))
    ids = [c["id"] for c in doc["checks"]]
    assert ids[-1] == "project_config"
    assert ids[:3] == ["python", "ffmpeg", "ffprobe"]


def test_an_explicit_folder_without_kcut_toml_is_not_a_project(tmp_path: Path) -> None:
    folder = tmp_path / "carpeta"
    folder.mkdir()
    _, doc = _doctor("--project", str(folder))
    assert "project_config" not in [c["id"] for c in doc["checks"]]
    assert _check(doc, "whisper_model")["detail"].startswith("medium")
