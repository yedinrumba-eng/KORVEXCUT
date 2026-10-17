"""Clip classification and stable id assignment."""

from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.ingest.classify import ID_HIGH_MAX, ID_PREFIX, ClipClass, NewFile, assign_ids, classify
from kcut.ingest.inventory import Clip, Inventory, load_inventory, save_inventory
from kcut.ingest.probe import AudioInfo, MediaInfo
from tests.unit.media_fakes import make_video

_VIDEO = make_video()
_AUDIO = AudioInfo("aac", 48000, 2, 0, 1)


def _info(video: bool, audio: bool) -> MediaInfo:
    return MediaInfo(1000, 10, "mov", _VIDEO if video else None, _AUDIO if audio else None)


class TestClassify:
    @pytest.mark.parametrize(
        "ext", [".txt", ".md", ".pdf", ".doc", ".docx", ".rtf", ".odt", ".PDF"]
    )
    def test_documents_by_extension(self, ext: str) -> None:
        assert classify(ext, None, None) == "doc"

    @pytest.mark.parametrize(
        "ext", [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".JPG"]
    )
    def test_images_by_extension(self, ext: str) -> None:
        assert classify(ext, None, None) == "imagen"

    def test_extension_wins_over_streams(self) -> None:
        assert classify(".png", _info(video=True, audio=False), None) == "imagen"
        assert classify(".txt", _info(video=False, audio=True), -3.0) == "doc"

    def test_extension_without_the_dot_is_accepted(self) -> None:
        assert classify("pdf", None, None) == "doc"

    def test_no_probe_is_unknown(self) -> None:
        assert classify(".bin", None, None) == "desconocido"

    def test_video_with_audible_audio_is_video_voz(self) -> None:
        assert classify(".mov", _info(True, True), -3.2) == "video_voz"
        assert classify(".mov", _info(True, True), -59.9) == "video_voz"

    @pytest.mark.parametrize("peak", [-60.0, -80.0, -120.0, None])
    def test_video_with_silent_or_unmeasured_audio_is_video_mudo(self, peak: float | None) -> None:
        assert classify(".mov", _info(True, True), peak) == "video_mudo"

    def test_video_without_audio_is_video_mudo(self) -> None:
        assert classify(".mp4", _info(True, False), None) == "video_mudo"

    def test_audio_only(self) -> None:
        assert classify(".m4a", _info(False, True), -3.0) == "audio"
        assert classify(".m4a", _info(False, True), -90.0) == "audio"

    def test_a_probe_with_no_streams_is_unknown(self) -> None:
        assert classify(".xyz", _info(False, False), None) == "desconocido"

    def test_id_prefixes(self) -> None:
        assert ID_PREFIX == {
            "video_voz": "a",
            "video_mudo": "b",
            "audio": "s",
            "imagen": "i",
            "doc": "d",
            "desconocido": "u",
        }


def _clip(
    clip_id: str, qhash: str, clip_class: ClipClass = "video_voz", file: str | None = None
) -> Clip:
    return Clip(clip_id, file or f"crudo/{clip_id}.mov", clip_id, clip_class, qhash, 1)


def _inventory(*clips: Clip, id_high: dict[str, int] | None = None) -> Inventory:
    return Inventory(generated="x", fps=30, clips=clips, id_high=id_high or {})


def _files(*items: tuple[str, str, ClipClass]) -> list[NewFile]:
    return [NewFile(rel, qhash, clip_class) for rel, qhash, clip_class in items]


def _ingest(files: list[NewFile], previous: Inventory | None) -> Inventory:
    """What the next inventory looks like after assigning ids to `files`."""
    ids, high = assign_ids(files, previous)
    clips = tuple(_clip(ids[f.rel], f.qhash, f.clip_class, f.rel) for f in files)
    return Inventory(generated="x", fps=30, clips=clips, id_high=high)


