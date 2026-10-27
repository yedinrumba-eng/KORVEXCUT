"""Layers without cycles (spec S1.5a row 12, 001.15 T1): `edl` does not reach up into the packages
that use it. A fresh interpreter imports the two reading modules and looks at what got loaded.
"""

import subprocess
import sys

CODE = (
    "import sys, kcut.edl.check, kcut.edl.kept; "
    "ok = {'kcut.audio', 'kcut.audio.wavio', 'kcut.render', 'kcut.render.geometry'}; "
    "bad = sorted(m for m in sys.modules "
    "if m.startswith(('kcut.gfx', 'kcut.audio', 'kcut.render', 'kcut.storyboard')) "
    "and m not in ok); "
    "print(bad); sys.exit(1 if bad else 0)"
)


def test_edl_layers_check_and_kept_load_no_gfx_storyboard_audio_or_render() -> None:
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", CODE],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert (done.returncode, done.stdout.strip()) == (0, "[]"), done.stderr


def test_edl_layers_the_issue_module_imports_nothing_of_kcut() -> None:
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c",
         "import sys, kcut.issues; print(sorted(m for m in sys.modules if m.startswith('kcut')))"],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )  # fmt: skip
    assert done.stdout.strip() == "['kcut', 'kcut.issues']", done.stderr


def test_edl_layers_kept_loads_no_command_and_unmasked_lives_in_pack_pii() -> None:
    """001.24 point 8 (S1.5b row 25): `UNMASKED` is in `kcut/pack/pii.py`, so `edl.kept` no longer
    pulls `kcut.commands.pack` (a CLI module) into a library."""
    code = (
        "import sys, kcut.edl.kept; "
        "bad = [m for m in sys.modules if m.startswith('kcut.commands')]; "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", code],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert (done.returncode, done.stdout.strip()) == (0, "[]"), done.stderr
    from kcut.commands import pack, view
    from kcut.pack import pii

    assert pack.UNMASKED is pii.UNMASKED is view.UNMASKED
