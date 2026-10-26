"""Shared pieces of the `view` / `frames` integration tests: project copies, a runner, readers."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from kcut.ingest.inventory import load_inventory as read_inventory
from kcut.paths import resolve_in_project
from tests.fixtures.synth_media import MediaTruth

Synth = tuple[Path, MediaTruth]
Run = Callable[..., tuple[int, dict[str, Any], str]]


def gray(path: Path) -> float:
    return float(np.asarray(ImageOps.grayscale(Image.open(path))).mean())


def size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def remove(root: Path, clip_id: str, kind: str) -> None:
    clip = read_inventory(root / ".kcut" / "inventory.json").by_id(clip_id)
    assert clip is not None and clip.work is not None
    rel = clip.work.proxy if kind == "proxy" else clip.work.wav16
    assert rel is not None
    resolve_in_project(root, rel).unlink()


def project_args(root: Path) -> tuple[str, str]:
    return "--project", str(root)
