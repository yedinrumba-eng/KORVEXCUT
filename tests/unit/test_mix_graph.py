"""The graph of the mix (spec S1.8b row 3, 001.15; lesson 11): the three forms of the spec, to the
letter, and the rule that no label hangs: every output that a filter makes is used by another (and
a leftover output of `asplit` would go to `anullsink`). Pure: nothing is run here; the ducking with
the real ffmpeg is in `tests/integration/test_ducking.py`.
"""

import re

import pytest

from kcut.audio.mix_graph import build_graph, duck_only_graph
from kcut.audio.music_model import DEFAULT_DUCK, DuckCfg

AMIX = "normalize=0:duration=first:dropout_transition=0"
DUCKED = (  # 001.37: `apad` on both inputs of the compressor
    "[0:a]asplit=2[vm][vs];[vs]apad[vsp];[1:a]apad[mp];"
    "[mp][vsp]sidechaincompress=threshold=0.03:ratio=10:attack=15:release=350:makeup=1:knee=2.828"
    f"[md];[vm][md][2:a]amix=inputs=3:{AMIX}[mix]"
)


def test_mix_graph_voice_music_and_ducking_is_the_graph_of_the_spec() -> None:
    assert build_graph(True, True, DEFAULT_DUCK) == (DUCKED, 3)


def test_mix_graph_voice_music_without_ducking_is_the_sum_of_three() -> None:
    assert build_graph(True, False, DEFAULT_DUCK) == (
        f"[0:a][1:a][2:a]amix=inputs=3:{AMIX}[mix]",
        3,
    )


def test_mix_graph_without_music_is_the_voice_and_the_effects() -> None:
    expected = (f"[0:a][1:a]amix=inputs=2:{AMIX}[mix]", 2)
    assert build_graph(False, True, DEFAULT_DUCK) == expected
    assert build_graph(False, False, DEFAULT_DUCK) == expected  # ducking has no music to lower


def test_mix_graph_the_numbers_of_the_ducking_come_from_the_configuration() -> None:
    cfg = DuckCfg(True, 0.05, 6.5, 20.0, 500.0, 2.0, 4.0)
    graph, _ = build_graph(True, True, cfg)
    assert (
        "sidechaincompress=threshold=0.05:ratio=6.5:attack=20:release=500:makeup=2:knee=4" in graph
    )


def _labels(graph: str) -> tuple[list[str], list[str]]:
    """`(made, used)`: the labels that the filters of the graph write as outputs, and the ones they
    read (`[0:a]` and the like are inputs of the file, not made by any filter)."""
    made: list[str] = []
    used: list[str] = []
    for chain in graph.split(";"):
        match = re.fullmatch(r"((?:\[[^\]]+\])*)([^\[\]]+)((?:\[[^\]]+\])*)", chain)
        assert match is not None, chain
        reads, _, writes = match.groups()
        used += re.findall(r"\[([^\]]+)\]", reads)
        made += re.findall(r"\[([^\]]+)\]", writes)
    return made, [label for label in used if not re.fullmatch(r"\d+:a", label)]


@pytest.mark.parametrize(
    ("has_music", "duck"), [(True, True), (True, False), (False, True), (False, False)]
)
def test_mix_graph_no_label_hangs_and_none_is_used_before_it_is_made(
    has_music: bool, duck: bool
) -> None:
    graph, inputs = build_graph(has_music, duck, DEFAULT_DUCK)
    made, used = _labels(graph)
    # every output of a filter is read by another one (`mix` is the output of the whole graph)
    assert sorted(label for label in made if label != "mix") == sorted(used)
    assert made.count("mix") == 1 and "anullsink" not in graph
    ins = {int(m) for m in re.findall(r"\[(\d+):a\]", graph)}
    assert ins == set(range(inputs))  # every input of the file is read, and none that is not there


def test_mix_graph_asplit_has_both_of_its_outputs_used() -> None:
    graph, _ = build_graph(True, True, DEFAULT_DUCK)
    outputs = re.search(r"asplit=(\d+)((?:\[[^\]]+\])+)", graph)
    assert outputs is not None
    names = re.findall(r"\[([^\]]+)\]", outputs.group(2))
    assert len(names) == int(outputs.group(1)) == 2
    rest = graph.replace(outputs.group(0), "")
    assert all(f"[{name}]" in rest for name in names)


def test_mix_graph_the_ducking_alone_makes_md_from_the_music_and_the_voice() -> None:
    graph = duck_only_graph(DEFAULT_DUCK)
    assert graph == (
        "[0:a][1:a]sidechaincompress=threshold=0.03:ratio=10:attack=15:release=350"
        ":makeup=1:knee=2.828[md]"
    )
    assert _labels(graph) == (["md"], [])


def test_mix_graph_has_no_path_nor_text_of_the_user_in_it() -> None:
    for has_music, duck in ((True, True), (True, False), (False, False)):
        graph, _ = build_graph(has_music, duck, DEFAULT_DUCK)
        assert ":\\" not in graph and "/" not in graph and "'" not in graph
