"""Caps on what kcut reads and builds from files anyone could have planted (spec 001.16, point 9).

The corrections cannot grow a clip past 20 000 tokens, `kcut.toml` weighs 1 MB at most, `read_json`
looks at the size of the file before it reads and never reserves the whole cap, and the sidecars
(1 MB) and the resources manifest (4 MB) have caps of their own.
"""

import contextlib
import json
import tracemalloc
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from kcut.config.load import load_config
from kcut.errors import CheckFailed, ProjectError
from kcut.ingest import workfiles
from kcut.jsonio import read_json
from kcut.recursos.manifest import load_manifest
from kcut.text.corrections import MAX_TOKENS, Correction, apply
from kcut.transcribe.model import Word
from tests.unit.test_pack_command import _pack, _ready
from tests.unit.transcribe_fakes import FakeClip, Spoken, build_project, tone

MIB = 1024 * 1024


def _words(count: int) -> list[Word]:
    return [Word(f"a1:w{i:04d}", i, f"w{i}", i * 200, i * 200 + 150, 0.9) for i in range(count)]


def _corrections(words: list[Word], tokens: int) -> dict[str, Correction]:
    text = " ".join(["t"] * tokens)
    return {w.id: Correction(w.id, w.text, text) for w in words}


def _sparse(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(size)
    return path


def _padded(path: Path, document: object, size: int) -> Path:
    """A valid JSON document followed by spaces up to exactly `size` bytes."""
    head = json.dumps(document).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(head + b" " * (size - len(head)))
    return path


def _peak_kib(call: Any) -> float:
    tracemalloc.start()
    try:
        call()
    finally:
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    return peak / 1024


def _try(call: Any, *args: object) -> None:
    with contextlib.suppress(ProjectError):
        call(*args)


class TestCorrectionsTokenCap:
    def test_corrections_token_cap_is_20000(self) -> None:
        assert MAX_TOKENS == 20_000

    def test_corrections_token_cap_exactly_the_cap_is_applied(self) -> None:
        words = _words(200)
        assert len(apply(words, _corrections(words, 100))) == 20_000

    def test_corrections_token_cap_one_token_over_is_check_failed(self) -> None:
        words = _words(201)  # 201 x 100 = 20 100 tokens
        with pytest.raises(CheckFailed) as info:
            apply(words, _corrections(words, 100))
        assert "a1" in info.value.message_es and "20000" in info.value.message_es

    def test_corrections_token_cap_counts_the_tokens_of_one_word_corrections_too(self) -> None:
        words = _words(20_001)
        with pytest.raises(CheckFailed):
            apply(words, _corrections(words, 1))

    def test_corrections_token_cap_words_without_corrections_do_not_count(self) -> None:
        words = _words(30_000)
        few = {w.id: c for w, c in zip(words[:5], _corrections(words[:5], 3).values(), strict=True)}
        assert len(apply(words, few)) == 30_000 - 5 + 15

    def test_corrections_token_cap_through_pack_the_exit_is_1_and_nothing_is_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        count = 250
        spoken: list[Spoken] = [(f"w{i}", i * 200, i * 200 + 150, 0.9) for i in range(count)]
        root = _ready(tmp_path, monkeypatch, [FakeClip("a1", tone(60.0))], {"a1": spoken})
        text = " ".join(["t"] * 100)
        items = [{"word": f"a1:w{i:04d}", "expect": f"w{i}", "text": text} for i in range(count)]
        document = {"schema": "kcut.correcciones/1", "items": items}
        (root / "edit").mkdir(exist_ok=True)
        (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")
        capsys.readouterr()
        assert _pack(root, "--json") == 1
        out = json.loads(capsys.readouterr().out)["error"]
        assert out["kind"] == "CheckFailed" and "20000" in out["message"]
        assert not (root / "edit" / "transcripcion.md").exists()


class TestTomlSizeCap:
    def test_toml_size_cap_over_one_megabyte_is_a_project_error(self, tmp_path: Path) -> None:
        path = tmp_path / "kcut.toml"
        path.write_bytes(b"#" * (MIB + 1))
        with pytest.raises(ProjectError, match="1 MB"):
            load_config(path)

    def test_toml_size_cap_exactly_one_megabyte_still_loads(self, tmp_path: Path) -> None:
        path = tmp_path / "kcut.toml"
        path.write_bytes(b"#" * MIB)
        assert load_config(path).output.fps == 30

    def test_toml_size_cap_a_huge_file_is_refused_before_it_is_read(self, tmp_path: Path) -> None:
        path = _sparse(tmp_path / "kcut.toml", 8 * MIB)
        with pytest.raises(ProjectError, match="1 MB"):
            load_config(path)
        assert _peak_kib(lambda: _try(load_config, path)) < 1024

    def test_toml_size_cap_through_the_cli_the_exit_is_3(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = tmp_path / "p"
        (root / ".kcut").mkdir(parents=True)
        (root / "kcut.toml").write_bytes(b"#" * (MIB + 1))
        assert cli.main(["ingest", "--project", str(root), "--json"]) == 3
        assert "1 MB" in capsys.readouterr().out


class TestReadJsonNoPrealloc:
    def test_read_json_no_prealloc_a_small_file_with_the_default_cap_costs_kilobytes(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "a.json"
        path.write_text('{"a": 1}', encoding="utf-8")
        assert _peak_kib(lambda: read_json(path)) < 256  # the 64 MiB cap is not reserved

    def test_read_json_no_prealloc_a_file_over_the_cap_is_refused_without_reading_it(
        self, tmp_path: Path
    ) -> None:
        path = _sparse(tmp_path / "big.json", 3 * MIB)
        with pytest.raises(ProjectError, match="más de 2 MB"):
            read_json(path, 2 * MIB)
        assert _peak_kib(lambda: _try(read_json, path, 2 * MIB)) < 256

    def test_read_json_no_prealloc_a_file_at_the_cap_is_read(self, tmp_path: Path) -> None:
        path = _padded(tmp_path / "a.json", {"a": 1}, 2 * MIB)
        assert read_json(path, 2 * MIB) == {"a": 1}

    def test_read_json_no_prealloc_one_byte_over_is_refused(self, tmp_path: Path) -> None:
        path = _padded(tmp_path / "a.json", {"a": 1}, 2 * MIB + 1)
        with pytest.raises(ProjectError, match="más de 2 MB"):
            read_json(path, 2 * MIB)


class TestSidecarCaps:
    QHASH, PARAMS = "sha256:aaaaaaaa", {"sr": 16000}

    def _work(self, root: Path, size: int) -> Path:
        work = root / "a1_cam.wav"
        work.write_bytes(b"RIFF")
        _padded(workfiles.sidecar_path(work), {"qhash": self.QHASH, "params": self.PARAMS}, size)
        return work

    def test_sidecar_caps_1_mb_is_read(self, tmp_path: Path) -> None:
        work = self._work(tmp_path, MIB)
        assert workfiles.sidecar_state(work, self.QHASH, self.PARAMS) == "fresh"

    def test_sidecar_caps_one_byte_over_1_mb_counts_as_corrupt(self, tmp_path: Path) -> None:
        work = self._work(tmp_path, MIB + 1)
        assert workfiles.sidecar_state(work, self.QHASH, self.PARAMS) == "corrupt"

    def _manifest(self, tmp_path: Path, size: int) -> Any:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))])
        project.layout.manifest.parent.mkdir(parents=True, exist_ok=True)
        _padded(project.layout.manifest, {"schema": "kcut.recursos/1", "items": []}, size)
        return project

    def test_sidecar_caps_the_manifest_reads_4_mb(self, tmp_path: Path) -> None:
        assert load_manifest(self._manifest(tmp_path, 4 * MIB)) is not None

    def test_sidecar_caps_the_manifest_refuses_one_byte_more(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectError, match="más de 4 MB"):
            load_manifest(self._manifest(tmp_path, 4 * MIB + 1))
