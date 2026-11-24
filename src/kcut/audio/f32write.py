"""Write raw float32 little-endian mono files, the intermediates of the audio chain (DS4).

Split from `wavio.py` by the 300-line rule (001.38, point 2: `write_f32_blocks` gained its `guard`):
`wavio` reads and writes the 16-bit wav and reads raw float32 (`read_f32`); this module writes the
raw float32, always through a partial file. `wavio` does not import it, so the packages that only
read a wav (`edl.check`) do not load the mixer's side of the audio.
"""

import contextlib
import os
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from kcut.errors import ProjectError
from kcut.jsonio import refuse_directory


def _reason(exc: OSError) -> str:
    """Why a write failed, in words and with no path: the `strerror`, or the name of the class."""
    return exc.strerror or type(exc).__name__


def write_f32(
    path: Path, x: NDArray[np.float32], *, guard: Callable[[], None] | None = None
) -> None:
    """Write raw float32 little-endian mono samples (no clipping: peaks survive until loudnorm).
    `guard`: see `write_f32_blocks`."""
    write_f32_blocks(path, [x], guard=guard)


def write_f32_blocks(
    path: Path,
    blocks: Iterable[NDArray[np.float32]],
    *,
    guard: Callable[[], None] | None = None,
) -> None:
    """Write the blocks, one after the other, as raw float32 little-endian mono samples.

    Never in place (001.25, point 3): the samples go to `<name>.<pid>.partial`, created new, and
    `os.replace` puts the finished file over `path`. A hard link or a link planted at `path` is
    replaced and not written through, and two processes do not write the same partial. Only one
    block is in memory at a time. A folder at `path` or at the partial, a file that cannot be
    deleted or replaced, and a disk that fails are a ProjectError; the partial is never left.

    What fails while a block is being made (`blocks` reads a wav) is not a failure to write: an
    `OSError` from `blocks` is a ProjectError that says it could not read (001.26, point 6).

    `guard` (001.38, point 2) looks at the folder again: it is called right before `os.replace`
    and right before the partial is deleted at the end, because the blocks can take minutes to
    make and the folder can be changed for a link to somebody else's meanwhile. If it raises a
    ProjectError nothing is moved, and the partial is not deleted (the name is not ours any
    more); the error is the one that goes out.
    """
    refuse_directory(path)
    partial = path.with_name(f"{path.name}.{os.getpid()}.partial")
    refuse_directory(partial)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial.unlink(missing_ok=True)  # never write through a stale file or a planted link
        with partial.open("xb") as handle:
            for block in _made(blocks):
                handle.write(np.asarray(block, dtype="<f4").tobytes())
        if guard is not None:
            guard()
        os.replace(partial, path)
    except PermissionError:
        raise ProjectError(f"cierra el archivo {path} en el reproductor y repite") from None
    except OSError as exc:
        # 001.37, point 10: the reason goes before the path, as in `require_disk_space`: `cli`
        # cuts a message to 300 characters and, in a deep folder, the cut took the reason away
        raise ProjectError(f"no pude escribir ({_reason(exc)}) en {path}") from None
    finally:
        _discard(partial, guard)


def _discard(partial: Path, guard: Callable[[], None] | None) -> None:
    """Delete `partial`, but only if the `guard` still passes (001.38, point 2): if the folder was
    changed for a link, the name is a file of somebody else's folder and it stays where it is."""
    if guard is not None:
        try:
            guard()
        except ProjectError:
            return
    with contextlib.suppress(OSError):
        partial.unlink(missing_ok=True)


def _made(blocks: Iterable[NDArray[np.float32]]) -> Iterator[NDArray[np.float32]]:
    """`blocks`, one by one; an `OSError` that makes one of them is a ProjectError about reading,
    so `write_f32_blocks` does not call it a write. The message has no path: the one in the error
    can carry the name of the original clip, with a phone number in it (001.27, point 9)."""
    iterator = iter(blocks)
    while True:
        try:
            block = next(iterator)
        except StopIteration:
            return
        except OSError as exc:
            raise ProjectError(f"no pude leer el audio de entrada: {_reason(exc)}") from None
        yield block
