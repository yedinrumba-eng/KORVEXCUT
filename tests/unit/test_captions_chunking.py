"""Subtitle chunks (spec S1.6a rows 1 and 8): `build_chunks`, `shown_chunks` and the rule of what is
shown. Pure functions over `KeptWord`s; all at 30 fps (a frame is 33.3 ms), so 350 ms is 10.5
frames, 400 ms is 12, 150 ms is 5 and 60 ms is 2."""

import dataclasses

import pytest

from kcut.config.model import CaptionsSection
from kcut.edl.words import KeptWord
from kcut.errors import InternalError
from kcut.gfx.captions import (
    Chunk,
    ChunkWord,
    build_chunks,
    display_text,
    hide_window,
    shown_chunks,
)
from tests.unit.edl_fakes import config

FPS = 30
CFG = config().captions


def _w(i: int, text: str, s: int, e: int | None = None, clip: int = 0) -> KeptWord:
    """The word number `i`: output frames `[s, e)` (a quarter second by default)."""
    return KeptWord(f"a1:w{i:04d}", text, clip, s, s + 8 if e is None else e, "a1", 0, 0)


def _run(
    words: list[KeptWord], hide: list[tuple[int, int]] | None = None, cfg: CaptionsSection = CFG
) -> list[Chunk]:
    return build_chunks(words, cfg, hide or [], FPS)


def _texts(chunks: list[Chunk]) -> list[list[str]]:
    return [[w.text for w in c.words] for c in chunks]


def _talk(*texts: str, gap: int = 1, size: int = 8, clip: int = 0) -> list[KeptWord]:
    """Words one after another, `size` frames each and `gap` frames of silence between them."""
    words, at = [], 10
    for i, text in enumerate(texts):
        words.append(_w(i, text, at, at + size, clip))
        at += size + gap
    return words


def test_captions_chunking_the_defaults_of_the_template_are_3_words_and_18_characters() -> None:
    assert (CFG.max_words, CFG.max_chars, CFG.uppercase) == (3, 18, True)


def test_captions_chunking_at_most_three_words_per_chunk() -> None:
    chunks = _run(_talk("a", "b", "c", "d", "e", "f", "g"))
    assert _texts(chunks) == [["A", "B", "C"], ["D", "E", "F"], ["G"]]


def test_captions_chunking_at_most_eighteen_characters_counting_a_space_after_each_word() -> None:
    # sum(len + 1) of the words in the chunk + len of the new one > 18 closes the chunk
    chunks = _run(_talk("hola", "como", "estas"))  # (4+1)+(4+1)+5 = 15
    assert _texts(chunks) == [["HOLA", "COMO", "ESTAS"]]
    chunks = _run(_talk("hola", "como", "estasss"))  # 5+5+7 = 17: still fits
    assert len(chunks) == 1
    chunks = _run(_talk("hola", "como", "estassss"))  # 5+5+8 = 18: fits (not over)
    assert len(chunks) == 1
    chunks = _run(_talk("hola", "como", "estasssss"))  # 5+5+9 = 19: over
    assert _texts(chunks) == [["HOLA", "COMO"], ["ESTASSSSS"]]


def test_captions_chunking_the_length_is_counted_on_the_shown_text_without_punctuation() -> None:
    words = _talk("¡hola!", "(como)", "estasss")  # shown: HOLA COMO ESTASSS = 5+5+7
    assert _texts(_run(words)) == [["HOLA", "COMO", "ESTASSS"]]


def test_captions_chunking_a_word_from_another_clip_of_the_edl_never_joins_the_chunk() -> None:
    words = [
        _w(0, "uno", 10, 18, clip=0),
        _w(1, "dos", 19, 27, clip=0),
        _w(2, "tres", 28, 36, clip=2),
    ]
    assert _texts(_run(words)) == [["UNO", "DOS"], ["TRES"]]


def test_captions_chunking_a_pause_of_more_than_350_ms_starts_a_new_chunk() -> None:
    # 10 frames = 333 ms: same chunk; 11 frames = 366 ms: new chunk (frames * 1000 > 350 * fps)
    assert len(_run([_w(0, "uno", 10, 18), _w(1, "dos", 28, 36)])) == 1
    assert len(_run([_w(0, "uno", 10, 18), _w(1, "dos", 29, 37)])) == 2


def test_captions_chunking_a_pause_is_measured_from_the_end_of_the_last_word() -> None:
    words = [_w(0, "uno", 10, 40), _w(1, "dos", 45, 50)]  # a long word, then 5 frames of silence
    assert len(_run(words)) == 1


@pytest.mark.parametrize("mark", [",", ".", "?", "!", ";", ":"])
def test_captions_chunking_a_phrase_end_closes_the_chunk_once_it_is_400_ms_long(mark: str) -> None:
    long_enough = [_w(0, "hola" + mark, 10, 22), _w(1, "mundo", 23, 31)]  # 12 frames = 400 ms
    assert _texts(_run(long_enough)) == [["HOLA"], ["MUNDO"]]
    too_short = [_w(0, "hola" + mark, 10, 21), _w(1, "mundo", 22, 30)]  # 11 frames
    assert _texts(_run(too_short)) == [["HOLA", "MUNDO"]]


