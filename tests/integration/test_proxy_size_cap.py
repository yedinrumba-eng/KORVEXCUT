"""What a hostile proxy size may cost (spec 001.20, point 4, S1.4-27), measured in a child process.

A real proxy of 4096 x 4096 (48 MB a frame, the most `FrameReader` takes) and an inventory that
says 20000 x 20000 must not make the command reserve more than 200 MB. The figure is the commit
charge: what the process asked for, touched or not.
"""

import json
from pathlib import Path

import pytest

from tests.fixtures.peak_memory import measure
from tests.fixtures.synth_media import _ffmpeg

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]

LIMIT_MB = 200


def test_proxy_size_cap_a_real_4096_square_proxy_reserves_less_than_200_mb(
    tmp_path: Path,
) -> None:
    clip = tmp_path / "proyecto ñandú" / "cuadrado.mp4"
    clip.parent.mkdir()
    graph = "testsrc2=s=4096x4096:r=30:d=0.2,format=yuv420p"
    _ffmpeg(
        [*("-f", "lavfi", "-i", graph), *("-c:v", "libx264", "-preset", "ultrafast"), str(clip)]
    )
    code = (
        "from pathlib import Path\n"
        "from kcut.ff.reader import grab\n"
        "mark()\n"
        f"frame = grab(Path({str(clip)!r}), 0, 30, (4096, 4096), log=None)\n"
        "print(frame.shape, frame.flags.writeable)\n"
    )
    done = measure(code)
    assert done.returncode == 0, done.stderr
    assert "(4096, 4096, 3) True" in done.stdout
    assert done.commit_growth_mb < LIMIT_MB, done


def test_proxy_size_cap_an_inventory_of_20000_square_reserves_less_than_200_mb(
    view_fresh: Path,
) -> None:
    inventory = view_fresh / ".kcut" / "inventory.json"
    data = json.loads(inventory.read_text(encoding="utf-8"))
    for item in data["clips"]:
        if item["id"] == "a1":
            item["work"]["proxy_w"] = item["work"]["proxy_h"] = 20_000
    inventory.write_text(json.dumps(data), encoding="utf-8")
    code = (
        "from kcut import cli\n"
        "cli._build_parser()  # imports every command now, so only the run is measured\n"
        "mark()\n"
        f"argv = ['frames', 'a1', '30', '--project', {str(view_fresh)!r}, '--json']\n"
        "print('exit', cli.main(argv))\n"
    )
    done = measure(code)
    assert done.returncode == 0, done.stderr
    assert "exit 3" in done.stdout and "inventory.json no pasó la validación" in done.stdout
    assert done.commit_growth_mb < LIMIT_MB, done


def test_proxy_size_cap_a_proxy_that_is_not_the_size_of_the_inventory_is_refused_by_the_cli(
    view_fresh: Path,
) -> None:
    inventory = view_fresh / ".kcut" / "inventory.json"
    data = json.loads(inventory.read_text(encoding="utf-8"))
    for item in data["clips"]:
        if item["id"] == "a1":
            item["work"]["proxy_w"] = 4096  # inside the cap, but not what the ingest gives
    inventory.write_text(json.dumps(data), encoding="utf-8")
    code = (
        "from kcut import cli\n"
        "cli._build_parser()  # imports every command now, so only the run is measured\n"
        "mark()\n"
        f"argv = ['frames', 'a1', '30', '--project', {str(view_fresh)!r}, '--json']\n"
        "print('exit', cli.main(argv))\n"
    )
    done = measure(code)
    assert "exit 3" in done.stdout and "el proxy no coincide con el inventario" in done.stdout
    assert done.commit_growth_mb < LIMIT_MB
