"""kcut catalog: what the engine can do (spec S1.9a, D8). It needs no project.

`--json` prints `{"schema": "kcut.catalog/1", "engine_version", "items": [...]}`; the human output
is a table by category, one line for each item: `[disponible] graphic/title - Título grande -
costo bajo - <para qué>`. `--category C` lists only that category.
"""

from __future__ import annotations

import argparse

from kcut import __version__
from kcut.catalog.collect import collect
from kcut.catalog.model import CATEGORIES, SCHEMA, CatalogItem
from kcut.console import Out, safe_text
from kcut.errors import UsageError

NAME = "catalog"
HELP_ES = "Lista lo que el motor sabe hacer: gráficos, looks, sonidos, cámara, transiciones"
_STATUS_ES = {"available": "disponible", "planned": "planeado"}


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)
    sub.add_argument(
        "--category",
        metavar="C",
        default=None,
        help=f"solo esta categoría: {', '.join(CATEGORIES)}",
    )
    return sub


def run(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    chosen = args.category
    if chosen is not None and chosen not in CATEGORIES:
        raise UsageError(f"la categoría tiene que ser una de: {', '.join(CATEGORIES)}")
    items = [item for item in collect() if chosen is None or item.category == chosen]
    if not out.json_mode:
        _table(items)
    out.result(
        {
            "schema": SCHEMA,
            "engine_version": __version__,
            "items": [item.to_json() for item in items],
        }
    )
    return 0


def _table(items: list[CatalogItem]) -> None:
    """One line per item, grouped by category, with a header line for each category."""
    current = None
    for item in items:
        if item.category != current:
            current = item.category
            print(safe_text(f"== {current} =="))
        status = _STATUS_ES[item.status]
        line = (
            f"[{status}] {item.category}/{item.id} - {item.name_es} - costo {item.cost} - "
            f"{item.purpose_es}"
        )
        print(safe_text(line))
