"""`transcribe.fillers` has the same bounds as `glossary.terms` (spec 001.12, point 11)."""

import json

import pytest

from kcut.config.load import parse_config
from kcut.errors import ProjectError


def _fillers(items: list[str]) -> str:
    return f"[transcribe]\nfillers = {json.dumps(items, ensure_ascii=False)}\n"


def _terms(items: list[str]) -> str:
    return f"[glossary]\nterms = {json.dumps(items, ensure_ascii=False)}\n"


def _fail(text: str) -> str:
    with pytest.raises(ProjectError) as info:
        parse_config(text, default_name="x")
    assert info.value.exit_code == 3
    return info.value.message_es


class TestFillersBounds:
    def test_fillers_bounds_forty_characters_are_accepted(self) -> None:
        cfg = parse_config(_fillers(["e" * 40]), default_name="x")
        assert cfg.transcribe.fillers == ("e" * 40,)

    def test_fillers_bounds_a_filler_of_41_characters_names_the_field(self) -> None:
        message = _fail(_fillers(["eh", "e" * 41]))
        assert "transcribe.fillers[1]" in message and "40" in message

    def test_fillers_bounds_an_empty_filler_names_the_field(self) -> None:
        assert "transcribe.fillers[0]" in _fail(_fillers([""]))

    def test_fillers_bounds_200_are_accepted_and_201_are_not(self) -> None:
        cfg = parse_config(_fillers([f"f{i}" for i in range(200)]), default_name="x")
        assert len(cfg.transcribe.fillers) == 200
        assert "transcribe.fillers" in _fail(_fillers([f"f{i}" for i in range(201)]))

    def test_fillers_bounds_a_filler_that_is_not_text_names_the_field(self) -> None:
        assert "transcribe.fillers[0]" in _fail("[transcribe]\nfillers = [3]\n")

    def test_fillers_bounds_are_the_same_as_the_glossary(self) -> None:
        for items, ok in [(["a" * 40], True), (["a" * 41], False), ([""], False)]:
            glossary = _terms(items)
            fillers = _fillers(items)
            if ok:
                parse_config(glossary, default_name="x")
                parse_config(fillers, default_name="x")
            else:
                assert "glossary.terms[0]" in _fail(glossary)
                assert "transcribe.fillers[0]" in _fail(fillers)
        assert "glossary.terms" in _fail(_terms([f"t{i}" for i in range(201)]))
        assert (
            len(parse_config(_terms([f"t{i}" for i in range(200)]), default_name="x").glossary)
            == 200
        )

    def test_fillers_bounds_the_default_and_accented_fillers_still_work(self) -> None:
        cfg = parse_config(_fillers(["éste", "o sea", "¿sabes?"]), default_name="x")
        assert cfg.transcribe.fillers == ("éste", "o sea", "¿sabes?")
        assert parse_config("", default_name="x").transcribe.fillers[0] == "eh"


class TestFillerWordsCap:
    """001.18 point 6: a filler of `kcut.toml` has at most 5 words (the bridges of the PII
    detector compare sequences, and their cost grows with the longest one)."""

    def test_filler_words_cap_five_words_are_accepted(self) -> None:
        cfg = parse_config(_fillers(["a b c d e"]), default_name="x")
        assert cfg.transcribe.fillers == ("a b c d e",)

    def test_filler_words_cap_six_words_name_the_field(self) -> None:
        message = _fail(_fillers(["eh", "a b c d e f"]))
        assert "transcribe.fillers[1]" in message and "5" in message

    def test_filler_words_cap_counts_words_not_spaces(self) -> None:
        assert parse_config(_fillers(["a   b   c"]), default_name="x").transcribe.fillers
        assert "transcribe.fillers[0]" in _fail(_fillers(["a b c d e f g h i j k l m n o"]))

    def test_filler_words_cap_does_not_touch_the_glossary(self) -> None:
        term = "uno dos tres cuatro cinco seis"
        assert parse_config(_terms([term]), default_name="x").glossary == (term,)

    def test_filler_words_cap_the_defaults_fit(self) -> None:
        cfg = parse_config("", default_name="x")
        assert max(len(f.split()) for f in cfg.transcribe.fillers) <= 5
