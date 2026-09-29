"""Saved commands with {placeholders}, and the send history."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .. import config
from .storage import load_json, save_json

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def placeholders(text: str) -> list[str]:
    seen: list[str] = []
    for m in _PLACEHOLDER_RE.finditer(text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def fill(text: str, values: dict[str, str]) -> str:
    for name in placeholders(text):
        if name not in values:
            raise KeyError(name)
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], text)


@dataclass(frozen=True)
class Command:
    name: str
    text: str
    group: str = "General"

    def to_dict(self) -> dict:
        return {"name": self.name, "text": self.text, "group": self.group}

    @classmethod
    def from_dict(cls, d: object) -> "Command":
        if not isinstance(d, dict):
            raise ValueError("A command must be an object.")
        name, text, group = d.get("name"), d.get("text"), d.get("group", "General")
        if not isinstance(text, str) or not text:
            raise ValueError("Every command needs a non-empty 'text'.")
        if name is None:
            name = text
        if not isinstance(name, str) or not isinstance(group, str):
            raise ValueError("'name' and 'group' must be text.")
        return cls(name or text, text, group or "General")


EXAMPLES = (
    Command("help", "help", "Examples"),
    Command("version", "version", "Examples"),
    Command("reboot", "reboot", "Examples"),
    Command("Set a value", "set {key} {value}", "Examples"),
    Command("Get a value", "get {key}", "Examples"),
)


class CommandLibrary:
    def __init__(self, commands: Optional[Iterable[Command]] = None) -> None:
        self.commands: list[Command] = list(EXAMPLES if commands is None else commands)

    def groups(self) -> list[str]:
        out: list[str] = []
        for c in self.commands:
            if c.group not in out:
                out.append(c.group)
        return out

    def to_json(self) -> dict:
        return {"version": 1, "commands": [c.to_dict() for c in self.commands]}

    @staticmethod
    def parse(data: object) -> list[Command]:
        if not isinstance(data, dict) or not isinstance(data.get("commands"), list):
            raise ValueError("This is not a command library file.")
        return [Command.from_dict(d) for d in data["commands"]]

    @classmethod
    def load(cls, path: Path) -> "CommandLibrary":
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            return cls(cls.parse(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            # Keep the broken file for inspection; start with the examples.
            try:
                os.replace(path, path.with_name(path.name + ".bad"))
            except OSError:
                pass
            return cls()

    def save(self, path: Path) -> None:
        save_json(path, self.to_json())

    def import_file(self, path: Path) -> int:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Could not read the file: {exc}") from exc
        new = self.parse(data)
        added = 0
        for c in new:
            if c not in self.commands:
                self.commands.append(c)
                added += 1
        return added

    def export_file(self, path: Path) -> None:
        save_json(path, self.to_json())


class History:
    """Terminal-style history: previous() walks back, next() walks forward."""

    def __init__(self, items: Optional[Iterable[str]] = None,
                 max_items: int = config.MAX_HISTORY) -> None:
        self._max = max_items
        self.items: list[str] = [i for i in (items or []) if isinstance(i, str)][-max_items:]
        self._pos = len(self.items)

    def add(self, text: str) -> None:
        if text and (not self.items or self.items[-1] != text):
            self.items.append(text)
            del self.items[:-self._max]
        self._pos = len(self.items)

    def previous(self) -> Optional[str]:
        if not self.items:
            return None
        self._pos = max(0, self._pos - 1)
        return self.items[self._pos]

    def next(self) -> str:
        if self._pos < len(self.items) - 1:
            self._pos += 1
            return self.items[self._pos]
        self._pos = len(self.items)
        return ""

    @classmethod
    def load(cls, path: Path, max_items: int = config.MAX_HISTORY) -> "History":
        data = load_json(path, [])
        return cls(data if isinstance(data, list) else [], max_items)

    def save(self, path: Path) -> None:
        try:
            save_json(path, self.items)
        except OSError:
            pass
