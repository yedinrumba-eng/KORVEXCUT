"""kcut.toml: the template parses, unknown keys and bad ranges fail naming their path."""

import dataclasses
from pathlib import Path

import pytest

from kcut.config.load import load_config, parse_config
from kcut.config.names import clean_default_name
from kcut.config.template import render_template
from kcut.errors import ProjectError
from tests.unit.config_cases import RANGE_CASES
from tests.unit.config_golden import GOLDEN_9X16


def _fail(text: str) -> str:
    with pytest.raises(ProjectError) as info:
        parse_config(text, default_name="x")
    assert info.value.exit_code == 3
    return info.value.message_es


class TestTemplate:
    def test_matches_the_spec_text_exactly(self) -> None:
        assert render_template("piloto-01", "9:16", 30, "es", "2026-10-16") == GOLDEN_9X16

    def test_16x9_changes_only_the_preset_and_safe_zones(self) -> None:
        text = render_template("piloto-01", "16:9", 30, "es", "2026-10-16")
        expected = GOLDEN_9X16.replace('preset = "9:16"', 'preset = "16:9"')
        expected = expected.replace("safe_top_px = 250", "safe_top_px = 60")
        assert text == expected.replace("safe_bottom_px = 500", "safe_bottom_px = 120")

    def test_english_fillers(self) -> None:
        text = render_template("x", "9:16", 30, "en", "2026-10-16")
        assert 'fillers = ["uh", "um", "uhm", "er", "hmm"]' in text
        assert 'language = "en"' in text

    @pytest.mark.parametrize(("preset", "size"), [("9:16", (1080, 1920)), ("16:9", (1920, 1080))])
    @pytest.mark.parametrize("language", ["es", "en"])
    def test_every_variant_parses_back(
        self, preset: str, size: tuple[int, int], language: str
    ) -> None:
        cfg = parse_config(
            render_template("mi video", preset, 25, language, "2026-10-16"), default_name="z"
        )
        assert (cfg.output.preset, cfg.output.fps) == (preset, 25)
        assert (cfg.output.w, cfg.output.h) == size
        assert (cfg.project.name, cfg.project.language) == ("mi video", language)

    def test_awkward_name_survives_the_toml_escaping(self) -> None:
        name = 'Camión "rojo" \\ ñandú #1'
        cfg = parse_config(render_template(name, "9:16", 30, "es", "2026-10-16"), default_name="z")
        assert cfg.project.name == name

    def test_defaults_of_the_template(self) -> None:
        cfg = parse_config(GOLDEN_9X16, default_name="z")
        assert (cfg.output.safe_top_px, cfg.output.safe_bottom_px) == (250, 500)
        assert cfg.brand.accent2 == "#2FA8FF"
        assert cfg.transcribe.model == "medium"
        assert cfg.transcribe.fillers[:3] == ("eh", "ehh", "em")
        assert (cfg.analysis.silence_db, cfg.analysis.long_pause_ms) == (-42.0, 700)
        assert (cfg.sync.min_score, cfg.sync.min_ratio, cfg.sync.max_drift_ms) == (0.35, 1.5, 20)
        assert cfg.sync.min_refine_corr == 0.1
        assert dict(cfg.sync.manual) == {}
        assert (cfg.captions.y, cfg.captions.font_px) == (0.617, 76)
        assert cfg.captions.active_color == ""
        assert cfg.audio.voice.highpass_hz == 80
        assert (cfg.qa.max_tp, cfg.qa.max_av_delta_ms) == (-1.0, 25)
        assert cfg.storyboard.min_beat_ms == 500
        assert cfg.glossary == ()


