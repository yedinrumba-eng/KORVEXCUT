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
# All the images that go into one page, together (001.33, point 8): `page.html` carries each of them
# as a data URI. Counted in the bytes of the images (the file), not in the characters of the URI:
# 64 MiB hold three images of the cap above. The cue that crosses it is a G09 with this text.
MAX_PAGE_IMAGE_BYTES = 64 * 1024 * 1024
PAGE_IMAGES_TOO_BIG = (
    "las imágenes de los gráficos pasan de 64 MiB en total; usa menos o más livianas"
)
MAX_ASSET_PIXELS = 4096 * 4096  # width x height, read from the header before the image is decoded
WEBP_HEADER_BYTES = 30  # all the RIFF header of a WebP needs to say its size
MIME = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
# The format Pillow may open each extension as: a file is never opened as something else
FORMATS = {".png": "PNG", ".webp": "WEBP", ".jpg": "JPEG", ".jpeg": "JPEG"}
BAD_IMAGE = "Pillow no puede abrir la imagen: no es una imagen válida del formato de su extensión"
TOO_MANY_PIXELS = "la imagen tiene más de 4096 x 4096 píxeles; kcut no la usa"
FOLDER = "recursos/"
# 001.35, point 5: Chromium plays an APNG or an animated WebP with its own clock, so the same time
# would not give the same picture
ANIMATED_IMAGE = "la imagen está animada; los gráficos usan imágenes fijas"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
WEBP_ANIMATION_FLAG = 0x02  # the `A` bit of the flags byte of the `VP8X` chunk
WEBP_IMAGE_DATA = (b"VP8 ", b"VP8L", b"ANMF")  # from the first of these on, nothing says "animated"
# 001.36, point 4: the walk over the chunks of the header goes through at most the header chunk
# (`IHDR`; the first chunk of a WebP) and this many after it. A PNG of 20 MiB made of 1.75 million
# empty chunks cost 3 s each time a cue read it; one with more is a G09, with no path
MAX_HEADER_CHUNKS = 64
TOO_MANY_CHUNKS = "la imagen tiene demasiados bloques; vuelve a exportarla"


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
    if _is_animated(data, FORMATS[suffix]):  # from the header, before anything is decoded
        raise ProjectError(ANIMATED_IMAGE)
    _opens(data, FORMATS[suffix])
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def uri_bytes(uri: str) -> int:
    """The bytes of the image that the data URI `uri` (`image_data_uri` gave it) carries: the
    length of what is behind the comma, decoded, without the padding `=`."""
    body = uri.split(",", 1)[1]
    return len(body) // 4 * 3 - body.count("=", len(body) - 2)


def _read(path: Path) -> bytes:
    try:
        return read_capped(path, MAX_IMAGE_BYTES)
    except ProjectError:  # `read_capped`: over the cap, or it grew while it was read
        raise ProjectError("la imagen pesa más de 20 MB o cambió mientras se leía") from None
    except OSError:
        raise ProjectError("no pude leer la imagen") from None


def _is_animated(data: bytes, image_format: str) -> bool:
    """Does the header of `data` say it is an animation (001.35, point 5)? Only the chunk headers
    are read, never the pixels, and a file that is not that format is not animated (`_opens` has
    the word on it).

    - PNG: a chunk `acTL` before the first `IDAT` (an APNG); the chunks are walked by their
      lengths, up to `IDAT` or `IEND`.
    - WebP: a `VP8X` chunk whose flags have the animation bit, or an `ANIM` chunk, among the chunks
      that come before the first frame or image (`VP8 `, `VP8L`, `ANMF`).
    - Any other format has no animation.

    The walk looks at no more than the first chunk and `MAX_HEADER_CHUNKS` after it: with more
    before the image the file is a ProjectError (`TOO_MANY_CHUNKS`, G09; 001.36, point 4)."""
    if image_format == "PNG":
        return _png_has_actl(data)
    if image_format == "WEBP":
        return _webp_is_animated(data)
    return False


def _png_has_actl(data: bytes) -> bool:
    if data[: len(PNG_SIGNATURE)] != PNG_SIGNATURE:
        return False
    offset = len(PNG_SIGNATURE)
    walked = 0
    while offset + 8 <= len(data):  # 4 bytes of length and 4 of type
        kind = data[offset + 4 : offset + 8]
        if kind == b"acTL":
            return True
        if kind in (b"IDAT", b"IEND"):
            return False
        walked += 1
        if walked > MAX_HEADER_CHUNKS + 1:  # `IHDR` and the cap after it (001.36, point 4)
            raise ProjectError(TOO_MANY_CHUNKS)
        offset += 12 + int.from_bytes(data[offset : offset + 4], "big")  # length, type, data, CRC
    return False


def _webp_is_animated(data: bytes) -> bool:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return False
    offset = 12
    walked = 0
    while offset + 8 <= len(data):  # 4 bytes of type and 4 of size
        kind = data[offset : offset + 4]
        size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        if kind == b"VP8X" and offset + 8 < len(data) and data[offset + 8] & WEBP_ANIMATION_FLAG:
            return True
        if kind == b"ANIM":
            return True
        if kind in WEBP_IMAGE_DATA:
            return False
        walked += 1
        if walked > MAX_HEADER_CHUNKS + 1:  # the first chunk and the cap after it (001.36)
            raise ProjectError(TOO_MANY_CHUNKS)
        offset += 8 + size + (size & 1)  # a chunk of odd size has a pad byte
    return False


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
