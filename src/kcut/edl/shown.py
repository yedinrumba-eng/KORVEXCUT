"""How text and numbers of an EDL (or of the front-matter of the strategy) appear in a message
(spec 001.24, points 5 and 6). Pure.

An EDL is somebody else's file, and Claude reads what `kcut edl check` prints, so a message never
repeats free text: an id is shown only if it has the shape of an inventory id, a look that does not
exist is not shown at all, and any other text is shown as its length. Numbers go through
`describe_value`, which never builds the `str()` of an integer of thousands of digits.
"""

import re

from kcut.schema_util import describe_value

_CLIP_ID = re.compile(r"[a-z][0-9]{1,6}")  # the format of an id in the inventory
UNKNOWN_LOOK = "<look desconocido>"


def shown_id(value: object) -> str:
    """A clip id as it goes in a message: `'a1'` if it has the shape of an inventory id, else
    `<id inválido, N car.>` with the length of the text (`N` is 0 for what is not text)."""
    if isinstance(value, str) and _CLIP_ID.fullmatch(value) is not None:
        return describe_value(value)
    return f"<id inválido, {_length(value)} car.>"


def shown_text(value: object) -> str:
    """Any other free text as it goes in a message: `<texto, N car.>`."""
    return f"<texto, {_length(value)} car.>"


def shown_number(value: float) -> str:
    """A number of the EDL as it goes in a message."""
    return describe_value(value)


def _length(value: object) -> int:
    return len(value) if isinstance(value, str) else 0
