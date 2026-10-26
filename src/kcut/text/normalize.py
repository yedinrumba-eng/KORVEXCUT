"""Token normalization used to compare words across cameras, fillers and repeated takes."""

import unicodedata


def norm_token(s: str) -> str:
    """NFD, combining marks dropped, lower case, only `[a-z0-9]` kept.

    `"¿Qué?"` -> `"que"`, `"ñandú"` -> `"nandu"`.
    """
    decomposed = unicodedata.normalize("NFD", s)
    bare = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch for ch in bare.lower() if "a" <= ch <= "z" or "0" <= ch <= "9")


def norm_tokens(text: str) -> list[str]:
    """Split `text` on whitespace, normalize each piece and drop the ones that end up empty."""
    return [token for token in map(norm_token, text.split()) if token]
