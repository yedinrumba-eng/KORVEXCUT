"""From `edit/graphics.json` and the EDL to what is drawn: validated cues in output frames, colors
in hex, images inside the page and the subtitle chunks (spec S1.6a, 001.15 point 40).

`resolve` does not raise for a mistake in the file: every problem is an `Issue` in the result (the
codes G01-G12) and a cue with a problem is left out. It does raise `ProjectError` for a file that
cannot be read (a folder, broken JSON), like everything that reads a file of the user. The text of
the subtitles is raw in `chunks` (it goes to the MP4) and masked in `shown` (it goes to Claude).
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from kcut.config.model import BrandSection, CaptionsSection
from kcut.edl.kept import KeptWords, kept_words
from kcut.edl.model import Edl
from kcut.gfx.captions import Chunk, build_chunks, shown_chunks
from kcut.gfx.resolve_cues import ResolvedCue, Worker
from kcut.gfx.schema import GraphicsDoc, default_doc, parse_graphics
from kcut.ingest.inventory import Inventory, Notice
from kcut.issues import Issue
from kcut.jsonio import read_json
from kcut.pack.pii import UNMASKED
from kcut.paths import resolve_in_project
from kcut.project import Project, load_inventory

GRAPHICS_REL = "edit/graphics.json"
MAX_GRAPHICS_BYTES = 1024 * 1024  # as `MAX_EDL_BYTES`: a bigger file is refused unread (001.28)
CAPTIONS_CUE_ID = "__captions__"
G11_TEXT = "no hay edit/graphics.json: subtítulos por defecto desde la transcripción"
G12_TEXT = "no hay edit/graphics.json y los subtítulos están apagados: el video sale sin gráficos"
G08_TEXT = "el clip {} no tiene transcripción: corre kcut transcribe o pon captions.enabled=false"


@dataclass(frozen=True)
class ResolvedGraphics:
    """Everything that is drawn for one EDL. `chunks` have the raw text of the words and `shown`
    the text Claude may read for each word id (the raw text when `masked` is false). `source` is
    `file` if `edit/graphics.json` exists and `default` for the implicit document; `captions`
    says the subtitles are on; `empty` says there is nothing to draw (no cues and no subtitles).
    `issues` has the errors and warnings; `notices` the warnings of the run (`pii_unmasked`)."""

    version: int
    source: Literal["file", "default"]
    fps: int
    w: int
    h: int
    frames: int
    brand: dict[str, str]
    captions: bool
    captions_cfg: CaptionsSection
    style: dict[str, object]
    cues: tuple[ResolvedCue, ...]
    chunks: list[Chunk]
    shown: dict[str, str]
    masked: bool
    images: dict[str, str]
    issues: list[Issue]
    notices: list[Notice]
    empty: bool

    @property
    def graphics_json(self) -> str | None:
        """The file that was read, or `None` for the implicit document."""
        return GRAPHICS_REL if self.source == "file" else None


def resolve(
    project: Project,
    edl: Edl,
    version: int,
    *,
    inventory: Inventory | None = None,
    log: Path | None = None,
) -> ResolvedGraphics:
    """Read `edit/graphics.json` (or take the implicit document), check it against `edl` and
    resolve it. `inventory` and `log` are the ones the command already has; without them the
    inventory is loaded here."""
    cfg = project.config
    issues: list[Issue] = []
    notices: list[Notice] = []
    path = project.layout.edit / "graphics.json"
    source: Literal["file", "default"] = "file" if os.path.lexists(path) else "default"
    doc: GraphicsDoc | None = default_doc()
    if source == "file":
        data = read_json(resolve_in_project(project.root, GRAPHICS_REL), MAX_GRAPHICS_BYTES)
        doc, found = parse_graphics(data)
        issues += found
    on = (
        cfg.captions.enabled
        if doc is None or doc.captions_enabled is None
        else doc.captions_enabled
    )
    if source == "default":
        issues.append(
            Issue("G11", "warning", "", G11_TEXT) if on else Issue("G12", "warning", "", G12_TEXT)
        )
    brand = _brand(cfg.brand)
    cues: tuple[ResolvedCue, ...] = ()
    chunks: list[Chunk] = []
    shown: dict[str, str] = {}
    images: dict[str, str] = {}
    if doc is not None:
        kept = _kept(project, edl, doc, on, inventory, notices, log)
        worker = Worker(project, edl, kept, issues)
        windows = worker.windows(doc)
        found_cues, cue_windows = worker.cues(doc)
        windows += cue_windows
        cues = tuple(found_cues)
        images = worker.images
        if on:
            issues += [Issue("G08", "error", "captions", G08_TEXT.format(i)) for i in kept.missing]
            chunks = build_chunks(kept.words, cfg.captions, windows, edl.fps)
            shown = kept.shown
    if not cfg.privacy.mask_pii and not any(n.code == "pii_unmasked" for n in notices):
        notices.append(Notice("pii_unmasked", UNMASKED))
    return ResolvedGraphics(
        version=version, source=source, fps=edl.fps, w=edl.out_w, h=edl.out_h, frames=edl.frames,
        brand=brand, captions=on, captions_cfg=cfg.captions, style=_style(cfg.captions, brand),
        cues=cues, chunks=chunks, shown=shown, masked=cfg.privacy.mask_pii, images=images,
        issues=issues, notices=notices, empty=not cues and not on,
    )  # fmt: skip


def data_json(resolved: ResolvedGraphics, *, masked: bool) -> dict[str, object]:
    """The `kc-data` of the page (S1.6a, see the spec for the shape). With `masked=False` (the
    capture for the render, the MP4) the chunks have the raw text; with `masked=True` (`graphics
    still` and the storyboard, which Claude reads) they have the text of `shown_chunks`. The
    `params` of the cues are the ones Claude wrote, checked: they are not masked here."""
    cues: list[dict[str, object]] = [
        {
            "id": c.id,
            "component": c.component,
            "start_f": c.start_f,
            "end_f": c.end_f,
            "params": c.params,
        }
        for c in resolved.cues
    ]
    if resolved.captions:
        chunks = (
            shown_chunks(resolved.chunks, resolved.shown, resolved.captions_cfg)
            if masked
            else resolved.chunks
        )
        params = {"style": resolved.style, "chunks": [chunk_json(c) for c in chunks]}
        cues.append(
            {
                "id": CAPTIONS_CUE_ID,
                "component": "captions",
                "start_f": 0,
                "end_f": resolved.frames,
                "params": params,
            }
        )
    return {
        "fps": resolved.fps,
        "w": resolved.w,
        "h": resolved.h,
        "frames": resolved.frames,
        "brand": resolved.brand,
        "images": resolved.images,
        "cues": cues,
    }


def chunk_json(chunk: Chunk) -> dict[str, object]:
    """A chunk as `kc-data` and `graphics check --json` show it."""
    words = [{"text": w.text, "s_f": w.s_f} for w in chunk.words]
    return {"s_f": chunk.s_f, "e_f": chunk.e_f, "words": words}


def _brand(brand: BrandSection) -> dict[str, str]:
    return {
        "accent": brand.accent,
        "accent2": brand.accent2,
        "dark": brand.dark,
        "light": brand.light,
    }


def _style(cfg: CaptionsSection, brand: dict[str, str]) -> dict[str, object]:
    """The look of the subtitles, from `kcut.toml [captions]`; an empty color is the brand's."""
    return {
        "y": cfg.y,
        "font_px": cfg.font_px,
        "color": cfg.color,
        "active_color": cfg.active_color or brand["accent2"],
        "stroke_color": cfg.stroke_color or brand["dark"],
    }


def _kept(
    project: Project,
    edl: Edl,
    doc: GraphicsDoc,
    captions_on: bool,
    inventory: Inventory | None,
    notices: list[Notice],
    log: Path | None,
) -> KeptWords:
    """The kept words, if something needs them: the subtitles, or an anchor that names a word."""
    values = [v for w in doc.hide for v in (w.start, w.end)] + [
        v for c in doc.cues for v in (c.start, c.end)
    ]
    if not captions_on and not any(isinstance(v, dict) and "word" in v for v in values):
        return KeptWords(words=[], shown={}, missing=(), masked=project.config.privacy.mask_pii)
    inv = inventory if inventory is not None else load_inventory(project, log)
    return kept_words(project, edl, inv, notices=notices, log=log)