class TestDefaults:
    def test_empty_file_is_all_defaults_and_name_is_the_folder(self) -> None:
        cfg = parse_config("", default_name="mi carpeta")
        assert cfg.project.name == "mi carpeta"
        assert cfg.output.preset == "9:16"
        assert cfg.output.fps == 30

    def test_an_empty_file_equals_the_template_defaults(self) -> None:
        empty = parse_config("", default_name="piloto-01")
        golden = parse_config(GOLDEN_9X16, default_name="piloto-01")
        assert dataclasses.replace(empty, project=golden.project) == golden

    def test_16x9_gets_its_own_safe_zone_default(self) -> None:
        cfg = parse_config('[output]\npreset = "16:9"\n', default_name="x")
        assert (cfg.output.w, cfg.output.h) == (1920, 1080)
        assert (cfg.output.safe_top_px, cfg.output.safe_bottom_px) == (60, 120)

    def test_hex_colors_are_normalized_to_upper_case(self) -> None:
        cfg = parse_config('[brand]\naccent = "#e5ff1f"\n', default_name="x")
        assert cfg.brand.accent == "#E5FF1F"

    def test_the_model_is_immutable(self) -> None:
        cfg = parse_config("", default_name="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.output.fps = 24  # type: ignore[misc]
        with pytest.raises(TypeError):
            cfg.sync.manual["a2"] = 5  # type: ignore[index]


class TestUnknownKeys:
    def test_unknown_section(self) -> None:
        assert "extra" in _fail("[extra]\nx = 1\n")

    def test_unknown_key_in_a_section_is_named(self) -> None:
        message = _fail('[transcribe]\nmodle = "base"\n')
        assert "transcribe.modle" in message
        assert "desconocida" in message

    def test_unknown_key_in_a_nested_table(self) -> None:
        assert "audio.voice.gain" in _fail("[audio.voice]\ngain = 3\n")

    def test_w_and_h_are_derived_not_configurable(self) -> None:
        assert "output.w" in _fail("[output]\nw = 1080\n")


class TestRanges:
    @pytest.mark.parametrize(("text", "path"), RANGE_CASES)
    def test_out_of_range_value_names_its_path(self, text: str, path: str) -> None:
        assert path in _fail(text)

    def test_boundaries_are_accepted(self) -> None:
        text = (
            "[output]\nfps = 60\nsafe_top_px = 600\n[transcribe]\nbeam_size = 10\n"
            "cpu_threads = 64\n[analysis]\nphrase_pause_ms = 700\nlong_pause_ms = 700\n"
            "[captions]\ny = 0\nmax_words = 6\n"
        )
        cfg = parse_config(text, default_name="x")
        assert (cfg.output.fps, cfg.transcribe.beam_size, cfg.analysis.long_pause_ms) == (
            60,
            10,
            700,
        )

    def test_project_name_cannot_carry_line_breaks(self) -> None:
        assert "project.name" in _fail('[project]\nname = "a\\nb"\n')

    def test_manual_offsets_are_kept(self) -> None:
        cfg = parse_config("[sync.manual]\na2 = 1200\ns1 = -35\n", default_name="x")
        assert dict(cfg.sync.manual) == {"a2": 1200, "s1": -35}


class TestLoadFromDisk:
    def test_malformed_toml(self, tmp_path: Path) -> None:
        bad = tmp_path / "kcut.toml"
        bad.write_text("[output\nfps = 30", encoding="utf-8")
        with pytest.raises(ProjectError, match="TOML"):
            load_config(bad)

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectError, match="no existe"):
            load_config(tmp_path / "kcut.toml")

    def test_error_message_carries_the_file_name(self, tmp_path: Path) -> None:
        bad = tmp_path / "kcut.toml"
        bad.write_text("[output]\nfps = 31\n", encoding="utf-8")
        with pytest.raises(ProjectError, match=r"kcut\.toml: output\.fps"):
            load_config(bad)

    def test_default_name_is_the_project_folder(self, tmp_path: Path) -> None:
        folder = tmp_path / "video ñandú"
        folder.mkdir()
        (folder / "kcut.toml").write_text("", encoding="utf-8")
        assert load_config(folder / "kcut.toml").project.name == "video ñandú"


