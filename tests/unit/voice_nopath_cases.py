"""The voice and the name of the clip (spec S1.6a step 0, 001.27 point 9, and round 2, 001.28
point 2; rows 20 and 23): while the voice is made, no error message carries the path of the wav48 or
the `str()` of an `OSError`, because the path has the slug of the original name of the clip and that
name may have a phone number in it.

Collected from `test_wavio_f32.py`, as `test_voice_track.py` is at the 300-line limit. The
`streamed` fixture is the one of `voice_stream_cases.py`.

001.28: these tests used to replace `voice_track.read_wav_range`, and they passed although no
`OSError` ever came out of it. Now nothing of `wavio` is replaced: a real wav48, named as `ingest`
names it, is deleted before it is read, or `wave.open` is what fails.
"""

import dataclasses
import shutil
import wave
from pathlib import Path

import pytest

from kcut.audio.voice_track import write_voice
from kcut.errors import ProjectError
from kcut.ingest import workfiles
from kcut.ingest.inventory import Inventory
from tests.unit.edl_fakes import inventory, parsed
from tests.unit.voice_stream_cases import Streamed, streamed

__all__ = ["TestVoiceReadNoPath", "streamed"]
SLUG = "ana-perez-809-555-1234"  # of `Ana Perez 809-555-1234.mp4`, as `ingest` makes it
LEAKS = ("809", "555", "1234", "ana", "perez", SLUG, ":\\")


def _phone_in_the_name() -> Inventory:
    """The fake inventory with a1 as `crudo/Ana Perez 809-555-1234.mp4`."""
    inv = inventory()
    clips = tuple(
        dataclasses.replace(c, file="crudo/Ana Perez 809-555-1234.mp4", slug=SLUG)
        if c.id == "a1"
        else c
        for c in inv.clips
    )
    return dataclasses.replace(inv, clips=clips)


class TestVoiceReadNoPath:
    @staticmethod
    def _wav48(streamed: Streamed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """A real wav48 of `a1`, with the name `ingest` gives it, which `ensure_wav48` hands out."""
        wav = tmp_path / "wav48" / f"a1_{SLUG}.wav"
        wav.parent.mkdir()
        shutil.copy(streamed.wav, wav)
        monkeypatch.setattr(workfiles, "ensure_wav48", lambda *_a, **_k: wav)
        return wav

    @staticmethod
    def _message(streamed: Streamed, tmp_path: Path) -> str:
        with pytest.raises(ProjectError) as info:
            write_voice(streamed.project, parsed(), _phone_in_the_name(), tmp_path / "v.f32", None)
        assert info.value.exit_code == 3
        return info.value.message_es

    # 001.28: it patched `read_wav_range`; now a real wav48 is deleted before it is read
    def test_voice_read_no_path_wav_no_path_a_wav48_deleted_before_it_is_read(
        self, streamed: Streamed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wav = self._wav48(streamed, tmp_path, monkeypatch)

        def gone(*_a: object, **_k: object) -> Path:
            wav.unlink()  # `ensure_wav48` said it was there; it is not when it is read
            return wav

        monkeypatch.setattr(workfiles, "ensure_wav48", gone)
        message = self._message(streamed, tmp_path)
        assert message == "no pude leer el wav48 de a1: No such file or directory"
        assert not any(piece in message.lower() for piece in LEAKS)

    # 001.28: it patched `read_wav_range`; now `wave.open` is what raises the PermissionError
    def test_voice_read_no_path_wav_no_path_a_wav48_that_is_refused_by_wave_open(
        self, streamed: Streamed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wav = self._wav48(streamed, tmp_path, monkeypatch)
        error = PermissionError(13, "Permission denied", str(wav))
        assert "809" in str(error)  # the trap: `str()` of the error has the path

        def refused(*_a: object, **_k: object) -> None:
            raise error

        monkeypatch.setattr(wave, "open", refused)
        message = self._message(streamed, tmp_path)
        assert message == "no pude leer el wav48 de a1: Permission denied"
        assert not any(piece in message.lower() for piece in LEAKS)

    # 001.28: it patched `read_wav_range`; now `wave.open` raises an error with no `strerror`
    def test_voice_read_no_path_wav_no_path_an_error_with_no_system_message_says_its_class(
        self, streamed: Streamed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._wav48(streamed, tmp_path, monkeypatch)

        def refused(*_a: object, **_k: object) -> None:
            raise FileNotFoundError("Ana Perez 809-555-1234.wav")  # no `strerror`

        monkeypatch.setattr(wave, "open", refused)
        message = self._message(streamed, tmp_path)
        assert message == "no pude leer el wav48 de a1: FileNotFoundError"
        assert not any(piece in message.lower() for piece in LEAKS)
