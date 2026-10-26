"""Hand-made wav files for the header tests: honest ones and the ways a header can lie (001.16)."""

import random
import struct
from pathlib import Path
from typing import Any

from kcut.audio.wavio import read_wav_s16_mono
from kcut.errors import ProjectError

SR = 16000
PCM = b"\x01\x02" * 16000  # one second of 16-bit mono at 16 kHz
JUNK = b"JUNK"


def chunk(name: bytes, payload: bytes, size: int | None = None, pad: bool = True) -> bytes:
    """A RIFF chunk: its name, the size it SAYS (default the real one) and its payload."""
    out = name + struct.pack("<I", len(payload) if size is None else size) + payload
    return out + b"\x00" if pad and len(payload) & 1 else out


def fmt(tag: int = 1, ch: int = 1, rate: int = SR, ba: int = 2, bits: int = 16) -> bytes:
    return struct.pack("<HHIIHH", tag, ch, rate, rate * 2, ba, bits)


FMT = fmt()


def wav(chunks: list[bytes], riff_size: int | None = None) -> bytes:
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body) if riff_size is None else riff_size) + body


def _liar(name: bytes, size: int) -> bytes:
    return name + struct.pack("<I", size)


# What the header says is not what the file holds: every reader has to say ProjectError.
LYING: dict[str, bytes] = {
    "block_align_1_odd_data": wav([chunk(b"fmt ", fmt(ba=1)), chunk(b"data", PCM + b"\x00")]),
    "riff_one_byte_short": wav(
        [chunk(b"fmt ", FMT), chunk(b"data", PCM)], riff_size=4 + 8 + 16 + 8 + len(PCM) - 1
    ),
    "riff_size_small": wav([chunk(b"fmt ", FMT), chunk(b"data", PCM)], riff_size=20),
    "list_4gb_before_data": wav(
        [chunk(b"fmt ", FMT), _liar(b"LIST", 0xFFFFFFFF), chunk(b"data", PCM)]
    ),
    "list_4gb_minus_1": wav([chunk(b"fmt ", FMT), _liar(b"LIST", 0xFFFFFFFE), chunk(b"data", PCM)]),
    "list_wraps_the_seek": wav([chunk(b"fmt ", FMT), _liar(b"LIST", 0xFFFFFFF8) + b"x" * 64]),
    "junk_4gb_before_fmt": wav([_liar(JUNK, 0xFFFFFFFF), chunk(b"fmt ", FMT), chunk(b"data", PCM)]),
    "data_4gb": wav([chunk(b"fmt ", FMT), _liar(b"data", 0xFFFFFFFF) + PCM]),
    "data_4gb_minus_1": wav([chunk(b"fmt ", FMT), _liar(b"data", 0xFFFFFFFE) + PCM]),
    "data_2gb": wav([chunk(b"fmt ", FMT), _liar(b"data", 0x7FFFFFFE) + PCM]),
    "data_odd": wav([chunk(b"fmt ", FMT), _liar(b"data", len(PCM) - 1) + PCM]),
    "fmt_says_24_bits": wav([chunk(b"fmt ", fmt(bits=24)), chunk(b"data", PCM)]),
    "fmt_says_12_bits_odd_data": wav([chunk(b"fmt ", fmt(bits=12)), chunk(b"data", PCM + b"\x00")]),
    "fmt_says_zero_channels": wav([chunk(b"fmt ", fmt(ch=0)), chunk(b"data", PCM)]),
    "fmt_says_zero_bits": wav([chunk(b"fmt ", fmt(bits=0)), chunk(b"data", PCM)]),
    "fmt_after_data": wav([chunk(b"data", PCM), chunk(b"fmt ", FMT)]),
    "fmt_too_short": wav([chunk(b"fmt ", FMT[:10]), chunk(b"data", PCM)]),
    "fmt_empty": wav([chunk(b"fmt ", b""), chunk(b"data", PCM)]),
    "fmt_float": wav([chunk(b"fmt ", fmt(tag=3, ba=4, bits=32)), chunk(b"data", PCM)]),
    "fmt_extensible": wav([chunk(b"fmt ", fmt(tag=0xFFFE) + b"\x16\x00" + b"\x00" * 22)]),
    "no_fmt_and_no_data": wav([chunk(JUNK, b"zz")]),
    "300_chunks_before_data": wav(
        [chunk(b"fmt ", FMT)] + [chunk(JUNK, b"zz") for _ in range(300)] + [chunk(b"data", PCM)]
    ),
    "not_riff": b"RIFX" + b"\x00" * 100,
    "rf64": b"RF64" + b"\xff" * 4 + b"WAVE" + chunk(b"fmt ", FMT) + chunk(b"data", PCM),
    "cut_in_the_header": b"RIFF\x00\x00\x00\x00WAVEfmt ",
    "empty_file": b"",
}  # fmt: skip

# The ones `check_wav_extent` lets through because `wave` refuses them anyway.
LEFT_TO_WAVE = {
    "cut_in_the_header", "empty_file", "fmt_extensible", "fmt_float", "no_fmt_and_no_data",
    "not_riff", "rf64",
}  # fmt: skip

# Nothing wrong with these: every reader reads them.
HONEST: dict[str, bytes] = {
    "plain": wav([chunk(b"fmt ", FMT), chunk(b"data", PCM)]),
    "list_before_data": wav(
        [chunk(b"fmt ", FMT), chunk(b"LIST", b"INFOISFT" + struct.pack("<I", 5) + b"Lavf\x00"),
         chunk(b"data", PCM)]
    ),
    "odd_chunk_with_its_pad_byte": wav(
        [chunk(b"fmt ", FMT), chunk(b"LIST", b"abc"), chunk(b"data", PCM)]
    ),
    "riff_size_unknown": wav([chunk(b"fmt ", FMT), chunk(b"data", PCM)], riff_size=0xFFFFFFFF),
    "data_shorter_than_the_file": wav([chunk(b"fmt ", FMT), _liar(b"data", len(PCM) - 2) + PCM]),
    "a_liar_after_the_data": wav(
        [chunk(b"fmt ", FMT), chunk(b"data", PCM), _liar(JUNK, 0xFFFFFFFF)]
    ),
    "254_chunks_before_data": wav(
        [chunk(b"fmt ", FMT)] + [chunk(JUNK, b"zz") for _ in range(254)] + [chunk(b"data", PCM)]
    ),
}  # fmt: skip


def mutants(count: int = 80, seed: int = 7) -> list[bytes]:
    """The honest file with 1 to 4 header bytes changed at random: whatever `wave` makes of them,
    a reader may only return or say ProjectError."""
    rng = random.Random(seed)
    out: list[bytes] = []
    for _ in range(count):
        data = bytearray(HONEST["plain"])
        for _ in range(rng.randint(1, 4)):
            data[rng.randrange(0, 60)] = rng.choice([0, 1, 0x7F, 0x80, 0xFF, rng.randrange(256)])
        out.append(bytes(data))
    return out


def read_all(path: Path) -> object:
    return read_wav_s16_mono(path)


def outcome(reader: Any, path: Path) -> str:
    try:
        reader(path)
    except ProjectError:
        return "ProjectError"
    except Exception as exc:  # the point of the test: nothing else may come out
        return type(exc).__name__
    return "ok"