class TestProjectName:
    @pytest.mark.parametrize(
        "escape",
        ["u2028", "u2029", "u0085", "u202e", "u200b", "u0007", "u007f", "u200e", "u2066", "n", "t"],
    )
    def test_name_rejects_separators_control_and_format_characters(self, escape: str) -> None:
        message = _fail('[project]\nname = "a\\' + escape + 'b"\n')
        assert "project.name" in message

    def test_name_keeps_ordinary_text(self) -> None:
        text = '[project]\nname = "Camión \\"rojo\\" ñandú #1 - 日本"\n'
        assert parse_config(text, default_name="x").project.name == 'Camión "rojo" ñandú #1 - 日本'

    def test_name_longer_than_80_is_rejected_in_the_file(self) -> None:
        assert "project.name" in _fail('[project]\nname = "' + "n" * 81 + '"\n')

    def test_default_name_drops_forbidden_characters_and_is_cut_to_80(self) -> None:
        folder = "mi‮ video​ " + "x" * 100
        cfg = parse_config("", default_name=folder)
        assert cfg.project.name == ("mi video" + "x" * 100)[:80]
        assert len(cfg.project.name) == 80

    def test_default_name_falls_back_to_proyecto(self) -> None:
        assert parse_config("", default_name="‮​").project.name == "proyecto"
        assert clean_default_name("") == "proyecto"

    def test_default_name_of_a_folder_with_a_separator_in_it(self, tmp_path: Path) -> None:
        folder = tmp_path / "vid eo"
        try:
            folder.mkdir()
        except OSError:
            pytest.skip("este sistema de archivos no acepta U+2028 en un nombre")
        (folder / "kcut.toml").write_text("", encoding="utf-8")
        assert load_config(folder / "kcut.toml").project.name == "video"


class TestFullmatch:
    @pytest.mark.parametrize(
        ("toml", "path"),
        [
            ('[project]\nlanguage = "es\\n"\n', "project.language"),
            ('[project]\nlanguage = "xes"\n', "project.language"),
            ('[project]\ncreated = "2026-10-16\\n"\n', "project.created"),
            ('[sync]\nmaster = "a1\\n"\n', "sync.master"),
            ('[sync.manual]\n"a2\\n" = 5\n', "sync.manual"),
        ],
    )
    def test_fullmatch_refuses_a_value_with_a_trailing_newline(self, toml: str, path: str) -> None:
        assert path in _fail(toml)

    def test_fullmatch_still_accepts_the_good_values(self) -> None:
        text = '[project]\nlanguage = "en"\ncreated = "2026-10-16"\n[sync]\nmaster = "a1"\n'
        cfg = parse_config(text, default_name="x")
        assert (cfg.project.language, cfg.project.created) == ("en", "2026-10-16")
        assert cfg.sync.master == "a1"


class TestIngestSection:
    def test_defaults(self) -> None:
        cfg = parse_config("", default_name="x")
        assert (cfg.ingest.warn_duration_h, cfg.ingest.max_duration_h) == (3.0, 12.0)

    def test_ints_are_accepted_and_stored_as_floats(self) -> None:
        text = "[ingest]\nwarn_duration_h = 1\nmax_duration_h = 2\n"
        cfg = parse_config(text, default_name="x")
        assert cfg.ingest.warn_duration_h == 1.0
        assert isinstance(cfg.ingest.warn_duration_h, float)

    @pytest.mark.parametrize(
        ("toml", "path"),
        [
            ("[ingest]\nwarn_duration_h = 0.05\n", "ingest.warn_duration_h"),
            ("[ingest]\nwarn_duration_h = 49\n", "ingest.warn_duration_h"),
            ("[ingest]\nmax_duration_h = 49\n", "ingest.max_duration_h"),
            ("[ingest]\nwarn_duration_h = 5\nmax_duration_h = 4\n", "ingest.max_duration_h"),
            ("[ingest]\nwarn_duration_h = 13\n", "ingest.max_duration_h"),
            ("[ingest]\nhoras = 4\n", "ingest.horas"),
            ("[ingest]\nwarn_duration_h = true\n", "ingest.warn_duration_h"),
        ],
    )
    def test_ranges_name_their_path(self, toml: str, path: str) -> None:
        assert path in _fail(toml)

    def test_the_template_carries_the_section(self) -> None:
        text = render_template("x", "9:16", 30, "es", "2026-10-16")
        assert text.endswith("[ingest]\nwarn_duration_h = 3\nmax_duration_h = 12\n")
