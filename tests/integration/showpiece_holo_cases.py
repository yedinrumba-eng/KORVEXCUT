"""The width of the holographic board (spec S1.8a step 0, 001.35 point 10; row 17). Collected by
`test_components_showpiece.py` (300-line rule), whose helpers and fixture `root` it uses.

`w_px` goes from 300 to 2000: under about 140 px the 12-letter word was wider than the board,
because the letters have a floor of 16 px. At 300 px a word of 12 `M`, the widest letter, has to
stay inside the rectangle of the board: no pixel of the word (the near-white ones) outside of it.
"""

from pathlib import Path

import numpy as np


def test_components_showpiece_holo_width_300_keeps_a_12_letter_word_in_the_board(
    root: Path, tmp_path: Path
) -> None:
    # late import: `test_components_showpiece` imports this file, so it is whole only now
    from tests.integration import test_components_showpiece as module

    params = {
        "text": "MMMMMMMMMMMM",
        "type_at_f": 20,
        "type_step_f": 1,
        "accent_index": None,  # no letter in the accent color: all of them are the near-white one
        "w_px": 300,
    }
    resolved = module._resolve(root, module.CUES["holo"] | {"params": params})
    (cue,) = resolved.cues
    assert cue.params["w_px"] == 300
    shot = module._shot(resolved, cue.start_f + 25, tmp_path)  # every letter has fallen by now
    word = (shot[:, :, 3] > 200) & (shot[:, :, :3].min(axis=2) > 200)  # the letters: near white
    board = module._board_box(resolved)
    assert int((word & board).sum()) > 100, "holo: no hay palabra en el tablero"
    spilled = int((word & ~board).sum())
    assert spilled == 0, f"holo: {spilled} pixeles de la palabra fuera del tablero de 300 px"
    cols = np.nonzero(word.any(axis=0))[0]
    left, right = 0.5 * resolved.w - 150, 0.5 * resolved.w + 150
    assert left < cols.min() and cols.max() < right, (cols.min(), cols.max(), left, right)
