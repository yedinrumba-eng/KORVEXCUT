"""`capture_stills` hands each PNG to `on_shot(f, png)` as soon as it is made (spec S1.9b step 0,
row 8; 001.47 point 1), with the Chromium-less shooter of `fake_shooter`.

In the order of `frames`, inside the one session, and without keeping the PNG: with `on_shot` the
result is `{}`; without it the result is the dict it always was.
"""

from pathlib import Path

import pytest

from kcut.gfx.capture import capture_stills
from tests.integration.fake_shooter import Hooks, install_fake_shooter

SIZE = (8, 6)


def test_capture_on_shot_each_png_is_handed_over_in_the_order_of_frames_and_none_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hooks = install_fake_shooter(monkeypatch, Hooks())
    delivered: list[tuple[int, bytes]] = []
    seen_before: list[int] = []

    def on_shot(f: int, png: bytes) -> None:
        seen_before.append(len(hooks.shot))  # the frame is shot just before it is handed over
        delivered.append((f, png))

    found = capture_stills(
        "<p>x</p>", tmp_path, [30, 5, 90], 30, SIZE, tmp_path, None, on_shot=on_shot
    )
    assert found == {}
    assert [f for f, _ in delivered] == [30, 5, 90] and seen_before == [1, 2, 3]
    assert hooks.started == 1  # one session for all of them
    assert all(png.startswith(b"\x89PNG") for _, png in delivered)


def test_capture_on_shot_without_it_the_result_is_the_dict_of_always(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_shooter(monkeypatch, Hooks())
    found = capture_stills("<p>x</p>", tmp_path, [30, 5], 30, SIZE, tmp_path, None)
    assert sorted(found) == [5, 30] and all(png.startswith(b"\x89PNG") for png in found.values())


def test_capture_on_shot_what_it_raises_stops_the_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hooks = install_fake_shooter(monkeypatch, Hooks())

    def on_shot(f: int, png: bytes) -> None:
        raise ValueError("stop")

    with pytest.raises(ValueError, match="stop"):
        capture_stills("<p>x</p>", tmp_path, [1, 2, 3], 30, SIZE, tmp_path, None, on_shot=on_shot)
    assert hooks.shot == [1]
