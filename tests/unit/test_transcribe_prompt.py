"""The Whisper prompt: fillers first, then the glossary, then the extra text."""

from typing import Any

from kcut.config.load import parse_config
from kcut.transcribe.engine import build_prompt


def _cfg(toml: str = "") -> Any:
    return parse_config(toml, default_name="x")


class TestPrompt:
    def test_the_example_of_the_spec(self) -> None:
        toml = '[transcribe]\nfillers = ["eh", "este", "o sea", "mmm", "bueno", "pues"]\n'
        toml += '[glossary]\nterms = ["Higgsfield", "Claude", "IA"]\n'
        assert (
            build_prompt(_cfg(toml)) == "Eh, este, o sea, mmm, bueno, pues. Higgsfield, Claude, IA."
        )

    def test_the_extra_text_goes_last_after_a_space(self) -> None:
        toml = '[transcribe]\nfillers = ["eh"]\nprompt_extra = "Habla un dominicano."\n'
        toml += '[glossary]\nterms = ["Korvex"]\n'
        assert build_prompt(_cfg(toml)) == "Eh. Korvex. Habla un dominicano."

    def test_the_default_fillers_open_the_prompt(self) -> None:
        text = build_prompt(_cfg())
        assert text == "Eh, ehh, em, emm, mmm, este, o sea, pues, bueno, entonces."

    def test_no_glossary_and_no_extra_means_fillers_only(self) -> None:
        assert build_prompt(_cfg('[transcribe]\nfillers = ["um", "uh"]\n')) == "Um, uh."

    def test_without_fillers_the_glossary_keeps_its_own_case(self) -> None:
        toml = '[transcribe]\nfillers = []\n[glossary]\nterms = ["iPhone", "Korvex"]\n'
        assert build_prompt(_cfg(toml)) == "iPhone, Korvex."

    def test_nothing_configured_is_an_empty_prompt(self) -> None:
        assert build_prompt(_cfg("[transcribe]\nfillers = []\n")) == ""

    def test_accents_survive(self) -> None:
        toml = '[transcribe]\nfillers = ["éste", "o sea"]\n[glossary]\nterms = ["ñandú"]\n'
        assert build_prompt(_cfg(toml)) == "Éste, o sea. ñandú."
