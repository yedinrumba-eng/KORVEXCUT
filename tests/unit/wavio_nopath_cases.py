"""The readers of `wavio` never name a file by its path (spec 001.28, point 2; row 23).

Each of the seven readers gets `label`, the phrase that names the file (`el wav48 de a1`), and every
message it raises carries that phrase and nothing of the path or of `str()` of the `OSError`: the
name of the wav48 holds the slug of the original clip, and the slug may hold a phone number. Nothing
of `wavio` is replaced: real files, the real `wave`, the real `OSError` of the system.

Collected from `test_wavio_f32.py`. The half about the work files is in `workfiles_nopath_cases.py`
and the one about the voice is in `voice_nopath_cases.py`.
"""

import wave
from collections.abc import Callable
from pathlib import Path

import pytest

from kcut.audio.wavio import (
    check_wav_extent,
    open_wav,
    read_f32,
    read_wav_range,
    read_wav_s16_mono,
    wav_duration_ms,
    wav_peak,
)
from kcut.errors import ProjectError
from tests.unit.transcribe_fakes import riff_bytes
from tests.unit.wav_fakes import FMT, PCM, chunk, fmt, wav

__all__ = ["TestWavNoPathReaders"]
LABEL = "el wav48 de a1"
NAME = "a1_ana-perez-809-555-1234.wav"
LEAKS = ("ana", "perez", "809", "555", "1234", ":\\")


def _open(path: Path, label: str) -> None:
    with open_wav(path, label=label):
        pass


READERS: dict[str, Callable[[Path, str], object]] = {
    "check_wav_extent": lambda p, label: check_wav_extent(p, label=label),
    "open_wav": _open,
    "read_wav_s16_mono": lambda p, label: read_wav_s16_mono(p, label=label),
    "read_wav_range": lambda p, label: read_wav_range(p, 0, 100, label=label),
    "wav_duration_ms": lambda p, label: wav_duration_ms(p, label=label),
    "wav_peak": lambda p, label: wav_peak(p, label=label),
    "read_f32": lambda p, label: read_f32(p, label=label),
}
WAV_READERS = [name for name in READERS if name != "read_f32"]
# the ones that open the file with `wave` (`check_wav_extent` only looks at the header itself)
WAVE_OPENERS = [name for name in WAV_READERS if name != "check_wav_extent"]

# what is in the file when the header is wrong: a header that says more data than there is, and a
# header that is cut short
LYING = riff_bytes(0xFFFFFFF0, b"\0" * 100)
CUT = b"RIFF\x00\x00\x00\x00WAVEfmt "
STEREO = wav([chunk(b"fmt ", fmt(ch=2, ba=4)), chunk(b"data", PCM)])


class TestWavNoPathReaders:
    @staticmethod
    def _path(tmp_path: Path) -> Path:
        path = tmp_path / "wav48" / NAME
        path.parent.mkdir()
        return path

    @staticmethod
    def _message(
        call: Callable[[Path, str], object],
        path: Path,
        label: str = LABEL,
        leaks: tuple[str, ...] = LEAKS,
    ) -> str:
        with pytest.raises(ProjectError) as info:
            call(path, label)
        message = info.value.message_es
        assert message.startswith(label) or f" {label}" in message  # it names the file by its label
        assert not any(piece in message.lower() for piece in leaks), message
        return message

    @pytest.mark.parametrize("name", READERS)
    def test_wav_no_path_a_file_that_does_not_exist(self, tmp_path: Path, name: str) -> None:
        message = self._message(READERS[name], self._path(tmp_path))
        assert message == f"no pude leer {LABEL}: No such file or directory"

    @pytest.mark.parametrize("name", READERS)
    def test_wav_no_path_a_folder_where_the_file_goes(self, tmp_path: Path, name: str) -> None:
        path = self._path(tmp_path)
        path.mkdir()
        message = self._message(READERS[name], path)
        assert message.startswith(f"no pude leer {LABEL}: ")

    @pytest.mark.parametrize("name", WAV_READERS)
    def test_wav_no_path_a_header_that_says_more_data_than_the_file_has(
        self, tmp_path: Path, name: str
    ) -> None:
        path = self._path(tmp_path)
        path.write_bytes(LYING)
        message = self._message(READERS[name], path)
        assert message == f"{LABEL} está truncado o su cabecera miente; corre kcut ingest"

    @pytest.mark.parametrize("name", WAVE_OPENERS)
    def test_wav_no_path_a_header_that_is_cut_short(self, tmp_path: Path, name: str) -> None:
        path = self._path(tmp_path)
        path.write_bytes(CUT)  # `wave` refuses it, with its own text (no path in it)
        message = self._message(READERS[name], path)
        assert (
            message.startswith(f"no pude leer {LABEL}: ") and message != f"no pude leer {LABEL}: "
        )

    def test_wav_no_path_read_f32_with_a_size_that_is_not_float32(self, tmp_path: Path) -> None:
        path = self._path(tmp_path)
        path.write_bytes(b"1234567")
        message = self._message(READERS["read_f32"], path)
        assert message == f"{LABEL}: tamaño inválido para float32 (7 bytes)"

    @pytest.mark.parametrize("name", ["read_wav_s16_mono", "read_wav_range", "wav_peak"])
    def test_wav_no_path_a_wav_that_is_not_mono_16_bits(self, tmp_path: Path, name: str) -> None:
        path = self._path(tmp_path)
        path.write_bytes(STEREO)
        message = self._message(READERS[name], path, leaks=LEAKS[1:])  # "canales" has an `ana`
        assert message == f"{LABEL}: se esperaba un wav mono de 16 bits (tiene 2 canales y 16 bits)"

    def test_wav_no_path_a_wav_with_a_zero_sample_rate(self, tmp_path: Path) -> None:
        path = self._path(tmp_path)
        path.write_bytes(wav([chunk(b"fmt ", fmt(rate=0)), chunk(b"data", PCM)]))
        message = self._message(READERS["wav_duration_ms"], path)
        assert message == f"{LABEL}: la frecuencia de muestreo es 0"

    @pytest.mark.parametrize("name", WAVE_OPENERS)
    @pytest.mark.parametrize(
        ("kind", "reason"),
        [
            ("PermissionError", "Permission denied"),
            ("wave.Error", "unknown format: 3"),
            ("RuntimeError", "RuntimeError"),  # any other error says only its class
        ],
    )
    def test_wav_no_path_a_wave_that_fails_says_its_text_and_never_the_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, kind: str, reason: str
    ) -> None:
        path = self._path(tmp_path)
        path.write_bytes(wav([chunk(b"fmt ", FMT), chunk(b"data", PCM)]))
        errors: dict[str, Exception] = {
            "PermissionError": PermissionError(13, "Permission denied", str(path)),
            "wave.Error": wave.Error("unknown format: 3"),
            "RuntimeError": RuntimeError(f"cannot seek in {path}"),  # the trap: it has the path
        }

        def boom(*_a: object, **_k: object) -> None:
            raise errors[kind]

        monkeypatch.setattr(wave, "open", boom)
        message = self._message(READERS[name], path)
        assert message == f"no pude leer {LABEL}: {reason}"

    def test_wav_no_path_the_default_labels_name_a_wav_and_an_audio(self, tmp_path: Path) -> None:
        path = self._path(tmp_path)
        with pytest.raises(ProjectError) as wav_error:
            wav_duration_ms(path)
        with pytest.raises(ProjectError) as audio_error:
            read_f32(path)
        assert wav_error.value.message_es == "no pude leer el wav: No such file or directory"
        assert audio_error.value.message_es == "no pude leer el audio: No such file or directory"
