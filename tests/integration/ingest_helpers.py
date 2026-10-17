"""Shared helpers of the ingest integration tests."""

import hashlib
import json
from pathlib import Path

from kcut.ingest.inventory import Inventory, load_inventory
from tests.conftest import run_kcut


def ingest(root: Path, *extra: str, proxies: bool = False) -> tuple[int, dict[str, object]]:
    """Run `kcut ingest --json` (without proxies unless asked: they cost ~7 s)."""
    flags = [] if proxies else ["--no-proxy"]
    result = run_kcut("ingest", "--project", str(root), "--json", *flags, *extra)
    return result.returncode, json.loads(result.stdout)


def inventory(root: Path) -> Inventory:
    return load_inventory(root / ".kcut" / "inventory.json")


def edit_toml(root: Path, old: str, new: str) -> None:
    toml = root / "kcut.toml"
    text = toml.read_text(encoding="utf-8")
    assert old in text
    toml.write_text(text.replace(old, new), encoding="utf-8")


def snapshot(folder: Path) -> dict[str, tuple[str, int]]:
    """Content hash and mtime of every file under `folder`, to prove nothing changed."""
    result: dict[str, tuple[str, int]] = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[path.relative_to(folder).as_posix()] = (digest, path.stat().st_mtime_ns)
    return result