def test_captions_chunking_the_phrase_end_is_looked_at_on_the_raw_text_and_in_the_last_word() -> (
    None
):
    words = [_w(0, "hola,", 10, 22), _w(1, "que", 23, 31), _w(2, "tal", 32, 40)]
    assert _texts(_run(words)) == [["HOLA"], ["QUE", "TAL"]]  # the comma is on the first word
    quoted = [_w(0, 'hola."', 10, 22), _w(1, "mundo", 23, 31)]
    assert len(_run(quoted)) == 1  # a text that ends in a quote does not end in a period


def test_captions_chunking_a_word_that_starts_in_a_hidden_window_is_left_out() -> None:
    words = _talk("uno", "dos", "tres", "cuatro")  # starts at 10, 19, 28, 37
    chunks = _run(words, hide=[(19, 28)])
    assert _texts(chunks) == [["UNO"], ["TRES", "CUATRO"]]


def test_captions_chunking_the_window_is_half_open_start_included_end_excluded() -> None:
    words = _talk("uno", "dos", "tres")  # starts at 10, 19, 28
    assert _texts(_run(words, hide=[(19, 28)])) == [["UNO"], ["TRES"]]
    assert _texts(_run(words, hide=[(20, 28)])) == [["UNO", "DOS", "TRES"]]


def test_captions_chunking_a_hidden_word_closes_the_chunk_even_when_the_next_would_fit() -> None:
    words = _talk("uno", "dos", "tres", "cuatro", "cinco")
    chunks = _run(words, hide=[(28, 29)])  # only "tres" is hidden
    assert _texts(chunks) == [["UNO", "DOS"], ["CUATRO", "CINCO"]]


def test_captions_chunking_a_chunk_ends_150_ms_after_its_last_word() -> None:
    (chunk,) = _run([_w(0, "uno", 10, 20), _w(1, "dos", 21, 30)])
    assert (chunk.s_f, chunk.e_f) == (10, 30 + 5)  # ms_to_f_ceil(150) = 5 frames


def test_captions_chunking_a_chunk_ends_where_the_next_one_begins() -> None:
    chunks = _run([_w(0, "uno", 10, 20), _w(1, "dos", 23, 30), _w(2, "tres", 42, 45)])
    assert [(c.s_f, c.e_f) for c in chunks] == [(10, 35), (42, 50)]
    close = _run(
        [_w(0, "a", 10, 20), _w(1, "b", 21, 24), _w(2, "c", 25, 30)],
        cfg=dataclasses.replace(CFG, max_words=1),
    )
    assert [(c.s_f, c.e_f) for c in close] == [(10, 21), (21, 25), (25, 35)]


def test_captions_chunking_a_chunk_is_cut_where_a_hidden_window_begins_inside_it() -> None:
    chunks = _run([_w(0, "uno", 10, 20), _w(1, "dos", 21, 30)], hide=[(32, 60)])
    assert [(c.s_f, c.e_f) for c in chunks] == [(10, 32)]  # 35 would run into the window
    chunks = _run([_w(0, "uno", 10, 20), _w(1, "dos", 21, 30)], hide=[(36, 60)])
    assert [(c.s_f, c.e_f) for c in chunks] == [(10, 35)]  # the window begins after the end


def test_captions_chunking_a_window_that_begins_before_the_chunk_does_not_cut_it() -> None:
    chunks = _run([_w(0, "uno", 10, 20)], hide=[(2, 8)])
    assert [(c.s_f, c.e_f) for c in chunks] == [(10, 25)]


def test_captions_chunking_the_chunk_has_the_id_the_text_and_the_start_of_each_word() -> None:
    (chunk,) = _run([_w(0, "uno,", 10, 20), _w(1, "dos", 21, 30)])
    assert chunk.words == [ChunkWord("a1:w0000", "UNO", 10), ChunkWord("a1:w0001", "DOS", 21)]


def test_captions_chunking_text_is_shown_without_edge_punctuation_and_in_capitals() -> None:
    assert display_text('¿"Hola,"?', CFG) == "HOLA"
    assert display_text("«a-b.c»", CFG) == "A-B.C"  # only the edges are cut
    assert display_text("'", CFG) == "" and display_text(" ,. ", CFG) == ""
    lower = dataclasses.replace(CFG, uppercase=False)
    assert display_text("¡Hola!", lower) == "Hola"


def test_captions_chunking_a_word_with_nothing_to_show_is_not_in_any_chunk() -> None:
    words = [_w(0, "uno", 10, 18), _w(1, "...", 19, 27), _w(2, "dos", 28, 36)]
    chunks = _run(words)
    assert _texts(chunks) == [["UNO", "DOS"]]


