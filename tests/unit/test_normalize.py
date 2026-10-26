"""`norm_token` / `norm_tokens`: accents, case and punctuation never decide a comparison."""

import pytest

from kcut.text.normalize import norm_token, norm_tokens


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("¿Qué?", "que"),
        ("ñandú", "nandu"),
        ("Hicksville,", "hicksville"),
        ("ÁÉÍÓÚ", "aeiou"),
        ("güe-güe", "guegue"),
        ("2026", "2026"),
        ("COVID-19", "covid19"),
        ("...", ""),
        ("", ""),
        ("日本", ""),
        ("é", "e"),  # "e" + combining acute, already decomposed
        ("é", "e"),  # precomposed "é"
        ("İ", "i"),  # capital I with dot: lower() adds a combining dot that is dropped
    ],
)
def test_norm_token(raw: str, expected: str) -> None:
    assert norm_token(raw) == expected


def test_norm_token_is_idempotent() -> None:
    once = norm_token("¡Hola, Ñandú 42!")
    assert once == "holanandu42"
    assert norm_token(once) == once


def test_norm_tokens_splits_on_any_whitespace_and_drops_empties() -> None:
    assert norm_tokens("¿Te  da\tcuriosidad\n de ... la IA?") == [
        "te",
        "da",
        "curiosidad",
        "de",
        "la",
        "ia",
    ]


def test_norm_tokens_of_nothing_is_empty() -> None:
    assert norm_tokens("") == []
    assert norm_tokens("  ¿? ... ") == []
