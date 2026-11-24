"""Delete what a fixture of a wide scope made with `tmp_path_factory.mktemp` (spec S1.9b step 0,
row 17; 001.45 point 3, 001.47 point 10).

pytest keeps the folders of `tmp_path_factory` until the end of the session (and the last few
sessions after it); a full run left 25.9 GiB in the basetemp. A fixture of scope `class`, `module`,
`package` or `session` that makes one calls `remove_tree` when its scope closes.
"""

import os
import shutil
import stat
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any


def remove_tree(path: Path) -> None:
    """Delete the folder `path` and everything in it, read-only files too (Windows will not delete
    them). A folder that is not there is nothing to do. What cannot be deleted (a file that is
    still open, a permission) is a `warnings.warn`, never an exception: the test that used the
    folder already has its verdict."""
    if not os.path.lexists(path):
        return

    def retry(func: Callable[[str], Any], failed: str, _error: BaseException) -> None:
        try:
            os.chmod(failed, stat.S_IWRITE)  # a read-only file: make it writable and try again
            func(failed)
        except OSError as again:
            reason = again.strerror or type(again).__name__
            warnings.warn(f"no pude borrar {failed} ({reason})", stacklevel=2)

    shutil.rmtree(path, onexc=retry)
