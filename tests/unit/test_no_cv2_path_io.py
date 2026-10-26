"""No `cv2.imread` / `cv2.imwrite` in `src/`, whatever the way they are called (0.10 point 13).

Both fail on Windows when the path has a non-ASCII character (`proyecto ñandú`). Images are read
with `cv2.imdecode(np.fromfile(...))` and written with `cv2.imencode(...)[1].tofile(...)`, or with
Pillow. The check walks the syntax tree of every file in `src/` (spec 001.20 point 10), so a call
split over lines, an alias, `from cv2 import imread` or `getattr(cv2, "imread")` do not slip by
the way they slip by a grep.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
FORBIDDEN = frozenset({"imread", "imwrite"})


def find_cv2_path_io(source: str) -> list[str]:
    """What in `source` reaches `cv2.imread` or `cv2.imwrite`: calls, imports, aliases."""
    tree = ast.parse(source)
    modules = {"cv2"}  # the names `cv2` goes by here (`import cv2 as c`)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.asname or a.name for a in node.names if a.name.split(".")[0] == "cv2"}
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "cv2":
            found += [f"from cv2 import {a.name}" for a in node.names if a.name in FORBIDDEN]
            found += [f"from cv2 import {a.name}" for a in node.names if a.name == "*"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN:
            if isinstance(node.value, ast.Name) and node.value.id in modules:
                found.append(f"{node.value.id}.{node.attr}")
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") in {
            "getattr",
            "__import__",
        }:
            names = [a.value for a in node.args if isinstance(a, ast.Constant)]
            if any(n in FORBIDDEN for n in names):
                found.append("getattr(..., imread/imwrite)")
    return found


def test_no_cv2_path_io_in_src() -> None:
    files = sorted(SRC.rglob("*.py"))
    assert files, f"no hay archivos .py bajo {SRC}"
    found = [
        f"{path.relative_to(SRC.parent)}: {hit}"
        for path in files
        for hit in find_cv2_path_io(path.read_text(encoding="utf-8"))
    ]
    assert not found, "cv2.imread/imwrite con una ruta falla con rutas no ASCII:\n" + "\n".join(
        found
    )


@pytest.mark.parametrize(
    "source",
    [
        "import cv2\nimg = cv2.imread(str(path))\n",
        "import cv2\ncv2.imwrite(out, frame)\n",
        "import cv2\ncv2.imread(\n    path,\n)\n",  # split over lines: a grep misses it
        "import cv2 as c\nc.imread(p)\n",
        "import cv2\nread = cv2.imread\nread(p)\n",  # an alias, never called as cv2.imread(
        "import cv2\nwrite = cv2.imwrite\n",
        "from cv2 import imread\nimread(p)\n",
        "from cv2 import imwrite as save\nsave(p, x)\n",
        "from cv2 import imdecode, imread\n",
        "from cv2 import *\n",
        "import cv2\ngetattr(cv2, 'imread')(p)\n",
        'import cv2\nfn = getattr(cv2, "imwrite")\n',
    ],
)
def test_no_cv2_path_io_the_detector_catches_each_way_in(source: str) -> None:
    assert find_cv2_path_io(source)


@pytest.mark.parametrize(
    "source",
    [
        "import cv2\nok, buf = cv2.imencode('.png', img)\n",
        "import cv2\nimg = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)\n",
        "from cv2 import imdecode, imencode\n",
        "import cv2\nmsg = 'cv2.imread( is forbidden'\n",  # text is not a call
        "# cv2.imread(p) in a comment\nx = 1\n",
        "from PIL import Image\nimage = Image.open(path)\nimage.read = 1\nx = imread\n",
        "import other\nother.imread(p)\n",  # not cv2
    ],
)
def test_no_cv2_path_io_the_detector_lets_the_safe_code_through(source: str) -> None:
    assert find_cv2_path_io(source) == []
