"""The whole check of an EDL against the project (spec S1.5a): references first, then numbers."""

from collections.abc import Mapping

from kcut.config.model import ProjectConfig
from kcut.edl.model import Edl
from kcut.edl.ranges import check_ranges
from kcut.edl.refs import check_refs
from kcut.ingest.inventory import Inventory
from kcut.issues import Issue


def validate(
    edl: Edl,
    inv: Inventory,
    cfg: ProjectConfig,
    version_from_name: int,
    audio_f: Mapping[str, int],
) -> list[Issue]:
    """`check_refs` then `check_ranges`, in that order. E01 is `parse_edl`'s; E10 and E16 are
    reserved and nobody emits them. `audio_f[src]` is the voice frames the audio of `src` has."""
    return [
        *check_refs(edl, inv, cfg, version_from_name),
        *check_ranges(edl, inv, cfg, audio_f),
    ]
