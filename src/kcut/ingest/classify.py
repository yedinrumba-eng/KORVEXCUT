"""Decide what each raw file is and give it a stable id (`a1`, `b1`, `s1`, `i1`, `d1`, `u1`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from kcut.errors import ProjectError

if TYPE_CHECKING:
    from kcut.ingest.inventory import Inventory
    from kcut.ingest.probe import MediaInfo

ClipClass = Literal["video_voz", "video_mudo", "audio", "imagen", "doc", "desconocido"]

DOC_EXT: Final = frozenset({".txt", ".md", ".pdf", ".doc", ".docx", ".rtf", ".odt"})
IMG_EXT: Final = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"})
SPEECH_MIN_PEAK_DBFS: Final = -60.0
ID_HIGH_MAX: Final = 999_998  # every id issued (a + up to 6 digits) passes the validator
ID_PREFIX: Final[dict[ClipClass, str]] = {
    "video_voz": "a",
    "video_mudo": "b",
    "audio": "s",
    "imagen": "i",
    "doc": "d",
    "desconocido": "u",
}


@dataclass(frozen=True)
class NewFile:
    """A scanned file waiting for an id: project-relative POSIX path, quick hash and class."""

    rel: str
    qhash: str
    clip_class: ClipClass


def classify(ext: str, info: MediaInfo | None, audio_peak_dbfs: float | None) -> ClipClass:
    """Class by extension first, then by streams; audible speech needs a peak above -60 dBFS."""
    extension = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
    if extension in DOC_EXT:
        return "doc"
    if extension in IMG_EXT:
        return "imagen"
    if info is None:
        return "desconocido"
    if info.video is not None:
        audible = (
            info.audio is not None
            and audio_peak_dbfs is not None
            and audio_peak_dbfs > SPEECH_MIN_PEAK_DBFS
        )
        return "video_voz" if audible else "video_mudo"
    if info.audio is not None:
        return "audio"
    return "desconocido"


def assign_ids(
    files: list[NewFile], previous: Inventory | None
) -> tuple[dict[str, str], dict[str, int]]:
    """Map `rel` -> id, and the new `id_high`. Ids are never reused.

    A file finds its previous clip first by (`qhash`, `file`), then by `qhash` alone (so a rename
    keeps the id); either way the id prefix must still match the class. Everything else gets
    `id_high[prefix] + 1`, in case-insensitive path order. A vanished id stays retired.
    """
    ordered = sorted(files, key=lambda f: (f.rel.casefold(), f.rel))
    old = list(previous.clips) if previous is not None else []
    high: dict[str, int] = dict(previous.id_high) if previous is not None else {}
    for clip in old:
        high[clip.id[0]] = max(high.get(clip.id[0], 0), int(clip.id[1:]))
    result: dict[str, str] = {}
    taken: set[str] = set()
    for exact in (True, False):
        for f in ordered:
            if f.rel in result:
                continue
            for clip in old:
                free = clip.id not in taken and clip.id[0] == ID_PREFIX[f.clip_class]
                if free and clip.qhash == f.qhash and (not exact or clip.file == f.rel):
                    result[f.rel] = clip.id
                    taken.add(clip.id)
                    break
    for f in ordered:
        if f.rel not in result:
            prefix = ID_PREFIX[f.clip_class]
            if high.get(prefix, 0) >= ID_HIGH_MAX:
                raise ProjectError(
                    f"se agotaron los ids del prefijo {prefix!r} ({ID_HIGH_MAX}); "
                    "rehaz el proyecto con kcut new"
                )
            high[prefix] = high.get(prefix, 0) + 1
            result[f.rel] = f"{prefix}{high[prefix]}"
    return result, high
