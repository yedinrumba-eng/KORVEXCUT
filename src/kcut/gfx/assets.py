"""The images a graphic may use, as data URIs for the page (spec S1.6a, DS9).

The page is loaded from a file with the network blocked, so an image cannot be a URL: it goes
inside the page. Only what `recursos/recursos.json` lists and a person approved (DS9), only
`.png`, `.webp`, `.jpg` and `.jpeg` (SVG can carry scripts and links), and nothing that is not
really an image of the format its extension says, of at most 4096 x 4096 pixels (001.28). A
WebP says its size in the RIFF header, and that is read before Pillow opens it (001.30).
"""

import base64
import io
from pathlib import Path

from PIL import Image

from kcut.errors import ProjectError
from kcut.jsonio import read_capped
from kcut.paths import resolve_in_project, to_rel
from kcut.project import Project
from kcut.recursos.manifest import require_approved

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_ASSET_PIXELS = 4096 * 4096  # width x height, read from the header before the image is decoded
WEBP_HEADER_BYTES = 30  # all the RIFF header of a WebP needs to say its size
MIME = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
# The format Pillow may open each extension as: a file is never opened as something else
FORMATS = {".png": "PNG", ".webp": "WEBP", ".jpg": "JPEG", ".jpeg": "JPEG"}
BAD_IMAGE = "Pillow no puede abrir la imagen: no es una imagen válida del formato de su extensión"
TOO_MANY_PIXELS = "la imagen tiene más de 4096 x 4096 píxeles; kcut no la usa"
FOLDER = "recursos/"


def image_data_uri(project: Project, rel: str) -> str:
    """`data:<mime>;base64,<bytes>` of the image `rel` (a path relative to the project).

    ProjectError (code G09) if the path does not stay in the project or does not begin with
    `recursos/`, if the extension is not allowed, if the file is over 20 MB, if it is over
    4096 x 4096 pixels or if Pillow cannot open it as the format of its extension (001.28).
    GateError (code G10, exit 5) if the file is not in the manifest of resources or has
    no `approved_by` (`require_approved`)."""
    try:
        path = resolve_in_project(project.root, rel)
        normalized = to_rel(project.root, path)
    except ProjectError:  # the message of the path check quotes the path: it is not repeated
        raise ProjectError(
            "la ruta de la imagen no vale: relativa al proyecto, sin .., sin letra de unidad "
            "y sin nombres reservados de Windows"
        ) from None
    if not normalized.startswith(FOLDER):
        raise ProjectError(f"la imagen tiene que estar en {FOLDER}")
    suffix = path.suffix.lower()
    mime = MIME.get(suffix)
    if mime is None:
        raise ProjectError("la imagen tiene que ser .png, .webp, .jpg o .jpeg (SVG no se usa)")
    require_approved(project, normalized)
    data = _read(path)
    _opens(data, FORMATS[suffix])
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _read(path: Path) -> bytes:
    try:
        return read_capped(path, MAX_IMAGE_BYTES)
    except ProjectError:  # `read_capped`: over the cap, or it grew while it was read
        raise ProjectError("la imagen pesa más de 20 MB o cambió mientras se leía") from None
    except OSError:
        raise ProjectError("no pude leer la imagen") from None


def _webp_pixels(data: bytes) -> int | None:
    """Width x height that the RIFF header of a WebP declares, read from its first 30 bytes, or
    `None` if the header is none of the three kinds (`VP8 ` lossy, `VP8L` lossless, `VP8X`
    extended). Pillow reserves the whole canvas when it opens a WebP, before anyone looks at the
    pixels: a file of 32 bytes that says 16384 x 16384 made it ask for 2 GB (001.30, point 3)."""
    head = data[:WEBP_HEADER_BYTES]
    if len(head) < 21 or head[:4] != b"RIFF" or head[8:12] != b"WEBP":
        return None
    kind = head[12:16]
    if kind == b"VP8 " and len(head) >= 30 and head[23:26] == b"\x9d\x01\x2a":
        # 14 bits each; the 2 bits above are a scale hint
        return (int.from_bytes(head[26:28], "little") & 0x3FFF) * (
            int.from_bytes(head[28:30], "little") & 0x3FFF
        )
    if kind == b"VP8L" and len(head) >= 25 and head[20] == 0x2F:
        bits = int.from_bytes(head[21:25], "little")  # width-1 and height-1, 14 bits each
        return ((bits & 0x3FFF) + 1) * (((bits >> 14) & 0x3FFF) + 1)
    if kind == b"VP8X" and len(head) >= 30:  # canvas width-1 and height-1, 24 bits each
        width = int.from_bytes(head[24:27], "little") + 1
        return width * (int.from_bytes(head[27:30], "little") + 1)
    return None


def _opens(data: bytes, image_format: str) -> None:
    """ProjectError unless Pillow opens `data` as `image_format` (the one of the extension and no
    other), the size in its header is at most `MAX_ASSET_PIXELS`, and it decodes. The size is
    asked before `load()`, so a small file that decodes to hundreds of millions of pixels is not
    decoded; for a WebP it is asked before `Image.open` too, from the RIFF header (001.30, point
    3). The messages are fixed: they never carry the path (001.28, point 6)."""
    if image_format == "WEBP":
        declared = _webp_pixels(data)
        if declared is None:
            raise ProjectError(BAD_IMAGE)
        if declared > MAX_ASSET_PIXELS:
            raise ProjectError(TOO_MANY_PIXELS)
    try:
        image = Image.open(io.BytesIO(data), formats=[image_format])
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise ProjectError(BAD_IMAGE) from None
    with image:
        width, height = image.size
        if width * height > MAX_ASSET_PIXELS:
            raise ProjectError(TOO_MANY_PIXELS)
        try:
            image.load()
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            raise ProjectError(BAD_IMAGE) from None
