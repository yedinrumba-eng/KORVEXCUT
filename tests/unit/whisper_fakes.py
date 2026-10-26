"""A stand-in for faster-whisper's `WhisperModel`: records how it is built and called."""

import sys
import types
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest


class FakeWhisper:
    """Records how it was built and called; answers with `segments` and `info`."""

    built: ClassVar[list[tuple[str, dict[str, Any]]]] = []
    asked: ClassVar[list[tuple[str, dict[str, Any]]]] = []
    segments: ClassVar[list[Any]] = []
    info: ClassVar[Any] = SimpleNamespace(language="es", language_probability=0.9766)
    failure: ClassVar[BaseException | None] = None

    def __init__(self, model: str, **kwargs: Any) -> None:
        if self.failure is not None:
            raise self.failure
        self.built.append((model, kwargs))

    def transcribe(self, audio: str, **kwargs: Any) -> tuple[Any, Any]:
        self.asked.append((audio, kwargs))
        return iter(self.segments), self.info


def install_whisper(monkeypatch: pytest.MonkeyPatch) -> type[FakeWhisper]:
    """Put a stand-in `faster_whisper` in place, so the real library is never even imported."""

    class Fresh(FakeWhisper):
        built: ClassVar[list[tuple[str, dict[str, Any]]]] = []
        asked: ClassVar[list[tuple[str, dict[str, Any]]]] = []
        segments: ClassVar[list[Any]] = []
        failure: ClassVar[BaseException | None] = None

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = Fresh  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    return Fresh


def word(text: str, start: float, end: float, p: float = 0.9) -> Any:
    return SimpleNamespace(word=text, start=start, end=end, probability=p)


def segment(start: float, end: float, text: str, *words: Any) -> Any:
    return SimpleNamespace(start=start, end=end, text=text, words=list(words))
