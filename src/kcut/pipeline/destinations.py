"""What `kcut build` writes in `.kcut/build/vN/` (spec 001.52 point 3, row 38).

`kcut render` looks at its five destinations before it does any work, so that a folder planted where
a file goes is told at once (exit 3) and not after minutes of mezzanines. `kcut build` does the same
with this list: the picture and its partial file, and the files of the mix with the partial file
that each one is written through (`<name>.<pid>.partial`, see `kcut.audio.mixer`). It lives in
`pipeline/`, neutral, and not in `commands/`.
"""

import os

from kcut.audio.mixer import FILES as MIX_FILES


def build_destinations() -> tuple[str, ...]:
    """The names, in `.kcut/build/vN/`, of what a build writes. The partial files of the mix carry
    the pid of this process."""
    pid = os.getpid()
    partials = tuple(f"{name}.{pid}.partial" for name in MIX_FILES)
    return ("video.mp4", "video.partial.mp4", *MIX_FILES, *partials)
