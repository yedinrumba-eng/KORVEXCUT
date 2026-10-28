"""What the graphics page cannot reach (spec S1.6b 001.1, 001.31 point 10, 001.32 point 5, 001.33
point 4). Split from `capture.py` by the 300-line rule; `capture` names both and is what the rest
of the code calls.

The page is the one that kcut builds, with everything it needs inside it, so it has no business with
the network: `only_local` is the route that lets through the page itself and `data:` and aborts the
rest, and `NO_WEBRTC` is the init script that takes WebRTC out of the page. The route does not see a
WebSocket (the CSP of `page.py` does) and neither the route nor the CSP sees WebRTC: an ICE server
`turn:...?transport=tcp` opens a plain TCP connection by itself.
"""

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Playwright is imported where it is used: `kcut doctor` has to start without it
    from playwright.sync_api import Route

WEBRTC_NAMES = (
    "RTCPeerConnection",
    "webkitRTCPeerConnection",
    "RTCDataChannel",
    "RTCSessionDescription",
    "RTCIceCandidate",
)
# Each name is left `undefined` and cannot be defined again, neither by assigning nor by
# `Object.defineProperty`. It goes in with `context.add_init_script`, before any script of the page
# runs, in every frame and in every window the page opens (001.33, point 4).
NO_WEBRTC = (
    f"for (const k of {json.dumps(list(WEBRTC_NAMES))}) "
    "Object.defineProperty(window, k, {value: undefined, configurable: false, writable: false});"
)


def only_local(page_uri: str) -> "Callable[[Route], None]":
    """The route that blocks the network: only the page itself (`page_uri`) and `data:` go through,
    the rest is aborted. Another `file://` is aborted too, a UNC path included (001.31, point 10):
    the page has everything it needs inside it. The URL is compared without telling capitals from
    small letters (001.32, point 2): a Windows path does not, and Chromium writes the letter of
    the drive in capitals and the host of a UNC path in small letters."""
    page_key = page_uri.casefold()

    def handler(route: "Route") -> None:
        url = route.request.url
        if url.casefold() == page_key or url.startswith("data:"):
            route.continue_()
        else:
            route.abort()

    return handler
