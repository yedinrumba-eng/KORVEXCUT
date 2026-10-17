"""Doctor checks with `proc.run` simulated: missing filters/encoders must flip ok to false."""

import importlib.metadata
import re
import sys
import tomllib
from collections import namedtuple
from pathlib import Path

import pytest

from kcut import proc
from kcut.doctor import checks
from kcut.doctor.checks import run_all
from kcut.errors import MissingDependency
from tests.unit.doctor_fakes import FAKE_FFMPEG, FAKE_FFPROBE, FakeFfmpeg
from tests.unit.test_ffmpeg_caps import ENCODERS_811

ALL_IDS = [
    "python",
    "ffmpeg",
    "ffprobe",
    "filters",
    "filters_optional",
    "encoders",
    "tonemap_chain",
    "soxr",
    "libs",
    "whisper_model",
    "chromium",
    "fonts",
    "disk",
]


class TestFilterChecks:
    def test_all_present(self, monkeypatch: pytest.MonkeyPatch, fake_tools: None) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg())
        required, optional = checks.check_filters()
        assert (required.id, required.required, required.ok) == ("filters", True, True)
        assert required.detail == "22/22"
        assert required.fix_es is None
        assert (optional.id, optional.required, optional.ok) == ("filters_optional", False, True)
        assert optional.detail == "2/2"

    def test_required_list_has_22_filters(self) -> None:
        assert len(checks.REQUIRED_FILTERS) == 22
        assert len(set(checks.REQUIRED_FILTERS)) == 22

    def test_missing_required_filter_is_detected(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        present = tuple(f for f in checks.REQUIRED_FILTERS if f not in {"zscale", "vibrance"})
        monkeypatch.setattr(proc, "run", FakeFfmpeg(filters=(*present, "flite")))
        required, optional = checks.check_filters()
        assert required.ok is False
        assert required.detail == "20/22 faltan: zscale, vibrance"
        assert required.fix_es == "usa el build full de gyan.dev"
        assert optional.ok is False
        assert optional.required is False
        assert optional.detail == "1/2 faltan: tonemap_opencl"

    def test_encoders_missing_libx264(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        no_x264 = "\r\n".join(ln for ln in ENCODERS_811.split("\r\n") if " libx264 " not in ln)
        monkeypatch.setattr(proc, "run", FakeFfmpeg(encoders=no_x264))
        result = checks.check_encoders()
        assert result.ok is False
        assert result.detail == "2/3 faltan: libx264"

    def test_encoders_all_present(self, monkeypatch: pytest.MonkeyPatch, fake_tools: None) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg())
        assert checks.check_encoders().ok is True


class TestFfmpegChecks:
    def test_version_and_path_in_detail(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg())
        result = checks.check_ffmpeg()
        assert result.ok is True
        assert result.detail == f"8.1.1 {FAKE_FFMPEG}"

    def test_old_major_version_fails(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg(version="ffmpeg version 6.1.1 Copyright"))
        result = checks.check_ffmpeg()
        assert result.ok is False
        assert result.fix_es is not None

    def test_unknown_version_is_ok(self, monkeypatch: pytest.MonkeyPatch, fake_tools: None) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg(version="ffmpeg version N-12345-gabc Copy"))
        result = checks.check_ffmpeg()
        assert result.ok is True
        assert result.detail.startswith("versión desconocida")

    def test_ffmpeg_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def missing(_name: str) -> Path:
            raise MissingDependency("no encuentro ffmpeg")

        monkeypatch.setattr(proc, "tool_path", missing)
        for result in (checks.check_ffmpeg(), checks.check_ffprobe(), checks.check_encoders()):
            assert result.ok is False
            assert "no encuentro ffmpeg" in result.detail
        required, optional = checks.check_filters()
        assert required.ok is False
        assert optional.ok is False

    def test_ffmpeg_gets_hide_banner_and_nostdin_but_ffprobe_only_hide_banner(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: None
    ) -> None:
        fake = FakeFfmpeg()
        monkeypatch.setattr(proc, "run", fake)
        checks.check_ffmpeg()
        checks.check_ffprobe()
        assert fake.calls[0] == [str(FAKE_FFMPEG), "-hide_banner", "-nostdin", "-version"]
        assert fake.calls[1] == [str(FAKE_FFPROBE), "-hide_banner", "-version"]


