"""Inventory file: JSON shape, round trip, strict reading."""

import json
import re
from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.ingest.classify import ClipClass
from kcut.ingest.inventory import (
    Clip,
    ClipAudio,
    ImageMeta,
    Inventory,
    SyncInfo,
    SyncMember,
    SyncRejected,
    WorkFiles,
    load_inventory,
    save_inventory,
)
from kcut.ingest.sync_stage import clip_warnings
from tests.unit.media_fakes import make_hlg_video

VIDEO = make_hlg_video(
    codec="hevc",
    w=3840,
    h=2160,
    display_w=2160,
    display_h=3840,
    rotation=-90,
    fps_r="60/1",
    fps_avg="35460/593",
    vfr=True,
    dolby_vision=True,
    dv_profile=8,
    color_range="tv",
)


_CLASSES: dict[str, ClipClass] = {"a": "video_voz", "s": "audio"}


def _stubs(*ids: str) -> tuple[Clip, ...]:
    """Bare clips for the ids a sync block names: it can only name clips the inventory has."""
    return tuple(Clip(i, f"crudo/{i}.bin", i, _CLASSES[i[0]], "sha256:00000000", 1) for i in ids)


def _sample() -> Inventory:
    return Inventory(
        generated="2026-10-16T10:22:31",
        fps=30,
        id_high={"a": 2, "d": 1, "i": 1, "s": 2},
        clips=(
            Clip(
                "a1",
                "crudo/crudo 1.MOV",
                "crudo-1",
                "video_voz",
                "sha256:9f2c",
                1534023111,
                131233,
                3936,
                VIDEO,
                ClipAudio("aac", 44100, 2, 0, 1, -3.2, False),
                None,
                WorkFiles(".kcut/proxy/a1_crudo-1.mp4", ".kcut/wav16/a1_crudo-1.wav", 540, 960),
                ("vfr", "hdr", "dolby_vision", "rotation"),
            ),
            Clip(
                "i1",
                "crudo/foto.png",
                "foto",
                "imagen",
                "sha256:aa",
                20311,
                image=ImageMeta(800, 600, True),
            ),
            Clip("d1", "crudo/brief.txt", "brief", "doc", "sha256:bb", 512),
            *_stubs("a2", "s1", "s2"),
        ),
        sync=SyncInfo(
            "a1",
            (SyncMember("a2", 4722, 0.91, 0.31, 2.94, 1, 9, "envelope+raw", 0.99),),
            (
                SyncRejected("s1", 0.12, 1.1, "pico de correlacion bajo"),
                SyncRejected("s2", 0.4, 2.2, "sync_weak_refine: bajo", 0.018),
            ),
        ),
    )


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / ".kcut" / "inventory.json"
    save_inventory(path, _sample())
    assert load_inventory(path) == _sample()


def test_file_shape_matches_the_spec_example(tmp_path: Path) -> None:
    path = tmp_path / "inventory.json"
    save_inventory(path, _sample())
    data = json.loads(path.read_text(encoding="utf-8"))
    assert list(data) == ["schema", "generated", "fps", "id_high", "clips", "sync"]
    assert data["id_high"] == {"a": 2, "d": 1, "i": 1, "s": 2}
    assert data["schema"] == "kcut.inventory/1"
    a1, i1, d1, *stubs = data["clips"]  # the stubs are the clips the sync block names
    assert [clip["id"] for clip in stubs] == ["a2", "s1", "s2"]
    assert list(a1) == [
        "id",
        "file",
        "slug",
        "class",
        "qhash",
        "size_bytes",
        "duration_ms",
        "frames",
        "video",
        "audio",
        "work",
        "warnings",
    ]
    assert a1["video"]["color_transfer"] == "arib-std-b67"
    assert a1["audio"] == {
        "codec": "aac",
        "sample_rate": 44100,
        "channels": 2,
        "start_ms": 0,
        "streams": 1,
        "peak_dbfs": -3.2,
        "silent": False,
    }
    assert a1["work"]["proxy_w"] == 540
    assert list(i1) == ["id", "file", "slug", "class", "qhash", "size_bytes", "image", "warnings"]
    assert i1["image"] == {"w": 800, "h": 600, "has_alpha": True}
    assert list(d1) == ["id", "file", "slug", "class", "qhash", "size_bytes", "warnings"]
    assert data["sync"]["members"][0]["method"] == "envelope+raw"
    assert data["sync"]["rejected"][0]["reason"] == "pico de correlacion bajo"
    assert data["sync"]["members"][0]["refine_corr"] == 0.99
    assert list(data["sync"]["members"][0])[:6] == [
        "id",
        "offset_ms",
        "score",
        "second",
        "ratio",
        "refine_corr",
    ]
    assert data["sync"]["rejected"][0]["refine_corr"] is None
    assert data["sync"]["rejected"][1]["refine_corr"] == 0.018


def test_written_as_utf8_with_unix_newlines(tmp_path: Path) -> None:
    path = tmp_path / "inventory.json"
    inv = Inventory(
        "x",
        30,
        (Clip("d1", "crudo/ñandú.txt", "nandu", "doc", "sha256:bb", 1),),
        id_high={"d": 1},
    )
    save_inventory(path, inv)
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert "crudo/ñandú.txt" in raw.decode("utf-8")
    assert load_inventory(path) == inv


