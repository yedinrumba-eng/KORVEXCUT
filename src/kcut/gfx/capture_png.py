"""The PNG of a captured frame: how much of it is drawn and how it is written (spec S1.6b). Split
from `capture.py` by the 300-line rule (001.31); `capture` names both and is what the rest calls.
"""

from pathlib import Path

import cv2
import numpy as np

from kcut.errors import ProjectError, ToolError
from kcut.jsonio import refuse_directory


def max_alpha(png: bytes, size: tuple[int, int]) -> int:
    """The largest alpha of the PNG, 0 if nothing is drawn. A PNG that is not `(H, W, 4)` is a
    ToolError: Chromium was asked for a transparent page."""
    decoded = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    width, height = size
    if decoded is None or decoded.dtype != np.uint8 or decoded.shape != (height, width, 4):
        raise ToolError("Chromium no entregó un PNG con alfa del tamaño del video")
    return int(decoded[:, :, 3].max())


def write_png(path: Path, data: bytes) -> None:
    """Write `data` to `path`, which is made new: what was there is removed first and the file is
    opened with `x`, so a link planted at that name is not written through. A folder at that name
    is a ProjectError that says so: it is not deleted."""
    refuse_directory(path)
    try:
        path.unlink(missing_ok=True)
        with path.open("xb") as handle:
            handle.write(data)
    except PermissionError:
        raise ProjectError(f"cierra el gráfico {path.name} en el reproductor y repite") from None
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
        raise ProjectError(f"no pude escribir el gráfico {path.name}: {reason}") from None
