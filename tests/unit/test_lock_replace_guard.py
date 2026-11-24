"""The pieces under the guard of the folder before a move or a delete (spec 001.38, point 2;
S1.9a rows 12 and 13), without a mix: `atomic_replace` turns every `OSError` into a ProjectError,
`discard_partial` deletes nothing when its `guard` says the folder is not the same one, and
`write_f32_blocks` calls its `guard` right before `os.replace` and right before the partial is
deleted. `prepare_partial` says the reason before the path.
"""

import errno
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut.audio.f32write import write_f32_blocks
from kcut.errors import ProjectError
from kcut.render.lock import atomic_replace, discard_partial, prepare_partial


def _fail(exc: BaseException) -> Any:
    def replace(_src: object, _dst: object) -> None:
        raise exc

    return replace


def test_replace_guard_atomic_replace_moves_the_file(tmp_path: Path) -> None:
    (tmp_path / "a.partial").write_bytes(b"new")
    atomic_replace(tmp_path / "a.partial", tmp_path / "a")
    assert (tmp_path / "a").read_bytes() == b"new" and not (tmp_path / "a.partial").exists()


def test_replace_guard_atomic_replace_a_permission_error_keeps_its_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "replace", _fail(PermissionError(13, "Acceso denegado")))
    with pytest.raises(ProjectError) as info:
        atomic_replace(tmp_path / "a.partial", tmp_path / "a")
    assert info.value.message_es == f"cierra el archivo {tmp_path / 'a'} en el reproductor y repite"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (FileNotFoundError(), "FileNotFoundError"),
        (FileNotFoundError(2, "No existe el archivo"), "No existe el archivo"),
        (NotADirectoryError(20, "No es un directorio"), "No es un directorio"),
        (OSError(errno.ENOSPC, "No space left on device"), "No space left on device"),
        (OSError(), "OSError"),
    ],
)
def test_replace_guard_atomic_replace_any_other_oserror_is_a_project_error_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError, reason: str
) -> None:
    monkeypatch.setattr(os, "replace", _fail(error))
    with pytest.raises(ProjectError) as info:
        atomic_replace(tmp_path / "a.partial", tmp_path / "a")
    assert info.value.exit_code == 3
    assert info.value.message_es == f"no pude mover el archivo ({reason})"


def test_replace_guard_atomic_replace_the_message_has_no_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = FileNotFoundError(2, "No existe", str(tmp_path / "Maria-809-555-1234.partial"))
    monkeypatch.setattr(os, "replace", _fail(named))
    with pytest.raises(ProjectError) as info:
        atomic_replace(tmp_path / "x.partial", tmp_path / "x")
    assert "Maria" not in info.value.message_es and "809" not in info.value.message_es


def test_replace_guard_discard_partial_without_a_guard_deletes_the_file(tmp_path: Path) -> None:
    (tmp_path / "a.partial").write_bytes(b"x")
    discard_partial(tmp_path / "a.partial")
    assert not (tmp_path / "a.partial").exists()


def test_replace_guard_discard_partial_asks_the_guard_first_and_deletes_if_it_passes(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.partial").write_bytes(b"x")
    calls: list[str] = []
    discard_partial(tmp_path / "a.partial", lambda: calls.append("looked"))
    assert calls == ["looked"] and not (tmp_path / "a.partial").exists()


def test_replace_guard_discard_partial_leaves_the_file_when_the_guard_refuses(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.partial").write_bytes(b"not mine any more")

    def refuse() -> None:
        raise ProjectError("la carpeta ya no es la suya")

    discard_partial(tmp_path / "a.partial", refuse)  # and it does not raise either
    assert (tmp_path / "a.partial").read_bytes() == b"not mine any more"


def test_replace_guard_discard_partial_a_missing_file_is_nothing(tmp_path: Path) -> None:
    discard_partial(tmp_path / "never.partial", lambda: None)


def test_replace_guard_write_f32_blocks_calls_the_guard_before_the_move_and_before_the_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    real = os.replace

    def replace(src: Any, dst: Any) -> None:
        events.append("replace")
        real(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    write_f32_blocks(
        tmp_path / "v.f32", [np.ones(3, dtype=np.float32)], guard=lambda: events.append("guard")
    )
    assert events == ["guard", "replace", "guard"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["v.f32"]


def test_replace_guard_write_f32_blocks_a_refusing_guard_moves_and_deletes_nothing(
    tmp_path: Path,
) -> None:
    target = tmp_path / "v.f32"
    target.write_bytes(b"old")

    def refuse() -> None:
        raise ProjectError("la carpeta ya no es la suya")

    with pytest.raises(ProjectError, match="ya no es la suya"):
        write_f32_blocks(target, [np.ones(3, dtype=np.float32)], guard=refuse)
    assert target.read_bytes() == b"old"  # nothing was moved over it
    # and the partial was not deleted either: the name may be a file of somebody else's folder
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".partial")] == [
        f"v.f32.{os.getpid()}.partial"
    ]


def test_replace_guard_write_f32_blocks_without_a_guard_is_as_it_was(tmp_path: Path) -> None:
    write_f32_blocks(tmp_path / "v.f32", [np.ones(2, dtype=np.float32)])
    assert (tmp_path / "v.f32").stat().st_size == 8
    assert sorted(p.name for p in tmp_path.iterdir()) == ["v.f32"]


def test_prepare_partial_reason_comes_before_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    partial = tmp_path / "voice_chain.f32.1234.partial"
    partial.write_bytes(b"x")

    def unlink(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError(13, "Acceso denegado", str(self))

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(ProjectError) as info:
        prepare_partial(partial)
    assert info.value.message_es == f"no pude borrar (Acceso denegado) {partial}"
    assert info.value.message_es.count(str(partial)) == 1  # the path is not repeated


def test_prepare_partial_reason_without_a_system_text_is_the_name_of_the_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    partial = tmp_path / "x.partial"

    def unlink(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError()

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(ProjectError) as info:
        prepare_partial(partial)
    assert info.value.message_es == f"no pude borrar (PermissionError) {partial}"
