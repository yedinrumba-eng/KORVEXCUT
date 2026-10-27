"""The whole check of an EDL against the project (spec S1.5a): references first, then numbers."""

from collections.abc import Mapping

from kcut.config.model import ProjectConfig
from kcut.edl.model import Edl
from kcut.edl.ranges import check_ranges
from kcut.edl.refs import check_refs, source_status
from kcut.edl.timeline import VoiceIndex
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
    reserved and nobody emits them. `audio_f[src]` is the voice frames the audio of `src` has.

    The status of the sources and the index of the voice clips are made once here and given to
    both: the check is linear in the size of the EDL (001.24, point 4)."""
    status = source_status(edl, inv)
    index = VoiceIndex(edl)
    return [
        *check_refs(edl, inv, cfg, version_from_name, status=status, index=index),
        *check_ranges(edl, inv, cfg, audio_f, status=status, index=index),
    ]