class TestAssignIds:
    def test_first_ingest_numbers_per_prefix_in_path_order(self) -> None:
        files = _files(
            ("crudo/pantalla.mp4", "h5", "video_mudo"),
            ("crudo/cam b.mov", "h3", "video_voz"),
            ("crudo/foto.png", "h4", "imagen"),
            ("crudo/cam a.mp4", "h2", "video_voz"),
            ("crudo/brief.txt", "h1", "doc"),
        )
        ids, high = assign_ids(files, None)
        assert ids == {
            "crudo/brief.txt": "d1",
            "crudo/cam a.mp4": "a1",
            "crudo/cam b.mov": "a2",
            "crudo/foto.png": "i1",
            "crudo/pantalla.mp4": "b1",
        }
        assert high == {"d": 1, "a": 2, "i": 1, "b": 1}

    def test_order_ignores_case(self) -> None:
        files = _files(("crudo/B.mov", "h1", "video_voz"), ("crudo/a.mov", "h2", "video_voz"))
        assert assign_ids(files, None)[0] == {"crudo/a.mov": "a1", "crudo/B.mov": "a2"}

    def test_a_known_hash_keeps_its_id_even_if_renamed(self) -> None:
        previous = _inventory(_clip("a1", "h1"), _clip("a2", "h2"))
        files = _files(
            ("crudo/nuevo nombre.mov", "h2", "video_voz"), ("crudo/otro.mov", "h1", "video_voz")
        )
        assert assign_ids(files, previous)[0] == {
            "crudo/nuevo nombre.mov": "a2",
            "crudo/otro.mov": "a1",
        }

    def test_the_hash_and_file_pair_wins_over_the_hash_alone(self) -> None:
        previous = _inventory(
            _clip("a1", "H", file="crudo/y.mov"), _clip("a2", "H", file="crudo/x.mov")
        )
        files = _files(("crudo/x.mov", "H", "video_voz"), ("crudo/y.mov", "H", "video_voz"))
        assert assign_ids(files, previous)[0] == {"crudo/x.mov": "a2", "crudo/y.mov": "a1"}

    def test_new_files_take_the_next_number_above_id_high(self) -> None:
        previous = _inventory(_clip("a1", "h1"), _clip("a2", "h2"))
        files = _files(
            ("crudo/a.mov", "h1", "video_voz"),
            ("crudo/b.mov", "h2", "video_voz"),
            ("crudo/c.mov", "h9", "video_voz"),
            ("crudo/d.mp4", "h8", "video_mudo"),
        )
        ids, high = assign_ids(files, previous)
        assert (ids["crudo/c.mov"], ids["crudo/d.mp4"]) == ("a3", "b1")
        assert high == {"a": 3, "b": 1}

    def test_ids_never_reused_when_a_clip_is_reexported(self) -> None:
        cam1, cam2, cam3 = "crudo/cam1.mov", "crudo/cam2.mov", "crudo/cam3.mov"
        first = _ingest(_files((cam1, "H1", "video_voz"), (cam2, "H2", "video_voz")), None)
        assert [c.id for c in first.clips] == ["a1", "a2"]

        second = _ingest(_files((cam1, "H1", "video_voz"), (cam2, "H2b", "video_voz")), first)
        assert {c.file: c.id for c in second.clips} == {cam1: "a1", cam2: "a3"}

        third = _ingest(
            _files(
                (cam1, "H1", "video_voz"), (cam2, "H2b", "video_voz"), (cam3, "H3", "video_voz")
            ),
            second,
        )
        assert {c.file: c.id for c in third.clips} == {cam1: "a1", cam2: "a3", cam3: "a4"}
        assert "a2" not in {c.id for c in third.clips}
        assert third.id_high == {"a": 4}

    def test_ids_never_reused_after_a_file_is_deleted(self) -> None:
        previous = _inventory(
            _clip("a1", "h1"), _clip("a2", "h2"), _clip("a3", "h3"), id_high={"a": 3}
        )
        files = _files(
            ("crudo/a1.mov", "h1", "video_voz"),
            ("crudo/a3.mov", "h3", "video_voz"),
            ("crudo/nuevo.mov", "h9", "video_voz"),
        )
        assert assign_ids(files, previous)[0]["crudo/nuevo.mov"] == "a4"

    def test_a_deleted_top_id_is_not_handed_out_again_either(self) -> None:
        previous = _inventory(_clip("a1", "h1"), id_high={"a": 5})
        files = _files(("crudo/a1.mov", "h1", "video_voz"), ("crudo/n.mov", "h9", "video_voz"))
        ids, high = assign_ids(files, previous)
        assert ids["crudo/n.mov"] == "a6"
        assert high == {"a": 6}

    def test_without_id_high_it_is_rebuilt_from_the_ids_present(self) -> None:
        previous = _inventory(_clip("a1", "h1"), _clip("a7", "h7"))
        files = _files(("crudo/n.mov", "h9", "video_voz"))
        assert assign_ids(files, previous)[0]["crudo/n.mov"] == "a8"

    def test_identical_copies_do_not_share_an_id(self) -> None:
        previous = _inventory(_clip("a1", "h1"), id_high={"a": 1})
        files = _files(("crudo/a.mov", "h1", "video_voz"), ("crudo/copia a.mov", "h1", "video_voz"))
        ids, _ = assign_ids(files, previous)
        assert sorted(ids.values()) == ["a1", "a2"]
        assert ids["crudo/a.mov"] == "a1"

    def test_a_changed_class_does_not_keep_an_id_of_another_prefix(self) -> None:
        previous = _inventory(_clip("a1", "h1"), id_high={"a": 1})
        files = _files(("crudo/a1.mov", "h1", "video_mudo"))
        ids, high = assign_ids(files, previous)
        assert ids == {"crudo/a1.mov": "b1"}
        assert high == {"a": 1, "b": 1}

    def test_same_input_same_ids(self) -> None:
        files = _files(("crudo/x.mov", "h1", "video_voz"), ("crudo/y.wav", "h2", "audio"))
        first = _ingest(files, None)
        again = _ingest(files, first)
        assert {c.file: c.id for c in again.clips} == {c.file: c.id for c in first.clips}
        assert again.id_high == first.id_high


