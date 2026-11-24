"""The contact sheet of `kcut qa`, made so that it never shows the text of the transcript raw
(spec S1.9a; 001.39 D19, 001.40, 001.41).

`salida/vN.mp4` has the subtitles burned in as the words were said, raw, and Claude reads the
contact sheet. What the MP4 holds can come from other graphics, other settings or another
transcript than the ones of now, so with `privacy.mask_pii = true` not one frame of the sheet is
taken from it: every cell is the frame of the cut made from the proxy (`render.preview.base_frame`:
the same crop, zoom, look and fades as the render), and the ones that fall where the graphics of
the version are drawn (`active_frames` of `gfx.resolve`, no Chromium) have the page of the graphics
over it, blended by `gfx/still.py` as `kcut graphics still` does. The page is the masked one
(`masked=True`: the subtitles come out of `shown`, which has the phone numbers and the like
hidden). The `params` of the cues stay as Claude wrote them, as in `graphics still` and in S1.6a.

With `privacy.mask_pii = false` every frame comes from the video and the report says `pii_unmasked`.
If a cell cannot be made (Chromium is not there or fails, the proxy is not there,
`edit/graphics.json` cannot be read) the sheet is not written, whatever cells were made: the
report gets the warning `contact_skipped` with a fixed text, and the other checks. It never falls
back to the frame of the video, which has the raw text.

The page is written where `graphics still` writes it, `.kcut/build/vN/gfx/stills_work/page.html`,
and nowhere else; the PNGs of Chromium and the frames are only in memory. Each cell is reduced as
soon as it is made.
"""

from collections.abc import Iterator, Sequence
from pathlib import Path

from PIL import Image

from kcut.edl.model import Edl
from kcut.errors import MissingDependency, ProjectError, ToolError
from kcut.gfx import capture as gfx_capture
from kcut.gfx.capture import OnShot
from kcut.gfx.layer import GFX_DIR, folder_guard, page_for
from kcut.gfx.resolve import ResolvedGraphics, resolve
from kcut.gfx.still import STILLS_WORK, compose, decode_layer
from kcut.ingest.cache_guard import build_folder
from kcut.ingest.inventory import Inventory, Notice
from kcut.pack.pii import UNMASKED
from kcut.project import Project
from kcut.qa.contact import cell_of, cell_size, cells_jpeg, contact_frames, contact_jpeg
from kcut.render.frame_fx import fx_context
from kcut.render.preview import base_frame

SKIPPED_CODE = "contact_skipped"
CHROMIUM_ES = (
    "no se pudo dibujar un frame con gráficos (Chromium no está o falló): "
    "la hoja de contacto no se escribió; corre kcut doctor"
)
PROXY_ES = (
    "no se pudo armar un frame desde el proxy: "
    "la hoja de contacto no se escribió; corre kcut ingest"
)
GRAPHICS_ES = (
    "edit/graphics.json no se puede leer; la hoja de contacto no se escribió; "
    "corre kcut graphics check"
)


class SheetSkipped(Exception):
    """A cell of the sheet cannot be made, so the sheet is not written. `reason_es` is the fixed
    text for the report: nothing that came from the file, the proxy or Chromium is in it."""

    def __init__(self, reason_es: str) -> None:
        super().__init__(reason_es)
        self.reason_es = reason_es


def contact_sheet(
    project: Project,
    edl: Edl,
    version: int,
    inventory: Inventory,
    video: Path,
    frames: int,
    size: tuple[int, int],
    notices: list[Notice],
    log: Path | None,
) -> bytes | None:
    """The JPEG of the sheet of `video` (which has `frames` and is `size` = `(width, height)`), or
    `None` if a cell could not be made (then `notices` has `contact_skipped`).

    With `privacy.mask_pii = false`: the frames of the video, and `pii_unmasked`. Otherwise: no
    frame of the video (see the module). The sheet has a place for each 2 s of the video, or of
    the EDL if that is shorter: the proxy has nothing past the cut."""
    if not project.config.privacy.mask_pii:
        notices.append(Notice("pii_unmasked", UNMASKED))
        return contact_jpeg(video, frames, edl.fps, size, log)
    length = min(frames, edl.frames)
    cells = masked_cells(
        project, edl, version, inventory, contact_frames(length, edl.fps), cell_size(*size),
        notices, log,
    )  # fmt: skip
    try:
        return cells_jpeg(cells, length, edl.fps, size)
    except SheetSkipped as skip:
        notices.append(Notice(SKIPPED_CODE, skip.reason_es))
        return None


def masked_cells(
    project: Project,
    edl: Edl,
    version: int,
    inventory: Inventory,
    sheet_frames: Sequence[int],
    cell: tuple[int, int],
    notices: list[Notice],
    log: Path | None,
) -> Iterator[Image.Image]:
    """The cell of each frame of `sheet_frames`, in order, one at a time: the frame from the proxy,
    with the masked page of the graphics over it where there are graphics. A folder of the cache
    that is a link is a ProjectError (exit 3), as everywhere that kcut writes in `.kcut/`; a cell
    that cannot be made is `SheetSkipped`."""
    try:
        resolved = resolve(project, edl, version, inventory=inventory, log=log)
    except ProjectError:  # the file cannot be read; what it says is not repeated
        raise SheetSkipped(GRAPHICS_ES) from None
    notices.extend(resolved.notices)
    live = set(gfx_capture.active_frames(resolved))
    ctx = fx_context(project, edl)
    size = (edl.out_w, edl.out_h)

    def one(f: int, shot: bytes | None) -> Image.Image:
        try:
            base = base_frame(project, edl, inventory, f, ctx, log=log)
        except (ProjectError, ToolError):
            raise SheetSkipped(PROXY_ES) from None
        if shot is not None:
            try:
                base = compose(base, decode_layer(shot, size))
            except ToolError:
                raise SheetSkipped(CHROMIUM_ES) from None
        return cell_of(base, cell)

    made: dict[int, Image.Image] = {}  # the cells of the frames with graphics: small, not the PNGs

    def on_shot(f: int, shot: bytes) -> None:
        made[f] = one(f, shot)  # the PNG is used here and not kept (001.47, point 1)

    _shoot(project, edl, version, resolved, [f for f in sheet_frames if f in live], on_shot)
    for f in sheet_frames:
        yield made.pop(f) if f in made else one(f, None)


def _shoot(
    project: Project,
    edl: Edl,
    version: int,
    resolved: ResolvedGraphics,
    wanted: list[int],
    on_shot: OnShot,
) -> None:
    """Hand the PNG that Chromium draws for each frame of `wanted` (the masked page) to `on_shot`,
    one at a time and as soon as it is made; nothing if `wanted` is empty. The folders go through
    `folder_guard` (a link there is a ProjectError)."""
    if not wanted:
        return
    build = build_folder(project, version)
    work = build / GFX_DIR / STILLS_WORK
    guard = folder_guard(project, build, build / GFX_DIR, work)
    try:
        gfx_capture.capture_stills(
            page_for(resolved, masked=True), work, wanted, edl.fps, (edl.out_w, edl.out_h), work,
            None, on_shot=on_shot, guard=guard,
        )  # fmt: skip
    except (MissingDependency, ToolError):
        raise SheetSkipped(CHROMIUM_ES) from None