class TestCheckResults:
    def test_python_is_312(self) -> None:
        result = checks.check_python()
        assert result.ok is (sys.version_info[:2] == (3, 12))
        assert result.detail.startswith("3.12.")

    def test_python_314_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = namedtuple("FakeVersion", "major minor micro releaselevel serial")
        monkeypatch.setattr(sys, "version_info", fake(3, 14, 0, "final", 0))
        result = checks.check_python()
        assert result.ok is False
        assert result.fix_es == "instala con py -3.12; ctranslate2 no soporta 3.14"

    def test_fonts_are_packaged(self) -> None:
        result = checks.check_fonts()
        assert result.ok is True
        assert result.detail == "4 archivos, FreeType ok"

    def test_fonts_missing_file_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(checks, "_FONT_FILES", (*checks._FONT_FILES, "no-existe.woff2"))
        result = checks.check_fonts()
        assert result.ok is False
        assert "no-existe.woff2" in result.detail

    def test_disk_is_not_required(self) -> None:
        result = checks.check_disk()
        assert result.required is False
        assert result.detail.endswith("GB libres")

    def test_disk_low_space_fails_without_being_required(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(checks, "_MIN_FREE_BYTES", 10**18)
        result = checks.check_disk()
        assert (result.ok, result.required) == (False, False)

    def test_libs_import_failure_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(checks, "_LIBS", (("modulo_que_no_existe_kcut", "nada"),))
        result = checks.check_libs()
        assert result.ok is False
        assert "modulo_que_no_existe_kcut" in result.detail

    def test_whisper_model_invalid_name_is_reported(self) -> None:
        result = checks.check_whisper_model("modelo-que-no-existe-xyz")
        assert result.ok is False
        assert result.required is True
        assert result.fix_es is not None
        assert "--allow-download" in result.fix_es


class TestRunAll:
    def test_order_of_ids(self, monkeypatch: pytest.MonkeyPatch, light_checks: None) -> None:
        monkeypatch.setattr(proc, "run", FakeFfmpeg())
        results = run_all("medium")
        assert [r.id for r in results] == ALL_IDS
        assert all(r.ok for r in results if r.required)


def test_whisper_model_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid model name that is simply not downloaded must fail offline, never download."""
    import faster_whisper.utils as fw_utils

    calls: list[tuple[str, dict[str, object]]] = []

    def not_cached(model_name: str, **kwargs: object) -> str:
        calls.append((model_name, kwargs))
        raise RuntimeError("no hay modelo en la cache local")

    monkeypatch.setattr(fw_utils, "download_model", not_cached)
    result = checks.check_whisper_model("medium")
    assert result.id == "whisper_model"
    assert result.required is True
    assert result.ok is False
    assert result.fix_es is not None
    assert "--allow-download" in result.fix_es
    assert calls == [("medium", {"local_files_only": True})]


def test_chromium_hint_derived(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install hint names the installed Playwright; checks.py types no version by hand."""
    import playwright.sync_api as sync_api

    real_version = importlib.metadata.version

    def fake_version(name: str) -> str:
        return "9.8.7" if name == "playwright" else real_version(name)

    def no_browser() -> None:
        raise RuntimeError("Executable doesn't exist")

    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    monkeypatch.setattr(sync_api, "sync_playwright", no_browser)
    result = checks.check_chromium()
    assert result.ok is False
    assert result.fix_es == (
        f'Playwright 9.8.7 necesita su Chromium: "{sys.executable}" '
        "-m playwright install chromium (descarga: pide OK)"
    )
    source = Path(checks.__file__).read_text(encoding="utf-8")
    assert re.search(r"1\.\d+\.\d+", source) is None


def test_chromium_hint_quoted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The interpreter path has spaces on this machine: the hint must be copy-pasteable."""
    import playwright.sync_api as sync_api

    def no_browser() -> None:
        raise RuntimeError("Executable doesn't exist")

    monkeypatch.setattr(sync_api, "sync_playwright", no_browser)
    monkeypatch.setattr(sys, "executable", r"C:\KORVEX DEV\KORVEXCUT\.venv\Scripts\python.exe")
    result = checks.check_chromium()
    assert result.fix_es is not None
    assert f'"{sys.executable}" -m playwright install chromium' in result.fix_es


def test_fonts_hint_derived(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Pillow floor in the fonts hint is the one pyproject.toml declares, never typed twice."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    deps = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["dependencies"]
    floor = next(dep.partition(">=")[2] for dep in deps if dep.lower().startswith("pillow>="))
    monkeypatch.setattr(checks, "_FONT_FILES", (*checks._FONT_FILES, "no-existe.woff2"))
    assert checks.check_fonts().fix_es == (
        f"reinstala el paquete (pip install -e .) y usa Pillow >= {floor} con FreeType"
    )
    real_requires = importlib.metadata.requires

    def fake_requires(name: str) -> list[str] | None:
        if name == "kcut":
            return ["numpy>=1.26", "Pillow>=99.1", 'pytest>=8; extra == "dev"']
        return real_requires(name)

    monkeypatch.setattr(importlib.metadata, "requires", fake_requires)
    assert "usa Pillow >= 99.1 con FreeType" in (checks.check_fonts().fix_es or "")
    source = Path(checks.__file__).read_text(encoding="utf-8")
    assert re.search(r"Pillow\s*>=\s*\d", source) is None
