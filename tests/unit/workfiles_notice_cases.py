"""The notice `cache_rebuilt` of a work file with a damaged sidecar (spec 001.29, point 3, row 31):
it names the file by its class and its clip, `wav48 de a1`, and not by its name, which has the slug
of the original clip and the slug may hold a phone number. `kcut render` prints that notice.

Collected from `test_workfiles.py`, whose `project` fixture (a project with `.kcut/wav16/` and
`crudo/`) these use.
"""

import json

import pytest

from kcut.ingest import workfiles
from kcut.ingest.examine import _audio_peak
from kcut.ingest.inventory import Clip, Notice, WorkFiles
from kcut.ingest.naming import qhash
from kcut.ingest.scan import Found
from kcut.project import Project

__all__ = ["TestNoticeNoSlug"]
SLUG = "ana-perez-809-555-1234"  # of `Ana Perez 809-555-1234.mp4`, as `ingest` makes it
LEAKS = ("ana", "perez", "809", "555", "1234", SLUG)
DAMAGED = "el sidecar estaba dañado y se reconstruye"


def _clean(notice: Notice) -> bool:
    return not any(piece in notice.detail.lower() for piece in LEAKS)


class TestNoticeNoSlug:
    def test_notice_no_slug_a_wav48_with_a_damaged_sidecar_is_named_by_its_class_and_clip(
        self, project: Project
    ) -> None:
        wav = project.layout.wav48 / f"a1_{SLUG}.wav"
        wav.parent.mkdir(parents=True)
        wav.write_bytes(b"audio")
        workfiles.sidecar_path(wav).write_text("{this is not json", encoding="utf-8")
        notices: list[Notice] = []
        assert not workfiles._usable(wav, "sha256:abc", workfiles.wav_params(48000), notices)
        assert [(n.code, n.detail) for n in notices] == [
            ("cache_rebuilt", f"wav48 de a1: {DAMAGED}")
        ]
        assert _clean(notices[0])

    def test_notice_no_slug_a_proxy_with_a_damaged_sidecar_is_named_by_its_class_and_clip(
        self, project: Project
    ) -> None:
        proxy = project.layout.proxy / f"a1_{SLUG}.mp4"
        proxy.parent.mkdir(parents=True)
        proxy.write_bytes(b"video")
        workfiles.sidecar_path(proxy).write_text("", encoding="utf-8")
        notices: list[Notice] = []
        assert not workfiles._usable(proxy, "sha256:abc", {"crf": 23}, notices)
        assert [n.detail for n in notices] == [f"proxy de a1: {DAMAGED}"]
        assert _clean(notices[0])

    def test_notice_no_slug_a_fresh_or_missing_sidecar_says_nothing(self, project: Project) -> None:
        wav = project.layout.wav48 / f"a1_{SLUG}.wav"
        wav.parent.mkdir(parents=True)
        wav.write_bytes(b"audio")
        notices: list[Notice] = []
        assert not workfiles._usable(wav, "sha256:abc", {"sr": 48000}, notices)  # no sidecar
        workfiles.sidecar_path(wav).write_text(
            json.dumps({"qhash": "sha256:abc", "params": {"sr": 48000}}), encoding="utf-8"
        )
        assert workfiles._usable(wav, "sha256:abc", {"sr": 48000}, notices)
        assert notices == []

    def test_notice_no_slug_ingest_names_the_old_wav16_by_its_class_and_clip(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`ingest` looks at the wav16 of the last run; if its sidecar is damaged it is made again
        and the notice names it. `stage_wav16` and the peak are replaced: no ffmpeg."""
        raw = project.root / "crudo" / "Ana Perez 809-555-1234.mp4"
        raw.write_bytes(b"footage")
        digest = qhash(raw)
        old = project.layout.wav16 / f"a1_{SLUG}.wav"
        old.write_bytes(b"audio")
        workfiles.sidecar_path(old).write_text("{no", encoding="utf-8")
        known = Clip(
            "a1",
            "crudo/Ana Perez 809-555-1234.mp4",
            SLUG,
            "video_voz",
            digest,
            7,
            work=WorkFiles(None, f".kcut/wav16/a1_{SLUG}.wav", 540, 960),
        )
        staged = project.layout.wav16 / "stage-fake.wav"
        monkeypatch.setattr(workfiles, "stage_wav16", lambda *_a, **_k: staged)
        monkeypatch.setattr("kcut.ingest.examine.wav_peak", lambda _p: 0.5)
        item = Found(rel="crudo/Ana Perez 809-555-1234.mp4", path=raw, size=7, hash=digest)
        notices: list[Notice] = []
        _audio_peak(project, item, {digest: known}, project.root / "log.txt", notices)
        assert [(n.code, n.detail) for n in notices] == [
            ("cache_rebuilt", f"wav16 de a1: {DAMAGED}")
        ]
        assert _clean(notices[0]) and item.wav == staged
