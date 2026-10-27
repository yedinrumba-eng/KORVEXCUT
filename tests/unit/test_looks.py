"""The table of looks (spec S1.5b, DS3, D10) and its agreement with the one `edl/refs.py` checks
against (001.23 point 3, 001.24 point 15): two lists of ids kept equal by this test.
"""

import pytest

from kcut.config.model import BrandSection
from kcut.edl.refs import LOOK_IDS
from kcut.render.looks import LOOKS, LookDef, look_chain

BRAND = BrandSection("#E5FF1F", "#2FA8FF", "#0B0B0E", "#FFFFFF")

CHAINS = {
    "neutro": "",
    "contraste": "curves=all='0/0 0.25/0.20 0.5/0.5 0.75/0.80 1/1',vibrance=intensity=0.12",
    "calido": "colorbalance=rs=0.04:bs=-0.04:rm=0.03:bm=-0.03:rh=0.02:bh=-0.02,"
    "vibrance=intensity=0.05",
    "frio": "colorbalance=rs=-0.04:bs=0.05:rm=-0.03:bm=0.04:rh=-0.01:bh=0.02",
    "cinematico": "curves=all='0/0.02 0.25/0.21 0.5/0.5 0.75/0.79 1/0.98',"
    "colorbalance=rs=-0.05:gs=0.01:bs=0.05:rh=0.05:gh=0.01:bh=-0.04,"
    "vibrance=intensity=-0.08,vignette=angle=0.5",
    "bn-acento": "colorhold=color=0xE5FF1F:similarity=0.25:blend=0.10",
}


class TestTheTable:
    def test_looks_the_ids_of_refs_and_the_ids_of_looks_are_the_same_list(self) -> None:
        """`edl` does not import `render`, so the EDL check keeps its own list: here they meet."""
        assert frozenset(LOOKS) == LOOK_IDS
        assert set(LOOKS) == {"neutro", "contraste", "calido", "frio", "cinematico", "bn-acento"}

    @pytest.mark.parametrize("look", sorted(CHAINS))
    def test_looks_each_chain_is_the_one_of_the_spec(self, look: str) -> None:
        assert look_chain(look, BRAND) == CHAINS[look]

    def test_looks_the_mapping_is_keyed_by_the_id_of_each_look(self) -> None:
        assert all(key == look.id for key, look in LOOKS.items())
        assert all(isinstance(look, LookDef) for look in LOOKS.values())

    def test_looks_every_look_has_its_texts_for_the_catalog_and_a_cost(self) -> None:
        for look in LOOKS.values():
            assert look.name_es and look.purpose_es and look.avoid_es
            assert look.cost in {"bajo", "medio", "alto"}

    def test_looks_the_purposes_are_the_ones_of_the_spec(self) -> None:
        wanted = {
            "neutro": "sin look",
            "contraste": "más punch y color",
            "calido": "piel cálida, interiores",
            "frio": "tech, noche",
            "cinematico": "teal-naranja suave con viñeta",
            "bn-acento": "blanco y negro salvo el color de marca",
        }
        assert {look.id: look.purpose_es for look in LOOKS.values()} == wanted

    def test_looks_no_chain_names_a_filter_that_only_takes_yuv(self) -> None:
        yuv_only = ("eq=", "hue=", "lut=", "unsharp=", "format=yuv", "scale=")
        for look in LOOKS.values():
            assert not [name for name in yuv_only if name in look.chain], look.id


class TestTheAccent:
    def test_looks_bn_acento_takes_the_accent_of_the_brand_as_0xrrggbb(self) -> None:
        brand = BrandSection("#12ab9F", "#2FA8FF", "#0B0B0E", "#FFFFFF")
        assert look_chain("bn-acento", brand).startswith("colorhold=color=0x12AB9F:")

    def test_looks_the_table_keeps_the_placeholder_and_the_chain_never_does(self) -> None:
        assert "RRGGBB" in LOOKS["bn-acento"].chain
        assert all("RRGGBB" not in look_chain(look, BRAND) for look in LOOKS)

    @pytest.mark.parametrize("accent", ["E5FF1F", "#E5FF1", "#E5FF1FF", "#GGGGGG", "", "red"])
    def test_looks_an_accent_that_is_not_a_hex_color_is_refused(self, accent: str) -> None:
        brand = BrandSection(accent, "#2FA8FF", "#0B0B0E", "#FFFFFF")
        with pytest.raises(ValueError, match="acento"):
            look_chain("bn-acento", brand)

    def test_looks_the_other_looks_do_not_look_at_the_accent(self) -> None:
        brand = BrandSection("nonsense", "#2FA8FF", "#0B0B0E", "#FFFFFF")
        assert look_chain("calido", brand) == CHAINS["calido"]

    def test_looks_a_look_that_does_not_exist_is_a_bug_of_the_caller(self) -> None:
        with pytest.raises(ValueError, match="look desconocido"):
            look_chain("vintage", BRAND)
