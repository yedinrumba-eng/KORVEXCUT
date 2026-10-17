"""Slugs for cache names and the quick content hash of raw files."""

import hashlib
from pathlib import Path

import pytest

from kcut.ingest.naming import qhash, slugify

MIB = 1024 * 1024


class TestSlugify:
    @pytest.mark.parametrize(
        ("name", "slug"),
        [
            ("crudo 1", "crudo-1"),
            ("Crudo 1", "crudo-1"),
            ("cámara ñandú", "camara-nandu"),
            ("  --Hola__Mundo!!  ", "hola-mundo"),
            ("IMG_0001.MOV", "img-0001-mov"),
            ("a" * 100, "a" * 40),
            ("", "clip"),
            ("***", "clip"),
            ("日本語", "clip"),
            ("ｆｕｌｌ ｗｉｄｔｈ", "full-width"),
        ],
    )
    def test_cases(self, name: str, slug: str) -> None:
        assert slugify(name) == slug

    def test_never_longer_than_40_and_never_ends_with_a_dash(self) -> None:
        slug = slugify("palabra " * 20)
        assert len(slug) <= 40
        assert not slug.endswith("-")
        assert not slug.startswith("-")

    def test_only_safe_characters(self) -> None:
        slug = slugify('a<b>c:d"e/f\\g|h?i*j k')
        assert set(slug) <= set("abcdefghijklmnopqrstuvwxyz0123456789-")


class TestQhash:
    def test_small_file_matches_the_documented_recipe(self, tmp_path: Path) -> None:
        path = tmp_path / "pequeno.bin"
        path.write_bytes(b"hola")
        expected = hashlib.sha256((4).to_bytes(8, "little") + b"hola" + b"hola").hexdigest()
        assert qhash(path) == f"sha256:{expected}"

    def test_big_file_hashes_size_first_and_last_8_mib(self, tmp_path: Path) -> None:
        body = bytes(range(256)) * (20 * MIB // 256)
        path = tmp_path / "grande.bin"
        path.write_bytes(body)
        expected = hashlib.sha256(
            len(body).to_bytes(8, "little") + body[: 8 * MIB] + body[-8 * MIB :]
        ).hexdigest()
        assert qhash(path) == f"sha256:{expected}"

    def test_the_middle_is_not_read_but_the_ends_and_size_are(self, tmp_path: Path) -> None:
        body = bytearray(b"\x01" * (20 * MIB))
        path = tmp_path / "x.bin"
        path.write_bytes(bytes(body))
        base = qhash(path)

        body[10 * MIB] = 9  # middle: invisible on purpose (that is what makes it quick)
        path.write_bytes(bytes(body))
        assert qhash(path) == base

        body[-1] = 9  # last byte
        path.write_bytes(bytes(body))
        assert qhash(path) != base

    def test_size_is_part_of_the_hash(self, tmp_path: Path) -> None:
        (tmp_path / "a.bin").write_bytes(b"\x01" * (20 * MIB))
        (tmp_path / "b.bin").write_bytes(b"\x01" * (21 * MIB))  # same first and last 8 MiB
        assert qhash(tmp_path / "a.bin") != qhash(tmp_path / "b.bin")

    def test_same_content_other_name_same_hash(self, tmp_path: Path) -> None:
        (tmp_path / "a.mov").write_bytes(b"contenido")
        (tmp_path / "b.mov").write_bytes(b"contenido")
        assert qhash(tmp_path / "a.mov") == qhash(tmp_path / "b.mov")

    def test_empty_file(self, tmp_path: Path) -> None:
        (tmp_path / "vacio").write_bytes(b"")
        assert qhash(tmp_path / "vacio") == "sha256:" + hashlib.sha256(bytes(8)).hexdigest()
