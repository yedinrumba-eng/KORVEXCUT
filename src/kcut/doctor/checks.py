"""Machine checks behind `kcut doctor` (spec S1.1)."""

import importlib
import importlib.metadata
import shutil
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Literal

from kcut import proc
from kcut.doctor.ffmpeg_caps import parse_encoders, parse_filters, parse_version
from kcut.errors import KcutError

REQUIRED_FILTERS = (
    "zscale",
    "tonemap",
    "loudnorm",
    "ebur128",
    "sidechaincompress",
    "afftdn",
    "blackdetect",
    "freezedetect",
    "overlay",
    "acompressor",
    "highpass",
    "asplit",
    "anullsink",
    "amix",
    "aresample",
    "scale",
    "fps",
    "colorbalance",
    "curves",
    "vibrance",
    "vignette",
    "colorhold",
)
OPTIONAL_FILTERS = ("flite", "tonemap_opencl")
REQUIRED_ENCODERS = ("libx264", "aac", "pcm_s16le")

_MIN_FFMPEG_MAJOR = 7
_TOOL_TIMEOUT_S = 60.0
_CHROMIUM_BUDGET_S = 30.0
_MIN_FREE_BYTES = 5 * 1024**3
_FONT_FILES = (
    "inter-latin-600-normal.woff2",
    "inter-latin-800-normal.woff2",
    "inter-latin-900-normal.woff2",
    "OFL-Inter.txt",
)
_LIBS = (
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("cv2", "opencv-python"),
    ("PIL", "Pillow"),
    ("faster_whisper", "faster-whisper"),
    ("playwright", "playwright"),
)
_FFMPEG_FIX = "instala ffmpeg 7 o superior (build full de gyan.dev) en el PATH o define KCUT_FFMPEG"
_FULL_BUILD_FIX = "usa el build full de gyan.dev"


@dataclass(frozen=True)
class CheckResult:
    """One line of the doctor report."""

    id: str
    required: bool
    ok: bool
    detail: str
    fix_es: str | None


def run_all(model_name: str) -> list[CheckResult]:
    """Run every check, in the documented order. Never raises for an expected failure."""
    filters, filters_optional = check_filters()
    return [
        check_python(),
        check_ffmpeg(),
        check_ffprobe(),
        filters,
        filters_optional,
        check_encoders(),
        check_libs(),
        check_whisper_model(model_name),
        check_chromium(),
        check_fonts(),
        check_disk(),
    ]


def check_python() -> CheckResult:
    v = sys.version_info
    detail = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) == (3, 12):
        return CheckResult("python", True, True, detail, None)
    return CheckResult(
        "python", True, False, detail, "instala con py -3.12; ctranslate2 no soporta 3.14"
    )


def check_ffmpeg() -> CheckResult:
    try:
        path, text = _tool_output("ffmpeg", "-version")
    except KcutError as exc:
        return CheckResult("ffmpeg", True, False, exc.message_es, _FFMPEG_FIX)
    version = parse_version(text)
    if version is None:
        return CheckResult("ffmpeg", True, True, f"versión desconocida {path}", None)
    detail = f"{version[0]}.{version[1]}.{version[2]} {path}"
    if version[0] < _MIN_FFMPEG_MAJOR:
        return CheckResult("ffmpeg", True, False, detail, _FFMPEG_FIX)
    return CheckResult("ffmpeg", True, True, detail, None)


def check_ffprobe() -> CheckResult:
    try:
        path, _ = _tool_output("ffprobe", "-version")
    except KcutError as exc:
        return CheckResult("ffprobe", True, False, exc.message_es, _FFMPEG_FIX)
    return CheckResult("ffprobe", True, True, str(path), None)


def check_filters() -> tuple[CheckResult, CheckResult]:
    """Return the (required, optional) filter checks from one `ffmpeg -filters` call."""
    try:
        _, text = _tool_output("ffmpeg", "-filters")
    except KcutError as exc:
        return (
            CheckResult("filters", True, False, exc.message_es, _FFMPEG_FIX),
            CheckResult("filters_optional", False, False, exc.message_es, None),
        )
    found = parse_filters(text)
    optional_fix = "opcional: el build full de gyan.dev los incluye (flite solo se usa en tests)"
    return (
        _coverage("filters", True, REQUIRED_FILTERS, found, _FULL_BUILD_FIX),
        _coverage("filters_optional", False, OPTIONAL_FILTERS, found, optional_fix),
    )


def check_encoders() -> CheckResult:
    try:
        _, text = _tool_output("ffmpeg", "-encoders")
    except KcutError as exc:
        return CheckResult("encoders", True, False, exc.message_es, _FFMPEG_FIX)
    return _coverage("encoders", True, REQUIRED_ENCODERS, parse_encoders(text), _FULL_BUILD_FIX)


