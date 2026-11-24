"""One item of the catalog and its parameters (spec S1.9a, format `kcut.catalog/1`).

Every text is Spanish and one line. `cost` is how much the item weighs when the video is made
(`bajo`, `medio` or `alto`). `edl_field` is not in the JSON: it is the field of `edl/model.py` that
makes a camera or a transition, so a test can check that what the catalog offers exists; the
transition `cut` has none (cutting is putting nothing).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from kcut.params import ParamSpec

Category = Literal["graphic", "look", "sfx", "music", "camera", "transition", "workflow"]
Status = Literal["available", "planned"]
Cost = Literal["bajo", "medio", "alto"]
CATEGORIES: tuple[Category, ...] = (
    "graphic",
    "look",
    "sfx",
    "music",
    "camera",
    "transition",
    "workflow",
)
SCHEMA = "kcut.catalog/1"


@dataclass(frozen=True)
class CatalogParam:
    """A parameter as `ParamSpec` has it: the kind, whether it is required, its default and the
    limits of a number (or of the length of a list)."""

    name: str
    kind: str
    required: bool
    default: object
    lo: float | None
    hi: float | None
    help_es: str

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "default": _plain(self.default),
            "lo": self.lo,
            "hi": self.hi,
            "help_es": self.help_es,
        }


@dataclass(frozen=True)
class CatalogItem:
    category: Category
    id: str
    name_es: str
    purpose_es: str
    avoid_es: str
    status: Status
    since: str
    cost: Cost
    cost_note_es: str = ""
    params: tuple[CatalogParam, ...] = ()
    edl_field: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "category": self.category,
            "id": self.id,
            "name_es": self.name_es,
            "purpose_es": self.purpose_es,
            "avoid_es": self.avoid_es,
            "status": self.status,
            "since": self.since,
            "cost": self.cost,
            "cost_note_es": self.cost_note_es,
            "params": [param.to_json() for param in self.params],
        }


def params_of(specs: Sequence[ParamSpec]) -> tuple[CatalogParam, ...]:
    """The parameters of a component or an effect, as the catalog lists them. The specs of the
    elements of a list or an object (`item`) are not listed: the parameter says what it holds."""
    return tuple(
        CatalogParam(s.name, s.kind, s.required, s.default, s.lo, s.hi, s.help_es) for s in specs
    )


def _plain(value: object) -> object:
    """A default as JSON can hold it: tuples are lists."""
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value
