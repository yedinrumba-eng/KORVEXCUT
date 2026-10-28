"""Chord symbols as notes (spec S1.8b, 001.15): `Am`, `F`, `C#m`, `Bb`.

Pure. A symbol is a root (`C C# Db D D# Eb E F F# Gb G G# Ab A A# Bb B`) and an optional `m` for
a minor chord; nothing else is a chord. `parse_chord` gives the note of the bass and the three
notes of the triad as MIDI numbers: the bass is the root inside `[40, 51]`, and each note of the
triad is moved by octaves into `[53, 64]` and the three are sorted from low to high (with the range
`[55, 66]` the F came out as `(65, 57, 60)`; the pilot has `(53, 57, 60)`). Both ranges hold twelve
numbers, so every pitch class has exactly one note in them.
"""

import re

_ROOTS = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
    "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}  # fmt: skip
_SYMBOL = re.compile(r"([A-G][#b]?)(m?)")
BASS_LOW = 40  # the bass note is in [40, 51]
TRIAD_LOW = 53  # the notes of the triad are in [53, 64]
_MAJOR = (0, 4, 7)
_MINOR = (0, 3, 7)


def is_chord(symbol: str) -> bool:
    """Is `symbol` a root of the list and, if it has one, an `m` after it?"""
    found = _SYMBOL.fullmatch(symbol)
    return found is not None and found.group(1) in _ROOTS


def parse_chord(symbol: str) -> tuple[int, tuple[int, int, int]]:
    """`(bass, (low, middle, high))` of the chord `symbol`, as MIDI notes: the bass inside
    `[40, 51]` and the triad (major `0 4 7`, minor `0 3 7`) inside `[53, 64]`, sorted. `Am` is
    `(45, (57, 60, 64))`, `F` is `(41, (53, 57, 60))`. A symbol that is not a chord is a
    `ValueError` that does not repeat it."""
    found = _SYMBOL.fullmatch(symbol)
    if found is None or found.group(1) not in _ROOTS:
        raise ValueError("no es un acorde: raíz de la lista y una m opcional")
    root = _ROOTS[found.group(1)]
    intervals = _MINOR if found.group(2) else _MAJOR
    bass = BASS_LOW + (root - BASS_LOW) % 12
    notes = sorted(TRIAD_LOW + (root + step - TRIAD_LOW) % 12 for step in intervals)
    return bass, (notes[0], notes[1], notes[2])
