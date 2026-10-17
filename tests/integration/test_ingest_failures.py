"""Ingest keeps going when one step of one file fails, and says exactly what failed."""

import json
import shutil
from pathlib import Path

import pytest

from kcut import cli
from kcut.errors import ToolError
from kcut.ingest import examine as examine_module
from kcut.ingest import scan as scan_module
from kcut.ingest import workfiles
from kcut.ingest.probe import MediaInfo
from tests.conftest import run_kcut
from tests.fixtures.synth_media import MediaTruth, has_flite, make_audio_track
from tests.integration.ingest_helpers import ingest, inventory
from tests.unit.media_fakes import make_video

Synth = tuple[Path, MediaTruth]


@pytest.fixture
def blank(tmp_path: Path) -> Path:
    root = tmp_path / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    return root


@pytest.mark.slow
@pytest.mark.ffmpeg
def test_wav16_failed_keeps_class(
    blank: Path, synth_project: Synth, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ffprobe is fine, the audio extraction dies: the clip keeps its class, proxy and frames."""
    shutil.copy2(synth_project[0] / "crudo" / "cam a.mp4", blank / "crudo" / "cam a.mp4")

    def dies(*_a: object, **_k: object) -> Path:
        raise ToolError("ffmpeg se cayo extrayendo el audio")

    monkeypatch.setattr(workfiles, "stage_wav16", dies)
    assert cli.main(["ingest", "--project", str(blank), "--json"]) == 0

    clip = inventory(blank).by_id("b1")
    assert clip is not None
    assert clip.clip_class == "video_mudo"
    assert clip.frames == 360 and clip.duration_ms == 12000
    assert clip.video is not None and clip.audio is None
    assert clip.work is not None and clip.work.wav16 is None
    assert clip.work.proxy is not None and (blank / clip.work.proxy).is_file()
    assert "wav16_failed" in clip.warnings
    assert "probe_failed" not in clip.warnings
    assert "unknown_type" not in clip.warnings


@pytest.mark.slow
@pytest.mark.ffmpeg
def test_wav16_failed_on_an_audio_file_keeps_the_audio_class(
    blank: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_audio_track(blank / "crudo" / "voz.m4a", 0.0, has_flite())

    def dies(*_a: object, **_k: object) -> Path:
        raise ToolError("ffmpeg se cayo")

    monkeypatch.setattr(workfiles, "stage_wav16", dies)
    assert cli.main(["ingest", "--project", str(blank), "--json", "--no-proxy"]) == 0
    clip = inventory(blank).by_id("s1")
    assert clip is not None and clip.clip_class == "audio"
    assert clip.warnings == ("wav16_failed",)
    assert clip.duration_ms is not None and clip.frames is not None


def test_proxy_size_zero_probe_failed(blank: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A video that declares a 0x0 size marks that clip `probe_failed`; the run goes on."""
    (blank / "crudo" / "cero.mp4").write_bytes(b"no importa: el probe esta simulado")
    (blank / "crudo" / "nota.txt").write_text("hola", encoding="utf-8")
    info = MediaInfo(5000, 10, "mov", make_video(w=0, h=0, display_w=0, display_h=0), None)
    monkeypatch.setattr(examine_module, "_probe", lambda path, log: info)

    assert cli.main(["ingest", "--project", str(blank), "--json", "--no-proxy"]) == 0

    broken = inventory(blank).by_id("u1")
    assert broken is not None
    assert broken.clip_class == "desconocido"
    assert broken.warnings == ("probe_failed",)
    assert broken.video is None and broken.work is None
    assert inventory(blank).by_id("d1") is not None


@pytest.mark.slow
@pytest.mark.ffmpeg
def test_corrupt_sidecar_rebuilt(blank: Path, synth_project: Synth) -> None:
    """A sidecar that cannot be read (garbage, or JSON nested too deep) is rebuilt, not fatal."""
    shutil.copy2(synth_project[0] / "crudo" / "cam a.mp4", blank / "crudo" / "cam a.mp4")
    assert ingest(blank, proxies=True)[0] == 0
    proxy = blank / ".kcut" / "proxy" / "a1_cam-a.mp4"
    wav = blank / ".kcut" / "wav16" / "a1_cam-a.wav"
    proxy_side, wav_side = workfiles.sidecar_path(proxy), workfiles.sidecar_path(wav)
    proxy_side.write_text("{ esto no es json", encoding="utf-8")
    wav_side.write_text("[" * 100_000, encoding="utf-8")
    stamps = (proxy.stat().st_mtime_ns, wav.stat().st_mtime_ns)

    code, doc = ingest(blank, proxies=True)

    assert code == 0
    codes = [w["code"] for w in doc["warnings"]]  # type: ignore[attr-defined]
    assert codes.count("cache_rebuilt") == 2
    assert proxy.stat().st_mtime_ns != stamps[0]
    assert wav.stat().st_mtime_ns != stamps[1]
    for side in (proxy_side, wav_side):
        assert "qhash" in json.loads(side.read_text(encoding="utf-8"))
    assert inventory(blank).by_id("a1") is not None


@pytest.mark.slow
@pytest.mark.ffmpeg
def test_a_clip_over_the_maximum_is_registered_but_not_processed(
    blank: Path, synth_project: Synth, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copy2(synth_project[0] / "crudo" / "cam a.mp4", blank / "crudo" / "cam a.mp4")
    real = examine_module._probe

    def long_probe(path: Path, log: Path) -> MediaInfo:  # the 12 s clip "lasts" 13 hours
        info = real(path, log)
        return MediaInfo(13 * 3_600_000, info.size_bytes, info.format_name, info.video, info.audio)

    monkeypatch.setattr(examine_module, "_probe", long_probe)
    assert cli.main(["ingest", "--project", str(blank), "--json"]) == 0
    clip = inventory(blank).by_id("b1")
    assert clip is not None
    assert clip.clip_class == "video_mudo"
    assert clip.warnings == ("long_duration", "too_long")
    assert clip.work is not None and (clip.work.proxy, clip.work.wav16) == (None, None)
    assert clip.audio is None
    assert not list((blank / ".kcut" / "proxy").glob("*.mp4"))
    assert not list((blank / ".kcut" / "wav16").glob("*.wav"))
    assert inventory(blank).sync.master is None


def test_hash_oserror_probe_failed(
    blank: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file that cannot be read for its hash gets no clip and no id; the others are ingested."""
    (blank / "crudo" / "bueno.txt").write_text("hola", encoding="utf-8")
    (blank / "crudo" / "malo.mov").write_bytes(b"bloqueado por otro programa")
    (blank / "crudo" / "otro.txt").write_text("chao", encoding="utf-8")
    real = scan_module.qhash

    def locked(path: Path) -> str:
        if path.name == "malo.mov":
            raise PermissionError(13, "El proceso no tiene acceso al archivo")
        return real(path)

    monkeypatch.setattr(scan_module, "qhash", locked)
    assert cli.main(["ingest", "--project", str(blank), "--json", "--no-proxy"]) == 0
    captured = capsys.readouterr()
    doc = json.loads(captured.out)

    inv = inventory(blank)
    assert [(c.id, c.file) for c in inv.clips] == [
        ("d1", "crudo/bueno.txt"),
        ("d2", "crudo/otro.txt"),
    ]
    assert "u" not in inv.id_high  # no id, not even a retired one, was spent on the broken file
    broken = [w for w in doc["warnings"] if w["code"] == "probe_failed"]
    assert len(broken) == 1
    assert broken[0]["file"] == "crudo/malo.mov"
    assert "crudo/malo.mov" in broken[0]["message_es"]
    assert broken[0]["id"] is None
    assert "crudo/malo.mov" in captured.err  # also said on stderr


def test_a_file_that_could_not_be_hashed_is_ingested_once_it_can_be(
    blank: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (blank / "crudo" / "a.txt").write_text("a", encoding="utf-8")
    (blank / "crudo" / "b.txt").write_text("b", encoding="utf-8")
    real = scan_module.qhash
    monkeypatch.setattr(
        scan_module,
        "qhash",
        lambda p: (_ for _ in ()).throw(OSError("busy")) if p.name == "a.txt" else real(p),
    )
    assert cli.main(["ingest", "--project", str(blank), "--json", "--no-proxy"]) == 0
    assert [c.file for c in inventory(blank).clips] == ["crudo/b.txt"]
    monkeypatch.setattr(scan_module, "qhash", real)
    assert cli.main(["ingest", "--project", str(blank), "--json", "--no-proxy"]) == 0
    assert {c.file: c.id for c in inventory(blank).clips} == {
        "crudo/a.txt": "d2",
        "crudo/b.txt": "d1",
    }


def test_surrogate_name_is_reported_as_probe_failed_and_the_rest_is_ingested(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Windows allows a lone surrogate in a file name; it cannot go to the inventory (001.7)."""
    root = tmp_path / "proyecto ñandú"
    assert cli.main(["new", str(root)]) == 0
    (root / "crudo" / "nota.txt").write_text("hola", encoding="utf-8")
    try:
        (root / "crudo" / "clip\ud800.mov").write_bytes(b"no es un video")
    except (OSError, UnicodeEncodeError) as exc:
        pytest.skip(f"este sistema no admite un nombre con surrogate suelto: {exc}")
    capsys.readouterr()

    assert cli.main(["ingest", "--project", str(root), "--json", "--no-proxy"]) == 0

    doc = json.loads(capsys.readouterr().out)
    (notice,) = [w for w in doc["warnings"] if w["code"] == "probe_failed"]
    assert notice["id"] is None and notice["file"] == "crudo/clip?.mov"
    assert (
        "el nombre de este archivo tiene caracteres inválidos; renómbralo" in notice["message_es"]
    )
    assert [c.id for c in inventory(root).clips] == ["d1"]
    assert (root / ".kcut" / "inventory.json").is_file()
