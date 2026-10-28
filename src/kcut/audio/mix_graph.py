"""The graph of filters of the mix (spec S1.8b, 001.15; lesson 11): the voice, the music under it
and the sound effects, summed.

Pure. The inputs of `ffmpeg` are the voice (`[0:a]`), the music (`[1:a]`, only if there is any) and
the effects (the last one), all raw float32 files that come in with `-i`: no path is ever written in
the graph (spec 0.8), and every number is `fnum`. The sum is `amix` with `normalize=0` (the level is
set by the gains and by `loudnorm` at the end) and `duration=first`, which is the voice: the length
of the video.

Lesson 11: a label that a filter makes and nobody uses stops the graph (`ffmpeg` waits for a
consumer that is not there). Every output of `asplit` is used here; if one were left over it would
go to `anullsink`, and a test checks that no label hangs.

001.37: `sidechaincompress` ends when one of its two inputs reaches its end and throws away what
the other one still had in its queue, so which input got there first (a race between threads of
`ffmpeg`) decided how much of the tail of the music was lost. Both inputs of the compressor go
through `apad` (endless silence after their end): nobody ends before the other, and `amix`, which
closes with the voice, is the one that sets the length. No `-t` and no padding of the files.
"""

from kcut.audio.music_model import DuckCfg
from kcut.ff.args import fnum

_AMIX = "normalize=0:duration=first:dropout_transition=0"


def _sidechain(duck: DuckCfg) -> str:
    return (
        f"sidechaincompress=threshold={fnum(duck.threshold)}:ratio={fnum(duck.ratio)}"
        f":attack={fnum(duck.attack_ms)}:release={fnum(duck.release_ms)}"
        f":makeup={fnum(duck.makeup)}:knee={fnum(duck.knee)}"
    )


def build_graph(has_music: bool, duck: bool, duck_cfg: DuckCfg) -> tuple[str, int]:
    """`(filter_complex, number of inputs)` of the mix, with the output labeled `[mix]`.

    - voice, music and ducking: the voice is split in two, one goes to the mix and the other is the
      sidechain of the compressor that lowers the music (`[md]`), and both inputs of the compressor
      go through `apad` (001.37); inputs `0` voice, `1` music, `2` effects;
    - voice and music with no ducking: the three are summed; the same inputs;
    - no music: the voice and the effects (`[0:a]`, `[1:a]`), two inputs."""
    if not has_music:
        return f"[0:a][1:a]amix=inputs=2:{_AMIX}[mix]", 2
    if not duck:
        return f"[0:a][1:a][2:a]amix=inputs=3:{_AMIX}[mix]", 3
    graph = (
        "[0:a]asplit=2[vm][vs];"
        "[vs]apad[vsp];"
        "[1:a]apad[mp];"
        f"[mp][vsp]{_sidechain(duck_cfg)}[md];"
        f"[vm][md][2:a]amix=inputs=3:{_AMIX}[mix]"
    )
    return graph, 3


def duck_only_graph(duck_cfg: DuckCfg) -> str:
    """Only the ducking, for its test: input `0` is the music (what is lowered) and input `1` is the
    voice (the sidechain); the output is `[md]`."""
    return f"[0:a][1:a]{_sidechain(duck_cfg)}[md]"