class TestIdCap:
    """`ID_HIGH_MAX = 999_998`: every id that is issued passes the inventory validator."""

    def test_id_cap_raises_a_project_error_instead_of_an_id_nobody_would_accept(self) -> None:
        previous = _inventory(id_high={"a": ID_HIGH_MAX})
        files = _files(("crudo/nuevo.mov", "h1", "video_voz"))
        with pytest.raises(ProjectError, match="agotaron") as info:
            assign_ids(files, previous)
        assert info.value.exit_code == 3

    def test_id_cap_is_per_prefix(self) -> None:
        previous = _inventory(id_high={"a": ID_HIGH_MAX})
        files = _files(("crudo/nota.txt", "h1", "doc"))
        ids, high = assign_ids(files, previous)
        assert ids == {"crudo/nota.txt": "d1"}
        assert high["a"] == ID_HIGH_MAX

    def test_id_cap_one_below_still_issues_the_last_valid_id(self, tmp_path: Path) -> None:
        previous = _inventory(id_high={"a": ID_HIGH_MAX - 1})
        ids, high = assign_ids(_files(("crudo/x.mov", "h1", "video_voz")), previous)
        assert ids == {"crudo/x.mov": "a999998"}
        assert high["a"] == ID_HIGH_MAX
        # the id it issued passes the validator and so does the inventory that records it
        clip = _clip("a999998", "sha256:11111111", file="crudo/x.mov")
        path = tmp_path / ".kcut" / "inventory.json"
        save_inventory(path, Inventory("x", 30, (clip,), id_high=high))
        assert load_inventory(path, tmp_path).by_id("a999998") is not None

    def test_id_cap_is_what_the_validator_accepts(self, tmp_path: Path) -> None:
        path = tmp_path / ".kcut" / "inventory.json"
        over = Inventory("x", 30, (_clip("a999999", "sha256:22222222"),), id_high={"a": 999_999})
        save_inventory(path, over)
        with pytest.raises(ProjectError, match="id_high"):
            load_inventory(path, tmp_path)
        assert ID_HIGH_MAX == 999_998
