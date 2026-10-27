"""A page cannot open a window to the network or talk WebRTC (spec S1.6b row 36, 001.32 point 5):
the block of the network is on the context (`context.route`), so it covers the windows that the page
opens, and Chromium starts with `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`, so
WebRTC sends no UDP by itself. The page is the one `build_page` makes with a test runtime whose
`seek` waits a while, so that Chromium lives long enough for a request to reach the local servers of
the test if it was not stopped. It does not matter if the capture ends well or with the ToolError of
the page: what counts is that nothing comes out.
"""

import contextlib
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from kcut.errors import ToolError
from kcut.gfx.capture import capture_stills, launch_options
from kcut.gfx.page import build_page
from tests.integration.capture_helpers import H, W, counting_server, sample_data, with_runtime

pytestmark = [pytest.mark.chromium, pytest.mark.slow]
WEBRTC_FLAG = "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"
READY = "window.KC = { register() {} }; window.kcutReady = true;"


def _waiting(ms: int) -> str:
    """A `seek` that gives a promise that resolves after `ms` ms: the capture lasts that long."""
    return f"window.seek = () => new Promise((resolve) => setTimeout(resolve, {ms}));"


@contextmanager
def _counting_udp() -> Iterator[tuple[int, list[bytes]]]:
    """A local UDP socket that records every packet that reaches it: `(port, packets)`."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.2)
    packets: list[bytes] = []
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                packets.append(sock.recvfrom(4096)[0])
            except TimeoutError:
                continue
            except ConnectionResetError:  # Windows reports an ICMP error on a UDP socket this way
                continue
            except OSError:
                return

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield sock.getsockname()[1], packets
    finally:
        stop.set()
        thread.join(timeout=5)
        sock.close()


def test_gfx_popup_webrtc_the_launch_options_carry_the_webrtc_policy() -> None:
    options = launch_options()
    assert options["args"] == [WEBRTC_FLAG]
    assert options["headless"] is True and options["chromium_sandbox"] is True


def test_gfx_popup_webrtc_a_window_the_page_opens_never_reaches_the_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with counting_server() as (port, hits):
        opening = f'window.open("http://127.0.0.1:{port}/popup");'
        with_runtime(monkeypatch, f"{READY} {opening} {_waiting(1500)}")
        page = build_page(sample_data(), [])
        with contextlib.suppress(ToolError):  # the capture may end well or with a page error
            capture_stills(page, tmp_path, [0], 30, (W, H), tmp_path / "out", None)
        assert hits == []  # no request from the popup, whatever came of the capture


def test_gfx_popup_webrtc_a_peer_connection_sends_no_udp_in_three_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _counting_udp() as (port, packets):
        gathering = (
            "try { const pc = new RTCPeerConnection("
            f'{{ iceServers: [{{ urls: "stun:127.0.0.1:{port}" }}] }}); '
            'pc.createDataChannel("x"); '
            "pc.createOffer().then((o) => pc.setLocalDescription(o)).catch(() => {}); "
            "} catch (e) { /* blocked */ }"
        )
        with_runtime(monkeypatch, f"{READY} {gathering} {_waiting(3000)}")
        page = build_page(sample_data(), [])
        with contextlib.suppress(ToolError):
            capture_stills(page, tmp_path, [0], 30, (W, H), tmp_path / "out", None)
        assert packets == []  # not one packet of STUN in the 3 s that the page lived