def check_libs() -> CheckResult:
    versions: list[str] = []
    failed: list[str] = []
    for module, dist in _LIBS:
        try:
            importlib.import_module(module)
        except Exception as exc:
            failed.append(f"{module} ({_short(exc)})")
            continue
        try:
            versions.append(f"{module} {importlib.metadata.version(dist)}")
        except importlib.metadata.PackageNotFoundError:
            versions.append(f"{module} ?")
    if failed:
        return CheckResult(
            "libs",
            True,
            False,
            "no importan: " + ", ".join(failed),
            'reinstala: .venv/Scripts/python.exe -m pip install -e ".[dev]" -c requirements.lock',
        )
    return CheckResult("libs", True, True, ", ".join(versions), None)


def check_whisper_model(model_name: str) -> CheckResult:
    try:
        import faster_whisper.utils as fw_utils

        where = fw_utils.download_model(model_name, local_files_only=True)
    except Exception as exc:
        return CheckResult(
            "whisper_model",
            True,
            False,
            f"{model_name}: {_short(exc)}",
            "kcut transcribe --allow-download baja el modelo (~1.5 GB para medium); pide OK antes",
        )
    return CheckResult("whisper_model", True, True, f"{model_name} {where}", None)


def check_chromium() -> CheckResult:
    start = time.monotonic()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, timeout=_budget_ms(start))
            try:
                browser.new_page().set_content("<p>ok</p>", timeout=_budget_ms(start))
            finally:
                browser.close()
    except Exception as exc:
        return CheckResult("chromium", True, False, _short(exc), _chromium_fix())
    elapsed = time.monotonic() - start
    if elapsed > _CHROMIUM_BUDGET_S:
        detail = f"tardó {elapsed:.1f} s (máximo 30 s)"
        return CheckResult("chromium", True, False, detail, _chromium_fix())
    return CheckResult("chromium", True, True, f"headless ok en {elapsed:.1f} s", None)


def check_fonts() -> CheckResult:
    fonts_dir = files("kcut").joinpath("assets", "fonts")
    missing = [name for name in _FONT_FILES if not fonts_dir.joinpath(name).is_file()]
    try:
        from PIL import ImageFont

        freetype = isinstance(ImageFont.load_default(size=16), ImageFont.FreeTypeFont)
    except Exception:
        freetype = False
    if missing or not freetype:
        problems = [f"faltan: {', '.join(missing)}"] if missing else []
        if not freetype:
            problems.append("Pillow sin FreeType")
        return CheckResult(
            "fonts",
            True,
            False,
            "; ".join(problems),
            "reinstala el paquete (pip install -e .) y usa Pillow >= 10.1 con FreeType",
        )
    return CheckResult("fonts", True, True, f"{len(_FONT_FILES)} archivos, FreeType ok", None)


def check_disk() -> CheckResult:
    free = shutil.disk_usage(Path.cwd()).free
    detail = f"{free / 1024**3:.1f} GB libres"
    if free >= _MIN_FREE_BYTES:
        return CheckResult("disk", False, True, detail, None)
    return CheckResult(
        "disk", False, False, detail, "libera espacio: se recomiendan 5 GB libres para renders"
    )


def _tool_output(name: Literal["ffmpeg", "ffprobe"], *flags: str) -> tuple[Path, str]:
    """Run `<tool> <flags>` and return its path plus stdout and stderr as text."""
    path = proc.tool_path(name)
    base = [str(path), "-hide_banner"]
    if name == "ffmpeg":
        base.append("-nostdin")
    result = proc.run([*base, *flags], timeout_s=_TOOL_TIMEOUT_S, capture_stderr=True)
    return path, result.stdout.decode("utf-8", errors="replace") + result.stderr


def _coverage(
    check_id: str, required: bool, wanted: Iterable[str], found: frozenset[str], fix_es: str
) -> CheckResult:
    names = tuple(wanted)
    missing = [n for n in names if n not in found]
    detail = f"{len(names) - len(missing)}/{len(names)}"
    if not missing:
        return CheckResult(check_id, required, True, detail, None)
    return CheckResult(check_id, required, False, f"{detail} faltan: {', '.join(missing)}", fix_es)


def _chromium_fix() -> str:
    """Install hint built from the installed Playwright, so no version is typed by hand."""
    try:
        version = importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        version = "?"
    return (
        f"Playwright {version} necesita su Chromium: "
        f'"{sys.executable}" -m playwright install chromium (descarga: pide OK)'
    )


def _budget_ms(start: float) -> float:
    """Milliseconds left of the Chromium budget (at least 1 so Playwright accepts it)."""
    return max(1.0, (_CHROMIUM_BUDGET_S - (time.monotonic() - start)) * 1000)


def _short(exc: BaseException) -> str:
    first = (str(exc).strip().splitlines() or [""])[0]
    return f"{type(exc).__name__}: {first}"[:160]
