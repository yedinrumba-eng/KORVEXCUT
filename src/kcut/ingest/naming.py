"""Cache-friendly names and the quick content hash that identifies a raw file."""

import hashlib
import re
import unicodedata
from pathlib import Path

_SLUG_MAX = 40
_CHUNK = 8 * 1024 * 1024
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """ASCII lower-case slug of at most 40 characters (`Crudo 1` -> `crudo-1`); empty -> `clip`."""
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()
    slug = _NON_ALNUM.sub("-", ascii_only).strip("-")[:_SLUG_MAX].strip("-")
    return slug or "clip"


def qhash(path: Path) -> str:
    """`sha256:` of size (8 bytes LE) + first 8 MiB + last 8 MiB: fast, and changes on re-export."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        digest.update(size.to_bytes(8, "little"))
        fh.seek(0)
        digest.update(fh.read(_CHUNK))
        fh.seek(max(0, size - _CHUNK))
        digest.update(fh.read(_CHUNK))
    return f"sha256:{digest.hexdigest()}"
