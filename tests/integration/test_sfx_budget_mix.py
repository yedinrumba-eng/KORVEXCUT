"""What `kcut mix` does with the budget of the synthesis (spec S1.8b step 0, 001.36 point 2; row
13). The effects of a plan that last more than 1200 s together (001.37, point 9: it was 600 s) are
one A03 in `events` and nothing is synthesized: the example EDL is 11.5 s long, so 105 `pad` of the
whole video are 1207.5 s. And a `MemoryError` in the synthesis is a ProjectError (exit 3) with a
fixed text. The per-event limit of 30 s needs a video longer than that and is in
`tests/unit/test_sfx_budget.py`.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.integration.mix_helpers import BUILD, audio_project
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]


def _write_sfx(root: Path, events: list[dict[str, Any]]) -> None:
    document = {"schema": "kcut.sfx/1", "events": events}
    (root / "edit" / "sfx.json").write_text(json.dumps(document), encoding="utf-8")


def test_sfx_budget_mix_effects_over_1200_seconds_are_one_a03_and_nothing_is_synthesized(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = audio_project(view_fresh, sfx=False, music=False)
    # 001.37: 105 x 11.5 s = 1207.5 s (it was 53, 609.5 s)
    _write_sfx(root, [{"type": "pad", "at": 0, "dur_f": 345}] * 105)
    monkeypatch.setattr(
        "kcut.audio.mixer.build_sfx_bus", lambda *a, **k: pytest.fail("something was synthesized")
    )
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 1 and doc["ok"] is False, (doc, err)
    assert [(e["code"], e["path"], e["message"]) for e in doc["errors"]] == [
        ("A03", "events", "los efectos suman más de 1200 s de audio")  # 001.37: was 600
    ]
    assert not (root / BUILD / "mix.wav").exists() and not (root / BUILD / "sfx.f32").exists()


def test_sfx_budget_mix_104_pads_are_inside_the_budget_and_get_past_the_check(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """104 x 11.5 s = 1196 s: no A03 (001.37: it was 52 pads, 598 s, against 600 s). The synthesis
    is replaced so the test does not make 20 minutes of audio; what is checked is that the plan
    reaches it."""
    root = audio_project(view_fresh, sfx=False, music=False)
    _write_sfx(root, [{"type": "pad", "at": 0, "dur_f": 345}] * 104)
    seen: list[int] = []

    def stop(events: Any, *_a: Any, **_k: Any) -> Any:
        seen.append(len(events))
        raise MemoryError

    monkeypatch.setattr("kcut.audio.mixer.build_sfx_bus", stop)
    code, doc, err = kcut_json("mix", *project_args(root))
    # 001.37: was [52]; it got to the synthesis (and the stop is exit 3)
    assert seen == [104] and code == 3, (doc, err)


def test_sfx_budget_mix_a_memory_error_in_the_synthesis_is_exit_3_with_a_fixed_text(
    view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = audio_project(view_fresh)

    def no_memory(*_a: Any, **_k: Any) -> Any:
        raise MemoryError

    monkeypatch.setattr("kcut.audio.mixer.build_sfx_bus", no_memory)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert doc["error"]["message"] == "no hay memoria para sintetizar los efectos"
    assert not (root / BUILD / "mix.wav").exists()
