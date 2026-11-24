"""The ear of `kcut qa` (spec S1.9a, row 7; 001.15): the audio of `salida/vN.mp4` goes to
`.kcut/qa_ear/vN.wav` (through `vN.partial.wav`), Whisper writes it down, and the result is kept in
`.kcut/qa_ear/<key>.json` (format `kcut.transcript/1`, clip id `qa`), so the second time nothing is
transcribed. A file that does not validate counts as absent (`cache_rebuilt`) and is heard again.
Nothing is written in `.kcut/transcripts/`, where the ids are the ones of clips.
"""

import json
from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.ingest.inventory import Notice
from kcut.paths import Layout
from kcut.project import Project, check_layout_inside
from kcut.qa import ear
from kcut.qa.ear import Heard, hear
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.unit.gfx_resolve_fakes import make_project, with_privacy
from tests.unit.qa_fakes import NoModel, fake_extraction, install_ear

SPOKEN = [("Hola", 200, 600), ("esto", 700, 1000), ("funciona", 1100, 1700)]
LIMIT_S = 13.5  # 001.47: `limit_s` is mandatory; the length of the example EDL plus 2 s


@pytest.fixture
def project(tmp_path: Path, fake_tools: None) -> Project:
    project = make_project(tmp_path)
    (project.root / "salida").mkdir()
    (project.root / "salida" / "v1.mp4").write_bytes(b"not a video: the extraction is a fake")
    return project


def _video(project: Project, version: int = 1) -> Path:
    return project.root / "salida" / f"v{version}.mp4"


def _keys(project: Project) -> list[Path]:
    return sorted(p for p in project.layout.qa_ear.glob("*.json"))


def test_qa_ear_layout_the_folder_is_in_all_paths_so_a_link_there_is_refused_on_open() -> None:
    layout = Layout(Path("C:/p"))
    assert layout.qa_ear == Path("C:/p") / ".kcut" / "qa_ear"
    assert layout.qa_ear in layout.all_paths()


