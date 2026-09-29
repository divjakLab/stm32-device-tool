"""Turns raw serial bytes into timestamped, classified log lines."""

from __future__ import annotations

import enum
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .. import config


class Level(enum.Enum):
    NORMAL = "normal"
    WARN = "warn"
    ERROR = "error"
    MARKER = "marker"


_ERROR_RE = re.compile(r"error|fail|fault|assert", re.IGNORECASE)
_WARN_RE = re.compile(r"warn", re.IGNORECASE)
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_EOL_RE = re.compile(rb"\r\n|\r|\n")


def classify(text: str) -> Level:
    if _ERROR_RE.search(text):
        return Level.ERROR
    if _WARN_RE.search(text):
        return Level.WARN
    return Level.NORMAL


def format_ts(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


@dataclass(frozen=True)
class LogLine:
    ts: float
    text: str
    level: Level

    def formatted(self) -> str:
        return f"{format_ts(self.ts)}  {self.text}"


def make_marker(text: str, ts: float) -> LogLine:
    return LogLine(ts, f"── {text} ──", Level.MARKER)


def _clean(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = _ANSI_RE.sub("", text)
    return _CONTROL_RE.sub("", text)


class LineAssembler:
    """Splits a byte stream into lines. Handles CR, LF and CRLF (also when
    CRLF is split across two reads), flushes a partial line after a quiet
    period, and force-splits absurdly long lines (binary garbage)."""

    def __init__(self, idle_flush_s: float = config.LINE_IDLE_FLUSH_S,
                 max_line_bytes: int = config.MAX_LINE_BYTES) -> None:
        self._idle = idle_flush_s
        self._max = max_line_bytes
        self._buf = b""
        self._started = 0.0
        self._last_rx: Optional[float] = None
        self._skip_lf = False

    def _line(self, raw: bytes, ts: float) -> LogLine:
        text = _clean(raw)
        return LogLine(ts, text, classify(text))

    def feed(self, data: bytes, now: float) -> list[LogLine]:
        if self._skip_lf and data[:1] == b"\n":
            data = data[1:]
        if not data:
            return []
        self._skip_lf = data.endswith(b"\r")
        if not self._buf:
            self._started = now
        self._last_rx = now
        parts = _EOL_RE.split(self._buf + data)
        rest = parts.pop()
        out: list[LogLine] = []
        for i, raw in enumerate(parts):
            out.append(self._line(raw, self._started if i == 0 else now))
        if parts:
            self._started = now
        while len(rest) > self._max:
            out.append(self._line(rest[:self._max], self._started))
            rest = rest[self._max:]
            self._started = now
        self._buf = rest
        return out

    def flush_if_idle(self, now: float) -> list[LogLine]:
        if self._buf and self._last_rx is not None and now - self._last_rx >= self._idle:
            line = self._line(self._buf, self._started)
            self._buf = b""
            return [line]
        return []


def matches(line: LogLine, query: str) -> bool:
    q = query.strip().casefold()
    return not q or q in line.text.casefold()


class LogStore:
    def __init__(self, max_lines: int = config.MAX_LOG_LINES) -> None:
        self.lines: deque[LogLine] = deque(maxlen=max_lines)

    def extend(self, lines: Iterable[LogLine]) -> None:
        self.lines.extend(lines)

    def clear(self) -> None:
        self.lines.clear()

    def filtered(self, query: str) -> list[LogLine]:
        return [l for l in self.lines if matches(l, query)]

    def save(self, path: Path) -> None:
        Path(path).write_text("".join(l.formatted() + "\n" for l in self.lines), encoding="utf-8")


def prune_logs(directory: Path, keep: int) -> None:
    files = sorted(Path(directory).glob("*.txt"))
    for f in files[:-keep] if keep > 0 else files:
        f.unlink(missing_ok=True)


class SessionLog:
    """One text file per serial connection, flushed after every write."""

    def __init__(self, directory: Path, keep: int = config.MAX_SESSION_LOGS) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".txt"
        self.path = directory / name
        self._f = open(self.path, "a", encoding="utf-8")
        prune_logs(directory, keep)

    def write(self, lines: Iterable[LogLine]) -> None:
        for l in lines:
            self._f.write(l.formatted() + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()
