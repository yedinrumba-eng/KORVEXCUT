"""`write_bytes_atomic`: the PNG and JPG of kcut, written like the text files (spec 001.15).

Same road as `write_text_atomic`: a folder in the target, a stale `.tmp`, a target open in a
viewer and any other disk failure end in a ProjectError, and the target is never half written.
"""

from pathlib import Path

import pytest

from kcut import jsonio
from kcut.errors import ProjectError, UsageError

DATA = bytes(range(256)) + b"\r\n\n\r\x00fin"  # every byte value, and newlines that must not change


def test_write_bytes_atomic_writes_exactly_the_bytes(tmp_path: Path) -> None:
    target = tmp_path / "foto.png"
    jsonio.write_bytes_atomic(target, DATA)
    assert target.read_bytes() == DATA
    assert not (tmp_path / "foto.png.tmp").exists()


def test_write_bytes_atomic_replaces_a_file_that_was_there(tmp_path: Path) -> None:
    target = tmp_path / "foto.png"
    target.write_bytes(b"viejo, y mas largo que lo nuevo")
    jsonio.write_bytes_atomic(target, b"nuevo")
    assert target.read_bytes() == b"nuevo"


def test_write_bytes_atomic_makes_the_folders_of_the_target(tmp_path: Path) -> None:
    target = tmp_path / "proyecto ñandú" / "qa" / "v1" / "contacto.jpg"
    jsonio.write_bytes_atomic(target, b"jpg")
    assert target.read_bytes() == b"jpg"


def test_write_bytes_atomic_an_empty_payload_is_an_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "vacio.png"
    jsonio.write_bytes_atomic(target, b"")
    assert target.read_bytes() == b""


def test_write_bytes_atomic_a_folder_in_the_target_is_a_project_error(tmp_path: Path) -> None:
    target = tmp_path / "foto.png"
    target.mkdir()
    with pytest.raises(ProjectError) as info:
        jsonio.write_bytes_atomic(target, b"x")
    assert info.value.exit_code == 3
    assert "hay una carpeta donde kcut espera un archivo" in info.value.message_es
    assert target.is_dir()


def test_write_bytes_atomic_a_stale_tmp_is_replaced_not_written_through(tmp_path: Path) -> None:
    target = tmp_path / "foto.png"
    (tmp_path / "foto.png.tmp").write_bytes(b"resto de una corrida que murio")
    jsonio.write_bytes_atomic(target, b"bien")
    assert target.read_bytes() == b"bien" and not (tmp_path / "foto.png.tmp").exists()


def test_write_bytes_atomic_a_target_open_in_a_viewer_says_to_close_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "foto.png"
    target.write_bytes(b"abierto en el visor")

    def locked(src: object, dst: object) -> None:
        raise PermissionError("el archivo esta en uso")

    monkeypatch.setattr(jsonio.os, "replace", locked)
    with pytest.raises(ProjectError) as info:
        jsonio.write_bytes_atomic(target, b"nuevo")
    assert f"cierra el archivo {target} en el reproductor y repite" == info.value.message_es
    assert target.read_bytes() == b"abierto en el visor"  # untouched
    assert not (tmp_path / "foto.png.tmp").exists()  # and no leftover


def test_write_bytes_atomic_any_other_disk_failure_is_a_project_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full(src: object, dst: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(jsonio.os, "replace", full)
    with pytest.raises(ProjectError, match="no pude escribir"):
        jsonio.write_bytes_atomic(tmp_path / "foto.png", b"x")
    assert not (tmp_path / "foto.png.tmp").exists()


def test_out_bad_name_a_parent_that_is_a_file_is_a_project_error_not_an_os_error(
    tmp_path: Path,
) -> None:
    (tmp_path / "vista.png").write_bytes(b"soy un archivo")
    for writer, payload in ((jsonio.write_bytes_atomic, b"x"), (jsonio.write_text_atomic, "x")):
        with pytest.raises(ProjectError) as info:
            writer(tmp_path / "vista.png" / "otra.png", payload)  # type: ignore[operator]
        assert info.value.exit_code == 3


def test_out_bad_name_a_mkdir_that_fails_is_a_project_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError(13, "Acceso denegado")

    monkeypatch.setattr(Path, "mkdir", refuse)
    with pytest.raises(ProjectError) as info:
        jsonio.write_bytes_atomic(tmp_path / "nueva" / "foto.png", b"x")
    assert info.value.exit_code == 3 and "nueva" in info.value.message_es


@pytest.mark.parametrize(
    "name", ["a*b.png", "a?b.png", "a<b>.png", "a|b.png", 'a"b.png', "x" * 300]
)
def test_out_bad_name_a_name_the_system_refuses_is_a_project_error(
    tmp_path: Path, name: str
) -> None:
    with pytest.raises(ProjectError) as info:
        jsonio.write_bytes_atomic(tmp_path / name, b"x")
    assert info.value.exit_code == 3


def test_no_replace_race_a_file_that_is_there_is_a_usage_error_and_stays_as_it_was(
    tmp_path: Path,
) -> None:
    target = tmp_path / "foto.png"
    target.write_bytes(b"llego antes")
    with pytest.raises(UsageError) as info:
        jsonio.write_bytes_atomic(target, b"nuevo", replace=False)
    assert info.value.exit_code == 2
    assert "foto.png" in info.value.message_es and "--force" in info.value.message_es
    assert target.read_bytes() == b"llego antes"
    assert not (tmp_path / "foto.png.tmp").exists()  # and no leftover


def test_no_replace_race_a_file_that_appears_just_before_the_rename_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gap `assert_writable` cannot close: the target is not there when it looks, and is
    there when the bytes are ready (001.21, point 6)."""
    target = tmp_path / "foto.png"
    real = jsonio.os.rename

    def late(src: object, dst: object) -> None:
        target.write_bytes(b"otro proceso")  # created after the check, before the move
        real(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(jsonio.os, "rename", late)
    with pytest.raises(UsageError, match="ya existe"):
        jsonio.write_bytes_atomic(target, b"nuevo", replace=False)
    assert target.read_bytes() == b"otro proceso"
    assert not (tmp_path / "foto.png.tmp").exists()


def test_no_replace_race_a_new_file_is_written_and_leaves_no_tmp(tmp_path: Path) -> None:
    target = tmp_path / "nueva" / "foto.png"
    jsonio.write_bytes_atomic(target, DATA, replace=False)
    assert target.read_bytes() == DATA and not (tmp_path / "nueva" / "foto.png.tmp").exists()


def test_no_replace_race_replace_true_is_still_the_default_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "foto.png"
    target.write_bytes(b"viejo")
    jsonio.write_bytes_atomic(target, b"nuevo", replace=True)
    assert target.read_bytes() == b"nuevo"


def test_no_replace_race_a_folder_in_the_target_is_still_the_known_project_error(
    tmp_path: Path,
) -> None:
    (tmp_path / "foto.png").mkdir()
    with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo"):
        jsonio.write_bytes_atomic(tmp_path / "foto.png", b"x", replace=False)