def test_an_unbounded_ratio_is_stored_as_null_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "inventory.json"
    member = SyncMember("a2", 5, 0.5, 0.0, None, None, 0, "manual")
    inv = Inventory("x", 30, _stubs("a1", "a2"), SyncInfo("a1", (member,)), {"a": 2})
    save_inventory(path, inv)
    text = path.read_text(encoding="utf-8")
    assert "Infinity" not in text
    assert json.loads(text)["sync"]["members"][0]["ratio"] is None
    assert load_inventory(path) == inv


def test_by_id() -> None:
    inv = _sample()
    found = inv.by_id("i1")
    assert found is not None and found.file == "crudo/foto.png"
    assert inv.by_id("zz") is None


class TestStrictReading:
    def _write(self, tmp_path: Path, mutate: object) -> Path:
        path = tmp_path / "inventory.json"
        save_inventory(path, _sample())
        data = json.loads(path.read_text(encoding="utf-8"))
        assert callable(mutate)
        mutate(data)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    @pytest.mark.parametrize(
        ("mutate", "fragment"),
        [
            (lambda d: d.update(schema="otro/1"), "schema"),
            (lambda d: d.update(extra=1), "extra"),
            (lambda d: d["clips"][0].update(class_="x"), "class_"),
            (lambda d: d["clips"][0].update({"class": "video_raro"}), "class"),
            (lambda d: d["clips"][0]["video"].update(w="3840"), "clips[0].video.w"),
            (lambda d: d["clips"][0]["video"].pop("fps_r"), "fps_r"),
            (lambda d: d["clips"][0]["audio"].update(silent=0), "silent"),
            (lambda d: d["clips"][0]["work"].update(extra=1), "extra"),
            (lambda d: d["clips"][1]["image"].update(w=0), "image.w"),
            (lambda d: d["sync"]["members"][0].update(offset_ms=1.5), "offset_ms"),
            (lambda d: d["sync"]["rejected"][0].pop("reason"), "reason"),
            (lambda d: d["clips"][0].update(warnings=[1]), "warnings"),
        ],
    )
    def test_bad_files_name_the_field(self, tmp_path: Path, mutate: object, fragment: str) -> None:
        path = self._write(tmp_path, mutate)
        with pytest.raises(ProjectError, match=re.escape(fragment)) as info:
            load_inventory(path)
        assert info.value.exit_code == 3

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectError, match="no existe"):
            load_inventory(tmp_path / "no.json")

    def test_malformed_json(self, tmp_path: Path) -> None:
        path = tmp_path / "inventory.json"
        path.write_text("{ roto", encoding="utf-8")
        with pytest.raises(ProjectError, match="JSON mal formado"):
            load_inventory(path)


def _rejection_warnings(rejected: SyncRejected) -> tuple[str, ...]:
    clip = Clip("s2", "crudo/b.wav", "b", "audio", "sha256:bb", 10)
    return clip_warnings(clip, 30, SyncInfo("a1", (), (rejected,)), 20, frozenset())


@pytest.mark.parametrize(
    ("reason", "refine_corr", "expected"),
    [
        ("pico de correlacion bajo", None, ("sync_rejected",)),
        # a ratio rejection that carries a refine_corr is still just `sync_rejected`
        ("pico ambiguo (hay otro casi igual de alto)", 0.62, ("sync_rejected",)),
        ("sync_weak_refine: bajo", 0.018, ("sync_rejected", "sync_weak_refine")),
        # the motive is read from the reason, not deduced from `refine_corr`
        ("sync_weak_refine: bajo", None, ("sync_rejected", "sync_weak_refine")),
        ("sync_ambiguous: dos desfases", 0.85, ("sync_rejected", "sync_ambiguous")),
        ("sync_ambiguous: dos desfases", None, ("sync_rejected", "sync_ambiguous")),
        ("un texto que esta version no escribe", 0.9, ("sync_rejected",)),
    ],
)
def test_warning_from_reason_comes_from_the_stored_reason(
    reason: str, refine_corr: float | None, expected: tuple[str, ...]
) -> None:
    assert _rejection_warnings(SyncRejected("s2", 0.5, 2.0, reason, refine_corr)) == expected


def test_ambiguous_rejection_keeps_its_two_lags_and_round_trips(tmp_path: Path) -> None:
    ambiguous = SyncRejected("s2", 0.9, 4.0, "sync_ambiguous: x", 0.85, -2800, 4000)
    plain = SyncRejected("s3", 0.1, 1.0, "pico de correlacion bajo")
    clips, sync = _stubs("a1", "s2", "s3"), SyncInfo("a1", (), (ambiguous, plain))
    inv = Inventory("x", 30, clips, sync=sync, id_high={"a": 1, "s": 3})
    path = tmp_path / "inventory.json"
    save_inventory(path, inv)
    first, second = json.loads(path.read_text(encoding="utf-8"))["sync"]["rejected"]
    assert (first["lag_a_ms"], first["lag_b_ms"]) == (-2800, 4000)
    assert (second["lag_a_ms"], second["lag_b_ms"]) == (None, None)
    assert load_inventory(path) == inv


@pytest.mark.parametrize("bad", ["4000", 4000.5, True, [1]])
def test_ambiguous_lags_must_be_integers(tmp_path: Path, bad: object) -> None:
    path = tmp_path / "inventory.json"
    save_inventory(
        path, Inventory("x", 30, (), sync=SyncInfo("a1", (), (SyncRejected("s2", 0.9, 4.0, "r"),)))
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sync"]["rejected"][0]["lag_b_ms"] = bad
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProjectError, match="lag_b_ms"):
        load_inventory(path)
