"""The page has no WebRTC at all (spec S1.7 step 0, 001.33 point 4; row 12).

The flag of S1.6b row 36 cuts the UDP of WebRTC, but an ICE server `turn:...?transport=tcp` opens a
plain TCP connection that neither the route nor the CSP sees, and a text of the page can leave in
the `username` of TURN. So `_start` adds, before `context.route`, an init script that leaves
`RTCPeerConnection`, `webkitRTCPeerConnection`, `RTCDataChannel`, `RTCSessionDescription` and
`RTCIceCandidate` as `undefined`, and the page cannot put them back.
"""

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from kcut.errors import ToolError
from kcut.gfx import capture as gfx_capture
from kcut.gfx.capture import Shooter, capture_stills, launch_options
from kcut.gfx.page import build_page
from tests.integration.capture_helpers import H, W, page_with, sample_data, with_runtime

pytestmark = [pytest.mark.chromium, pytest.mark.slow]
NAMES = [
    "RTCPeerConnection",
    "webkitRTCPeerConnection",
    "RTCDataChannel",
    "RTCSessionDescription",
    "RTCIceCandidate",
]
READY = "window.KC = { register() {} }; window.kcutReady = true;"


@contextmanager
def _counting_tcp() -> Iterator[tuple[int, list[tuple[str, int]]]]:
    """A local TCP server that records the address of every connection it accepts."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    server.settimeout(0.2)
    seen: list[tuple[str, int]] = []
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                conn, addr = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            seen.append(addr)
            conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield server.getsockname()[1], seen
    finally:
        stop.set()
        thread.join(timeout=5)
        server.close()


def _turn_over_tcp(port: int, *, caught: bool) -> str:
    """A `seek` that tries a peer connection with a TURN server over TCP at `port`, then waits 2 s
    so that Chromium lives long enough for the connection to arrive if nothing stopped it."""
    attempt = (
        f'const pc = new RTCPeerConnection({{ iceServers: [{{ urls: "turn:127.0.0.1:{port}'
        '?transport=tcp", username: "x", credential: "y" }] }); '
        'pc.createDataChannel("x"); '
        "pc.createOffer().then((o) => pc.setLocalDescription(o)).catch(() => {});"
    )
    body = f"try {{ {attempt} }} catch (e) {{ /* blocked */ }}" if caught else attempt
    wait = "new Promise((resolve) => setTimeout(resolve, 2000))"
    return f"window.seek = () => {{ {body} return {wait}; }};"


def test_gfx_no_webrtc_the_five_names_are_undefined_and_the_page_cannot_put_them_back(
    tmp_path: Path,
) -> None:
    with Shooter(page_with(""), tmp_path, 30, (100, 100)) as shooter:
        assert shooter._page is not None
        kinds = shooter._page.evaluate("(names) => names.map((k) => typeof window[k])", NAMES)
        assert kinds == ["undefined"] * len(NAMES)
        rows = shooter._page.evaluate(
            """(names) => names.map((k) => {
                const d = Object.getOwnPropertyDescriptor(window, k);
                let redefined = true;
                try {
                    Object.defineProperty(window, k, { value: 1 });
                } catch (e) {
                    redefined = false;
                }
                window[k] = 1;
                return [d.configurable, d.writable, redefined, typeof window[k]];
            })""",
            NAMES,
        )
    assert rows == [[False, False, False, "undefined"]] * len(NAMES)


@pytest.mark.parametrize("caught", [True, False], ids=["caught", "uncaught"])
def test_gfx_no_webrtc_a_turn_server_over_tcp_receives_no_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caught: bool
) -> None:
    with _counting_tcp() as (port, seen):
        with_runtime(monkeypatch, f"{READY} {_turn_over_tcp(port, caught=caught)}")
        page = build_page(sample_data(), [])
        try:
            capture_stills(page, tmp_path, [0], 30, (W, H), tmp_path / "out", None)
        except ToolError:
            assert not caught  # an uncaught `new RTCPeerConnection` is an error of the page
        else:
            assert caught
        assert seen == []  # not one connection, whether it ended well or with the page error


def test_gfx_no_webrtc_the_init_script_goes_in_before_the_route_and_the_flag_stays() -> None:
    source = Path(gfx_capture.__file__).read_text(encoding="utf-8")
    assert source.index(".add_init_script(") < source.index("context.route(")
    options = launch_options()
    assert options["args"] == ["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]
    for name in NAMES:
        assert name in gfx_capture.NO_WEBRTC
    assert "configurable: false" in gfx_capture.NO_WEBRTC
    assert "writable: false" in gfx_capture.NO_WEBRTC


def test_gfx_no_webrtc_a_page_that_never_asks_for_it_still_captures(tmp_path: Path) -> None:
    found = capture_stills(page_with(""), tmp_path, [0], 30, (100, 100), tmp_path / "out", None)
    assert list(found) == [0]
