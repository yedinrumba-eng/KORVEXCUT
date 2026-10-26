"""The size of a proxy has a ceiling (spec 001.20, point 4, S1.4-27).

`work.proxy_w` / `proxy_h` come from `.kcut/inventory.json`, which nobody has to trust: a huge
size there used to become a read of `w * h * 3` bytes. Now the inventory refuses more than 4096,
`proxy_of` asks the size to be the one the ingest gives that video, and `FrameReader` refuses a
frame of more than 64 MB before it starts anything.
"""

import dataclasses
from pathlib import Path

import pytest

from kcut.commands.view import proxy_of
from kcut.errors import ProjectError
from kcut.ff import reader
from kcut.ff.reader import FrameReader
from kcut.ingest.inventory import Clip, load_inventory
from kcut.paths import Layout
from kcut.project import Project, open_project
from tests.unit.inventory_fakes import set_work, valid_inventory, written

MISMATCH = "el proxy no coincide con el inventario; corre kcut ingest"
MB64 = 64 * 1024 * 1024


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "proyecto ñandú"
    (folder / ".kcut").mkdir(parents=True)
    return folder


@pytest.fixture
def project(tmp_path: Path) -> Project:
    folder = tmp_path / "otro ñandú"
    folder.mkdir()
    (folder / "kcut.toml").write_text("", encoding="utf-8")
    for path in Layout(folder).all_paths():
        path.mkdir(parents=True, exist_ok=True)
    (folder / ".kcut" / "proxy" / "a1_cam-a.mp4").write_bytes(b"not a video, only a file")
    return open_project(str(folder))


def _clip(**work: object) -> Clip:
    clip = valid_inventory().clips[0]  # video 1440 x 2560: the ingest makes it 540 x 960
    assert clip.work is not None
    return dataclasses.replace(clip, work=dataclasses.replace(clip.work, **work))


class TestInventoryCap:
    @pytest.mark.parametrize("key", ["proxy_w", "proxy_h"])
    def test_proxy_size_cap_4096_is_the_most_the_inventory_takes(
        self, root: Path, key: str
    ) -> None:
        loaded = load_inventory(written(root, set_work(**{key: 4096})), root)
        assert getattr(loaded.clips[0].work, key) == 4096

    @pytest.mark.parametrize("key", ["proxy_w", "proxy_h"])
    @pytest.mark.parametrize("value", [4097, 20_000, 10**9, 10**400])
    def test_proxy_size_cap_more_than_4096_is_inventory_invalid(
        self, root: Path, key: str, value: int
    ) -> None:
        path = written(root, set_work(**{key: value}))
        with pytest.raises(ProjectError) as info:
            load_inventory(path, root)
        assert info.value.exit_code == 3 and key in info.value.message_es


class TestProxyOf:
    def test_proxy_size_cap_proxy_of_gives_the_file_and_the_size_the_ingest_gives(
        self, project: Project
    ) -> None:
        path, size = proxy_of(project, _clip())
        assert path.name == "a1_cam-a.mp4" and size == (540, 960)

    @pytest.mark.parametrize(
        ("w", "h"), [(541, 960), (540, 961), (960, 540), (1, 1), (4096, 4096), (270, 480)]
    )
    def test_proxy_size_cap_proxy_of_refuses_a_size_the_ingest_would_not_give(
        self, project: Project, w: int, h: int
    ) -> None:
        with pytest.raises(ProjectError) as info:
            proxy_of(project, _clip(proxy_w=w, proxy_h=h))
        assert info.value.exit_code == 3 and info.value.message_es == MISMATCH

    def test_proxy_size_cap_proxy_of_without_a_size_is_still_the_ingest_message(
        self, project: Project
    ) -> None:
        with pytest.raises(ProjectError, match="falta el proxy de a1; corre kcut ingest"):
            proxy_of(project, _clip(proxy_w=None, proxy_h=None))

    def test_proxy_size_cap_proxy_of_a_rotated_video_follows_the_displayed_size(
        self, project: Project
    ) -> None:
        clip = valid_inventory().clips[0]
        assert clip.video is not None and clip.work is not None
        turned = dataclasses.replace(
            clip,
            video=dataclasses.replace(clip.video, w=2560, h=1440, display_w=1440, display_h=2560),
        )
        assert proxy_of(project, turned)[1] == (540, 960)  # the same picture, turned


class TestFrameReaderCap:
    def _sentinel(self, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
        started: list[list[str]] = []

        def popen(args: list[str], **kwargs: object) -> None:
            started.append(args)
            raise RuntimeError("reached the launch")

        monkeypatch.setattr(reader.proc, "popen", popen)
        return started

    @pytest.mark.parametrize(
        "size", [(5000, 5000), (4096, 5462), (20_000, 20_000), (1, 70_000_000)]
    )
    def test_proxy_size_cap_frame_reader_refuses_a_frame_over_64_mb_before_starting(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, size: tuple[int, int]
    ) -> None:
        started = self._sentinel(monkeypatch)
        assert size[0] * size[1] * 3 > MB64
        with pytest.raises(ProjectError) as info:
            FrameReader(tmp_path / "x.mp4", 0, 1, 30, size, log=None)
        assert info.value.exit_code == 3 and started == []

    @pytest.mark.parametrize("size", [(4096, 4096), (4096, 5461), (540, 960), (1, 1)])
    def test_proxy_size_cap_frame_reader_up_to_64_mb_goes_on_to_start(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, size: tuple[int, int]
    ) -> None:
        started = self._sentinel(monkeypatch)
        assert size[0] * size[1] * 3 <= MB64
        with pytest.raises(RuntimeError, match="reached the launch"):
            FrameReader(tmp_path / "x.mp4", 0, 1, 30, size, log=None)
        assert len(started) == 1

    @pytest.mark.parametrize("size", [(0, 10), (10, 0), (-1, 10)])
    def test_proxy_size_cap_frame_reader_a_size_that_is_not_a_picture_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, size: tuple[int, int]
    ) -> None:
        started = self._sentinel(monkeypatch)
        with pytest.raises(ProjectError):
            FrameReader(tmp_path / "x.mp4", 0, 1, 30, size, log=None)
        assert started == []
