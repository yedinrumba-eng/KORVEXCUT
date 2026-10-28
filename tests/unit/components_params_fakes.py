"""What the cases of `test_components_params.py` share (spec S1.7 row 1): the brand, the path of the
cue and the two calls they all make. Not a test module."""

from kcut.config.load import parse_config
from kcut.gfx.components import COMPONENTS, validate_params
from kcut.issues import Issue

BRAND = parse_config("", default_name="x").brand
PATH = "cues[0].params"


def check(component: str, params: object) -> tuple[dict[str, object], list[Issue]]:
    """`validate_params` of `component`: the params with their defaults, and the G03 issues."""
    return validate_params(COMPONENTS[component], params, PATH, BRAND)


def paths(issues: list[Issue]) -> list[str]:
    """The path of each issue, after seeing that all of them are G03 errors."""
    assert all(issue.code == "G03" and issue.level == "error" for issue in issues), issues
    return [issue.path for issue in issues]


def messages(issues: list[Issue]) -> list[str]:
    return [issue.message_es for issue in issues]