def test_captions_chunking_no_words_no_chunks_and_a_single_word_is_one_chunk() -> None:
    assert _run([]) == []
    assert len(_run([_w(0, "hola", 5, 12)])) == 1


def test_captions_chunking_hide_window_starts_60_ms_before_the_graphic_and_ends_with_it() -> None:
    assert hide_window(100, 160, 30) == (98, 160)
    assert hide_window(100, 160, 60) == (96, 160)  # ceil(60 ms) = 4 frames at 60 fps
    assert hide_window(100, 160, 24) == (98, 160)  # ceil(1.44) = 2


def test_captions_chunking_a_chunk_left_with_no_frames_is_dropped() -> None:
    twin = [_w(0, "uno", 10, 12), _w(1, "dos", 10, 12)]  # the second begins where the first does
    chunks = _run(twin, cfg=dataclasses.replace(CFG, max_words=1))
    assert [(c.s_f, c.e_f) for c in chunks] == [(10, 17)] and _texts(chunks) == [["DOS"]]


class TestShown:
    """Row 8: `shown_chunks` gives the same frames with the text Claude may read."""

    RAW = _run(_talk("llama", "972", "808", "3211", "ya"))

    def test_shown_chunks_keep_the_frames_and_take_the_text_of_shown(self) -> None:
        shown = {
            "a1:w0000": "llama",
            "a1:w0001": "***",
            "a1:w0002": "***",
            "a1:w0003": "**11",
            "a1:w0004": "ya",
        }
        out = shown_chunks(self.RAW, shown, CFG)
        assert [(c.s_f, c.e_f) for c in out] == [(c.s_f, c.e_f) for c in self.RAW]
        assert _texts(out) == [["LLAMA", "***", "***"], ["**11", "YA"]]
        assert [w.s_f for c in out for w in c.words] == [w.s_f for c in self.RAW for w in c.words]
        assert [w.id for c in out for w in c.words] == [w.id for c in self.RAW for w in c.words]

    def test_shown_chunks_apply_the_same_rule_of_edges_and_capitals(self) -> None:
        shown = {
            "a1:w0000": "¿llama?",
            "a1:w0001": "(972)",
            "a1:w0002": "808,",
            "a1:w0003": "x",
            "a1:w0004": "ya.",
        }
        assert _texts(shown_chunks(self.RAW, shown, CFG)) == [["LLAMA", "972", "808"], ["X", "YA"]]
        lower = dataclasses.replace(CFG, uppercase=False)
        assert _texts(shown_chunks(self.RAW, shown, lower))[0] == ["llama", "972", "808"]

    def test_shown_chunks_a_word_that_is_left_empty_leaves_its_chunk_and_the_frames_stay(
        self,
    ) -> None:
        shown = {
            "a1:w0001": "",
            "a1:w0002": "...",
            "a1:w0000": "llama",
            "a1:w0003": "**11",
            "a1:w0004": "ya",
        }
        out = shown_chunks(self.RAW, shown, CFG)
        assert _texts(out) == [["LLAMA"], ["**11", "YA"]]
        assert [(c.s_f, c.e_f) for c in out] == [(c.s_f, c.e_f) for c in self.RAW]

    def test_shown_chunks_a_chunk_whose_words_all_vanish_is_still_there_with_its_frames(
        self,
    ) -> None:
        out = shown_chunks(self.RAW, {f"a1:w000{i}": "" for i in range(5)}, CFG)
        assert [c.words for c in out] == [[], []]
        assert [(c.s_f, c.e_f) for c in out] == [(c.s_f, c.e_f) for c in self.RAW]

    # 001.28: it was `a_word_that_shown_does_not_have_keeps_its_text`, which asserted the fallback
    # to the raw text; the door between the raw text and Claude fails closed now (row 26)
    @pytest.mark.parametrize("missing", range(5))
    def test_shown_chunks_shown_missing_id_is_an_internal_error_and_never_the_raw_text(
        self, missing: int
    ) -> None:
        shown = {f"a1:w000{i}": "###" for i in range(5) if i != missing}
        with pytest.raises(InternalError) as info:
            shown_chunks(self.RAW, shown, CFG)
        raw = ["llama", "972", "808", "3211", "ya"][missing]
        assert info.value.exit_code == 10
        assert f"a1:w000{missing}" in info.value.message_es  # the id says which word it was
        assert raw not in info.value.message_es.lower()  # the raw text of that word does not leave

    def test_shown_chunks_shown_missing_id_with_nothing_in_shown_is_an_internal_error(self) -> None:
        with pytest.raises(InternalError):
            shown_chunks(self.RAW, {}, CFG)
        assert shown_chunks([], {}, CFG) == []  # no words, nothing to look up

    def test_shown_chunks_do_not_change_the_chunks_they_come_from(self) -> None:
        before = _texts(self.RAW)
        # 001.28: it passed `{"a1:w0001": "###"}` alone; every id has to be in `shown` now
        shown_chunks(self.RAW, {f"a1:w000{i}": "###" for i in range(5)}, CFG)
        assert _texts(self.RAW) == before
