"""Strict schema helpers: types are exact, messages name the path in Spanish (spec 0.9)."""

import math
from typing import Any

import pytest

from kcut.errors import ProjectError
from kcut.schema_util import (
    SchemaError,
    hex_color,
    join_path,
    obj,
    one_of,
    only_keys,
    opt_bool,
    opt_float,
    opt_int,
    opt_list,
    opt_str,
    req_bool,
    req_float,
    req_int,
    req_list,
    req_str,
)


def _msg(call: Any) -> str:
    with pytest.raises(SchemaError) as info:
        call()
    assert isinstance(info.value, ProjectError)
    assert info.value.exit_code == 3
    return info.value.message_es


def test_paths_are_joined_like_the_spec_examples() -> None:
    assert join_path("spans", 3) == "spans[3]"
    assert join_path("spans[3]", "zoom") == "spans[3].zoom"
    assert join_path("", "zoom") == "zoom"


def test_the_range_message_of_the_spec() -> None:
    message = _msg(lambda: req_float({"zoom": 3.4}, "zoom", "spans[3]", 1.0, 3.0))
    assert message == "spans[3].zoom: debe estar entre 1.0 y 3.0 (vino 3.4)"


class TestInts:
    def test_accepts_a_plain_int(self) -> None:
        assert req_int({"n": 30}, "n", "") == 30

    @pytest.mark.parametrize("value", [30.0, True, False, "30", None, [1]])
    def test_rejects_float_bool_and_other_types(self, value: object) -> None:
        assert "n: debe ser un entero" in _msg(lambda: req_int({"n": value}, "n", ""))

    def test_range_and_missing(self) -> None:
        assert "debe ser como mínimo 1" in _msg(lambda: req_int({"n": 0}, "n", "", lo=1))
        assert "debe ser como máximo 5" in _msg(lambda: req_int({"n": 6}, "n", "", hi=5))
        assert "falta" in _msg(lambda: req_int({}, "n", "sec"))

    def test_optional_returns_the_default_when_absent_only(self) -> None:
        assert opt_int({}, "n", "", 7) == 7
        assert opt_int({}, "n", "", None) is None
        assert opt_int({"n": 2}, "n", "", 7) == 2
        assert "n:" in _msg(lambda: opt_int({"n": 2.0}, "n", "", 7))


class TestFloats:
    def test_accepts_int_and_float(self) -> None:
        assert req_float({"x": 2}, "x", "") == 2.0
        assert isinstance(req_float({"x": 2}, "x", ""), float)
        assert req_float({"x": -0.5}, "x", "") == -0.5

    @pytest.mark.parametrize("value", [True, "1.0", None, math.nan, math.inf, -math.inf])
    def test_rejects_bool_nan_inf_and_other_types(self, value: object) -> None:
        assert "debe ser un número finito" in _msg(lambda: req_float({"x": value}, "x", ""))

    def test_optional(self) -> None:
        assert opt_float({}, "x", "", 0.5) == 0.5
        assert opt_float({"x": 1}, "x", "", 0.5, 0.0, 1.0) == 1.0


class TestStringsBoolsLists:
    def test_str_length_rules(self) -> None:
        assert req_str({"s": "ab"}, "s", "", max_len=2) == "ab"
        assert "entre 0 y 2 caracteres" in _msg(lambda: req_str({"s": "abc"}, "s", "", max_len=2))
        assert "al menos 1" in _msg(lambda: req_str({"s": ""}, "s", "", min_len=1))
        assert "debe ser texto" in _msg(lambda: req_str({"s": 3}, "s", ""))
        assert opt_str({}, "s", "", "x") == "x"

    def test_bool_is_exact(self) -> None:
        assert req_bool({"b": False}, "b", "") is False
        assert "verdadero o falso" in _msg(lambda: req_bool({"b": 0}, "b", ""))
        assert opt_bool({}, "b", "", True) is True

    def test_list(self) -> None:
        assert req_list({"l": [1, 2]}, "l", "") == [1, 2]
        assert "lista" in _msg(lambda: req_list({"l": {}}, "l", ""))
        assert opt_list({}, "l", "", None) is None


class TestObjectsAndKeys:
    def test_obj(self) -> None:
        assert obj({"a": 1}, "x") == {"a": 1}
        assert "x: debe ser un objeto" in _msg(lambda: obj([], "x"))

    def test_unknown_key_is_named_with_its_path(self) -> None:
        message = _msg(lambda: only_keys({"in_f": 1, "zoom": 2}, {"in_f"}, "spans[3]"))
        assert message == "spans[3].zoom: clave desconocida"

    def test_known_keys_pass(self) -> None:
        only_keys({"a": 1}, {"a", "b"}, "")


class TestColorsAndChoices:
    def test_hex_is_normalized(self) -> None:
        assert hex_color("#e5ff1f", "c") == "#E5FF1F"

    @pytest.mark.parametrize(
        "value", ["e5ff1f", "#e5ff1", "#e5ff1fa", "#ggg000", "#e5ff1f\n", 5, None]
    )
    def test_bad_hex(self, value: object) -> None:
        assert "c: debe ser un color #RRGGBB" in _msg(lambda: hex_color(value, "c"))

    def test_one_of(self) -> None:
        assert one_of("a", ("a", "b"), "p") == "a"
        assert "debe ser uno de: a, b (vino 'c')" in _msg(lambda: one_of("c", ("a", "b"), "p"))
