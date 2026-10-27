"""The guard of `.kcut/` names a work file by class and clip in the commands (spec S1.6b round 1,
001.31 point 8; row 26): a junction that leaves `.kcut/` where the wav16 of a clip goes is exit 3
for `kcut ingest` with `wav16 de a1` in the message, and one where a mezzanine goes is exit 3 for
`kcut render` with `mezz de a1`; neither names the file (its name has the slug of the original clip,
which may hold a phone number). Nothing is written through the link.
"""

from pathlib import Path

import pytest

from kcut import cli
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.integration.render_small_cases import mezz_files, small, small_base
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["small", "small_base"]
SLUG = "ana-perez-809-555-1234"  # of `Ana Perez 809-555-1234.mp4`, as `ingest` makes it
LEAKS = ("ana", "perez", "809", "555", "1234")


@pytest.mark.ffmpeg
@pytest.mark.slow
def test_cache_guard_label_v2_ingest_with_a_junction_where_the_wav16_goes_names_the_clip(
    two_cameras: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    crudo = two_cameras / "crudo"
    (crudo / "cam a.mp4").rename(crudo / "Ana Perez 809-555-1234.mp4")
    wav = two_cameras / ".kcut" / "wav16" / f"a1_{SLUG}.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "ajeno"
    outside.mkdir()
    make_dir_link(wav, outside)
    try:
        code = cli.main(["ingest", "--no-proxy", "--json", "--project", str(two_cameras)])
    finally:
        remove_dir_link(wav)  # the link, not what it points at
    captured = capsys.readouterr()
    assert code == 3, captured.out
    assert "wav16 de a1 queda fuera de .kcut/" in captured.out
    assert not any(piece in (captured.out + captured.err).lower() for piece in LEAKS)
    assert list(outside.iterdir()) == []


@pytest.mark.ffmpeg
@pytest.mark.slow
def test_cache_guard_label_v2_render_with_a_junction_where_a_mezzanine_goes_names_the_clip(
    small: Path, kcut_json: Run
) -> None:
    (mezz,) = mezz_files(small)
    mezz.with_name(f"{mezz.name}.json").unlink()  # not fresh: it is made again
    mezz.unlink()
    outside = small / "salida"  # inside the project, outside `.kcut/`
    outside.mkdir(exist_ok=True)
    make_dir_link(mezz, outside)
    try:
        code, doc, err = kcut_json("render", "--no-graphics", *project_args(small))
    finally:
        remove_dir_link(mezz)
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert doc["error"]["message"].startswith("mezz de a1 queda fuera de .kcut/")
    assert list(outside.iterdir()) == []
