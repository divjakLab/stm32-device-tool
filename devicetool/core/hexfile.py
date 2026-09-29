"""Loading and checking Intel HEX files before anything touches the board."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from intelhex import IntelHex


class HexFileError(Exception):
    pass


@dataclass(frozen=True)
class HexInfo:
    path: Path
    size: int
    start: int
    end: int                       # exclusive
    segments: list[tuple[int, int]]


def load_hex(path) -> tuple[IntelHex, HexInfo]:
    p = Path(path)
    if not p.is_file():
        raise HexFileError(f"File not found:\n{p}")
    try:
        ih = IntelHex(str(p))
    except Exception as exc:
        raise HexFileError(f"This is not a valid .hex file:\n{exc}") from exc
    if len(ih) == 0:
        raise HexFileError("The .hex file contains no data.")
    segs = list(ih.segments())
    return ih, HexInfo(p, len(ih), segs[0][0], segs[-1][1], segs)
