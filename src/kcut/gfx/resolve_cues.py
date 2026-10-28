"""The cues and the hidden windows of a `graphics.json`, one by one: their parameters, their
images and their moments, in output frames (spec S1.6a). Split from `resolve.py` by the 300-line
rule; `resolve.py` is the entry point and the shape of what is drawn.

A moment that cannot be found is an error of the cue that uses it (G04 a word that the cut does
not keep, G05 a frame of a source that is not heard), a source frame heard more than once is a
warning (G06, the first is used) and a cue that does not fit in the video is G07. A message never
repeats text of the file.
"""

from dataclasses import dataclass
from typing import Any

from kcut.anchors import resolve_time
from kcut.edl.kept import KeptWords
from kcut.edl.model import Edl
from kcut.errors import GateError, ProjectError
from kcut.gfx import assets
from kcut.gfx.assets import image_data_uri
from kcut.gfx.captions import hide_window
from kcut.gfx.components import COMPONENTS, time_warnings, validate_params
from kcut.gfx.schema import CueDoc, GraphicsDoc
from kcut.issues import Issue
from kcut.params import ParamSpec
from kcut.project import Project
from kcut.schema_util import describe_value


@dataclass(frozen=True)
class ResolvedCue:
    """A cue of `graphics.json` after resolving: output frames `[start_f, end_f)` and its
    `params` checked, with their defaults and their colors in hex."""

    id: str
    component: str
    start_f: int
    end_f: int
    params: dict[str, object]


class Worker:
    """Resolves the windows and the cues of one document against one EDL. The problems go to
    `issues` (the list of the result); the images that cues use are kept in `images`."""

    def __init__(self, project: Project, edl: Edl, kept: KeptWords, issues: list[Issue]) -> None:
        self._project = project
        self._edl = edl
        self._kept = kept
        self._issues = issues
        self._image_bytes = 0  # what `images` weighs, as the page will carry it (001.33, point 8)
        self.images: dict[str, str] = {}

    def windows(self, doc: GraphicsDoc) -> list[tuple[int, int]]:
        """The `captions.hide` windows that resolve and fit in the video."""
        found = [self._span(w.start, w.end, f"captions.hide[{w.index}]") for w in doc.hide]
        return [span for span in found if span is not None]

    def cues(self, doc: GraphicsDoc) -> tuple[list[ResolvedCue], list[tuple[int, int]]]:
        """The cues without a problem, in order, and the windows in which they hide the
        subtitles (`captions.hide_window`: `hide_captions`, which is `big` by default)."""
        cues: list[ResolvedCue] = []
        windows: list[tuple[int, int]] = []
        for doc_cue in doc.cues:
            found = self._cue(doc_cue)
            if found is None:
                continue
            cues.append(found)
            hides = (
                COMPONENTS[found.component].big
                if doc_cue.hide_captions is None
                else doc_cue.hide_captions
            )
            if hides:
                windows.append(hide_window(found.start_f, found.end_f, self._edl.fps))
        return cues, windows

    def _cue(self, cue: CueDoc) -> ResolvedCue | None:
        where = f"cues[{cue.index}]"
        before = len(self._issues)
        component = COMPONENTS[cue.component]
        brand = self._project.config.brand
        params, found = validate_params(component, cue.params, f"{where}.params", brand)
        self._issues.extend(found)
        self._use_images(component.params, params, f"{where}.params")
        span = self._span(cue.start, cue.end, where)
        failed = any(i.level == "error" for i in self._issues[before:])
        if span is None or failed:
            return None
        length = span[1] - span[0]  # 001.35, point 9: times that fall where nobody will see them
        self._issues.extend(
            time_warnings(component, params, length, self._edl.fps, f"{where}.params")
        )
        return ResolvedCue(cue.id, cue.component, span[0], span[1], params)

    def _span(self, start: object, end: object, path: str) -> tuple[int, int] | None:
        """`[start, end)` in output frames, or `None` (with its issue) if a moment is not found
        or the span does not satisfy `0 <= start < end <= frames`."""
        first = self._moment(start, f"{path}.start")
        last = self._moment(end, f"{path}.end")
        if first is None or last is None:
            return None
        if not 0 <= first < last <= self._edl.frames:
            message = (
                f"queda en [{describe_value(first)}, {describe_value(last)}) y el video tiene "
                f"{self._edl.frames} frames: tiene que cumplirse 0 <= start < end <= frames"
            )
            self._issues.append(Issue("G07", "error", path, message))
            return None
        return first, last

    def _moment(self, value: object, path: str) -> int | None:
        found = resolve_time(value, self._kept.words, self._edl)
        if found.problem == "word_not_kept":
            message = "la palabra no está entre las que conserva el corte"
            self._issues.append(Issue("G04", "error", path, message))
        elif found.problem == "src_not_heard":
            message = "ese frame del clip no se oye en la salida"
            self._issues.append(Issue("G05", "error", path, message))
        elif found.problem is not None or found.frame is None:
            self._issues.append(Issue("G01", "error", path, "no es un frame ni un ancla"))
        else:
            if found.repeats > 1:
                message = f"ese frame del clip se oye {found.repeats} veces: se usa la primera"
                self._issues.append(Issue("G06", "warning", path, message))
            return found.frame
        return None

    def _use_images(self, specs: tuple[ParamSpec, ...], params: dict[str, Any], path: str) -> None:
        """Put in the page every image the parameters name (G09 / G10 if one cannot be used)."""
        for spec in specs:
            value = params.get(spec.name)
            where = f"{path}.{spec.name}"
            if spec.kind == "path" and isinstance(value, str):
                self._image(value, where)
            elif spec.kind == "list" and spec.item is not None and isinstance(value, list):
                for i, element in enumerate(value):
                    if isinstance(element, dict):
                        self._use_images(spec.item, element, f"{where}[{i}]")

    def _image(self, rel: str, path: str) -> None:
        if rel in self.images:
            return
        try:
            uri = image_data_uri(self._project, rel)
        except GateError as exc:
            self._issues.append(Issue("G10", "error", path, exc.message_es))
            return
        except ProjectError as exc:
            self._issues.append(Issue("G09", "error", path, exc.message_es))
            return
        size = assets.uri_bytes(uri)
        if self._image_bytes + size > assets.MAX_PAGE_IMAGE_BYTES:  # the cue that crosses it
            self._issues.append(Issue("G09", "error", path, assets.PAGE_IMAGES_TOO_BIG))
            return
        self._image_bytes += size
        self.images[rel] = uri