def test_qa_ear_hears_the_words_of_the_audio(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    engine = install_ear(monkeypatch, SPOKEN)
    heard = hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    assert isinstance(heard, Heard) and heard.language == "es"
    assert [(w.id, w.text, w.s_ms, w.e_ms) for w in heard.words] == [
        ("qa:w0000", "Hola", 200, 600),
        ("qa:w0001", "esto", 700, 1000),
        ("qa:w0002", "funciona", 1100, 1700),
    ]
    assert len(engine.calls) == 1 and engine.downloads == [False]  # no download, ever


def test_qa_ear_the_engine_is_asked_for_the_language_it_is_given_and_the_prompt_of_the_project(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    engine = install_ear(monkeypatch, SPOKEN, language="en")
    hear(project, _video(project), "en", log=None, limit_s=LIMIT_S)
    ((prompt, language),) = engine.args
    assert language == "en"
    assert "Eh" in prompt  # the fillers of the project: it writes them down instead of cleaning


def test_qa_ear_the_audio_goes_through_a_partial_file_to_a_16k_wav_named_after_the_version(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = fake_extraction(monkeypatch)
    install_ear(monkeypatch, SPOKEN)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    (args,) = seen
    assert Path(args[-1]).name == "v1.partial.wav" and "-y" in args
    assert args[args.index("-i") + 1] == str(_video(project))
    assert "aresample=16000:resampler=soxr:first_pts=0" in args[args.index("-af") + 1]
    assert (project.layout.qa_ear / "v1.wav").is_file()
    assert not list(project.layout.qa_ear.glob("*.partial*"))


def test_qa_ear_another_version_is_another_wav(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    install_ear(monkeypatch, SPOKEN)
    (project.root / "salida" / "v7.mp4").write_bytes(b"x")
    hear(project, _video(project, 7), "es", log=None, limit_s=LIMIT_S)
    assert (project.layout.qa_ear / "v7.wav").is_file()
    assert not (project.layout.qa_ear / "v1.wav").exists()


def test_qa_ear_the_second_run_does_not_transcribe_again(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    engine = install_ear(monkeypatch, SPOKEN)
    first = hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    second = hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    assert len(engine.calls) == 1 and engine.loaded == 1
    assert first is not None and second is not None and second.words == first.words
    assert len(_keys(project)) == 1


def test_qa_ear_a_second_run_with_a_cache_does_not_even_load_the_model(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    install_ear(monkeypatch, SPOKEN)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    monkeypatch.setattr(ear, "Engine", NoModel)  # if the cache is read, the model is not needed
    again = hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    assert again is not None and [w.text for w in again.words] == ["Hola", "esto", "funciona"]


def test_qa_ear_another_language_is_another_key_and_is_heard_again(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    engine = install_ear(monkeypatch, SPOKEN)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    hear(project, _video(project), "en", log=None, limit_s=LIMIT_S)
    assert len(engine.calls) == 2 and len(_keys(project)) == 2


def test_qa_ear_other_audio_is_another_key_and_is_heard_again(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch, seconds=2.0)
    engine = install_ear(monkeypatch, SPOKEN)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    fake_extraction(monkeypatch, seconds=3.0)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    assert len(engine.calls) == 2 and len(_keys(project)) == 2


def test_qa_ear_the_cache_file_has_the_format_of_a_transcript_and_the_clip_id_qa(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    install_ear(monkeypatch, SPOKEN)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    (path,) = _keys(project)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema"] == "kcut.transcript/1" and document["key"] == path.stem
    assert document["params"]["language"] == "es" and document["language"] == "es"
    assert [w["w"] for w in document["words"]] == ["Hola", "esto", "funciona"]


def test_qa_ear_nothing_is_written_in_transcripts(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    install_ear(monkeypatch, SPOKEN)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    assert not project.layout.transcripts.exists() or not list(project.layout.transcripts.iterdir())


@pytest.mark.parametrize(
    "damage",
    [
        lambda text: "{ not json",
        lambda text: "[]",
        lambda text: text.replace("kcut.transcript/1", "kcut.transcript/9"),
        lambda text: text.replace('"w": "Hola"', '"w": 7'),
        lambda text: text.replace('"e_ms": 1700', '"e_ms": 99999999'),  # past the end of the wav
        lambda text: text.replace('"language": "es"', '"language": "Spanish"', 1),
        lambda text: "",
    ],
    ids=["not_json", "not_object", "schema", "word_type", "past_the_wav", "language", "empty"],
)
def test_qa_ear_a_cache_file_that_does_not_validate_is_heard_again_with_a_notice(
    project: Project, monkeypatch: pytest.MonkeyPatch, damage: object
) -> None:
    fake_extraction(monkeypatch)
    engine = install_ear(monkeypatch, SPOKEN)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    (path,) = _keys(project)
    path.write_text(damage(path.read_text(encoding="utf-8")), encoding="utf-8")  # type: ignore[operator]
    notices: list[Notice] = []
    heard = hear(project, _video(project), "es", log=None, notices=notices, limit_s=LIMIT_S)
    assert heard is not None and [w.text for w in heard.words] == ["Hola", "esto", "funciona"]
    assert len(engine.calls) == 2  # it listened again
    assert [n.code for n in notices] == ["cache_rebuilt"]
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == "kcut.transcript/1"  # mended
    again: list[Notice] = []
    hear(project, _video(project), "es", log=None, notices=again, limit_s=LIMIT_S)
    assert again == [] and len(engine.calls) == 2  # and the mended file is read


def test_qa_ear_a_cache_made_for_other_parameters_is_not_used(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    engine = install_ear(monkeypatch, SPOKEN)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    (path,) = _keys(project)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["params"]["beam_size"] = 99
    path.write_text(json.dumps(document), encoding="utf-8")
    notices: list[Notice] = []
    hear(project, _video(project), "es", log=None, notices=notices, limit_s=LIMIT_S)
    assert len(engine.calls) == 2 and [n.code for n in notices] == ["cache_rebuilt"]


def test_qa_ear_the_cache_notice_does_not_quote_the_file(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    install_ear(monkeypatch, SPOKEN)
    hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    (path,) = _keys(project)
    path.write_text('{"words": ["Maria 809-555-1234"]}', encoding="utf-8")
    notices: list[Notice] = []
    hear(project, _video(project), "es", log=None, notices=notices, limit_s=LIMIT_S)
    assert "Maria" not in notices[0].detail and "809" not in notices[0].detail


def test_qa_ear_without_the_model_it_is_none_and_nothing_is_cached(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    monkeypatch.setattr(ear, "Engine", NoModel)
    assert hear(project, _video(project), "es", log=None, limit_s=LIMIT_S) is None
    assert _keys(project) == []
    assert not list(project.layout.qa_ear.glob("*.partial*"))


def test_qa_ear_a_render_nobody_says_anything_in_is_an_empty_list_of_words(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_extraction(monkeypatch)
    install_ear(monkeypatch, [])
    heard = hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    assert heard is not None and heard.words == []


def test_qa_ear_the_repr_does_not_show_the_words(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What was said can be a phone number: a `print` or a log must not leak it."""
    fake_extraction(monkeypatch)
    install_ear(monkeypatch, [("809-555-1234", 100, 900)])
    heard = hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    assert heard is not None and "809" not in repr(heard)


def test_qa_ear_a_link_in_the_folder_is_refused_when_the_project_is_opened(
    project: Project, tmp_path: Path
) -> None:
    """It is in `all_paths()`, so `check_layout_inside` looks at it as at every folder of the
    layout."""
    outside = tmp_path / "ajeno"
    outside.mkdir()
    project.layout.cache.mkdir(parents=True, exist_ok=True)
    make_dir_link(project.layout.qa_ear, outside)
    try:
        with pytest.raises(ProjectError, match="enlace"):
            check_layout_inside(project.root, project.layout)
    finally:
        remove_dir_link(project.layout.qa_ear)


def test_qa_ear_the_folder_as_a_link_is_refused_and_nothing_goes_through_it(
    project: Project, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_extraction(monkeypatch)
    install_ear(monkeypatch, SPOKEN)
    outside = tmp_path / "ajeno"
    outside.mkdir()
    project.layout.cache.mkdir(parents=True, exist_ok=True)
    make_dir_link(project.layout.qa_ear, outside)
    try:
        with pytest.raises(ProjectError):
            hear(project, _video(project), "es", log=None, limit_s=LIMIT_S)
    finally:
        remove_dir_link(project.layout.qa_ear)
    assert list(outside.iterdir()) == []


def test_qa_ear_masking_off_changes_nothing_for_the_ear_the_words_are_raw_either_way(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ear returns raw words (they go to the diff, which masks what it shows)."""
    fake_extraction(monkeypatch)
    install_ear(monkeypatch, [("3211", 100, 900)])
    raw = hear(with_privacy(project, False), _video(project), "es", log=None, limit_s=LIMIT_S)
    assert raw is not None and raw.words[0].text == "3211"
