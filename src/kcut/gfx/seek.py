"""Put the graphics page at a second, with a limit of time (spec S1.6b, 001.31 point 4).

`window.seek(t)` is the JavaScript of the page, and a page that hangs would hold the capture (and
the lock `build-vN`) for ever: Playwright's `page.evaluate` and `cdp.send` have no timeout. The
limit goes in the call itself, because the synchronous API of Playwright is for one thread and no
other thread may call it:

- `Runtime.evaluate` over CDP with `timeout`: V8 ends a script that runs for longer (a `while
  (true) {}`), and Chromium answers with a protocol error.
- `awaitPromise` with a race against `setTimeout` on the side of the page: a `seek` that gives a
  promise that never resolves is rejected when the time is over, with `MARKER` in what it says.

The promise resolves with no value (001.32, point 6): what `seek` returns does not travel over CDP,
so there is no `returnByValue` error for something that cannot be serialized (`window`, a cycle).
What is left to say "protocol error" is the end of a script or a Chromium that died.
"""

import json
import time
from typing import Any

MARKER = "kcut-frame-timeout"  # what the race of the page rejects with
_SEEK = (
    "(() => { return new Promise((resolve, reject) => {"
    f' const id = setTimeout(() => reject(new Error("{MARKER}")), %d);'
    " Promise.resolve(window.seek(%s)).then("
    "() => { clearTimeout(id); resolve(); }, (e) => { clearTimeout(id); reject(e); });"
    " }); })()"
)
_TERMINATED_AFTER = 0.9  # a protocol error after this much of the limit is the end of the script


class FrameTimeout(Exception):
    """The frame did not end in `timeout_s` seconds."""


class SeekError(Exception):
    """The `seek` of the page threw or rejected: the text is what the page said, first line."""


def evaluate_seek(cdp: Any, t: float, timeout_s: float, error: type[Exception]) -> None:
    """Run `window.seek(t)` in the page through `cdp`, waiting at most `timeout_s` seconds.

    `FrameTimeout` if the time ran out (a loop that V8 ended, or a promise that did not resolve),
    `SeekError` if the page threw, and nothing if it ended. `error` is the base class of the errors
    of Playwright: one that the call raises after nearly all the time is the end of the script, one
    that comes at once is another failure and goes up as it is."""
    ms = max(1, round(timeout_s * 1000))
    request = {
        "expression": _SEEK % (ms, json.dumps(t)),
        "awaitPromise": True,
        "returnByValue": True,
        "timeout": ms,
    }
    started = time.monotonic()
    try:
        reply = cdp.send("Runtime.evaluate", request)
    except error:
        if time.monotonic() - started >= _TERMINATED_AFTER * timeout_s:
            raise FrameTimeout from None
        raise
    details = reply.get("exceptionDetails") if isinstance(reply, dict) else None
    if details is None:
        return
    if MARKER in json.dumps(details, default=str):
        raise FrameTimeout
    text = str(details.get("text", "")).strip() if isinstance(details, dict) else ""
    raise SeekError(text.splitlines()[0] if text else "la página falló en el seek")
