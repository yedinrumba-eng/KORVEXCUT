"""Chord symbols as notes (spec S1.8b row 1, 001.15): the bass inside `[40, 51]`, the triad inside
`[53, 64]` and sorted from low to high. The four chords of the pilot give the exact notes of
`piloto/music.py`; with the range `[55, 66]` that the first spec had, the F came out as
`(65, 57, 60)`.
"""

import pytest

from kcut.audio.chords import is_chord, parse_chord

ROOTS = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
    "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}  # fmt: skip


@pytest.mark.parametrize(
    ("symbol", "bass", "tones"),
    [
        ("Am", 45, (57, 60, 64)),
        ("F", 41, (53, 57, 60)),
        ("C", 48, (55, 60, 64)),
        ("G", 43, (55, 59, 62)),
    ],
)
def test_chords_the_four_chords_of_the_pilot_have_its_exact_notes(
    symbol: str, bass: int, tones: tuple[int, int, int]
) -> None:
    assert parse_chord(symbol) == (bass, tones)


@pytest.mark.parametrize("minor", [False, True])
@pytest.mark.parametrize("root", list(ROOTS))
def test_chords_every_root_gives_a_bass_and_a_sorted_triad_in_their_ranges(
    root: str, minor: bool
) -> None:
    bass, tones = parse_chord(root + ("m" if minor else ""))
    assert 40 <= bass <= 51 and bass % 12 == ROOTS[root]
    assert all(53 <= note <= 64 for note in tones)
    assert list(tones) == sorted(tones) and len(set(tones)) == 3
    third = 3 if minor else 4
    assert sorted(note % 12 for note in tones) == sorted(
        (ROOTS[root] + step) % 12 for step in (0, third, 7)
    )


@pytest.mark.parametrize("symbol", ["", "H", "am", "AM", "Cb", "E#", "B#", "Fb", "A#b", "Am7"])
def test_chords_what_is_not_a_root_and_an_optional_m_is_not_a_chord(symbol: str) -> None:
    assert not is_chord(symbol)
    with pytest.raises(ValueError, match="no es un acorde"):
        parse_chord(symbol)


def test_chords_whitespace_and_the_symbols_of_the_list_with_an_m() -> None:
    for symbol in (" Am", "Am ", "A m", "Am\n"):
        assert not is_chord(symbol), repr(symbol)
    assert all(is_chord(root + "m") for root in ROOTS)


def test_chords_the_error_does_not_repeat_the_symbol() -> None:
    with pytest.raises(ValueError) as info:
        parse_chord("IGNORE-PREVIOUS")
    assert "IGNORE" not in str(info.value)
