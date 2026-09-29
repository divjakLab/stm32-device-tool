"""Small JSON helpers and the settings store."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data: Any) -> None:
    """Write atomically, so a crash mid-write never leaves a broken file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class Settings:
    """A dict persisted to JSON on every change. Save errors are ignored."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        data = load_json(self.path, {})
        self.data: dict = data if isinstance(data, dict) else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        try:
            save_json(self.path, self.data)
        except OSError:
            pass
