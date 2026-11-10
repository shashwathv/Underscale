"""Per-display settings, kept in ~/.config/underscale/displays.json.

Settings are keyed by the physical display (EDID vendor, product, serial),
not by the port, so a TV keeps its underscan whichever socket it is on.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .backends.base import Display


def _config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "underscale" / "displays.json"


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _config_path()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".displays-")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, self.path)

    def get_underscan(self, display: Display) -> float:
        entry = self._load().get(display.key, {})
        try:
            return max(0.0, float(entry.get("underscan", 0.0)))
        except (TypeError, ValueError):
            return 0.0

    def set_underscan(self, display: Display, amount: float) -> None:
        data = self._load()
        entry = data.setdefault(display.key, {})
        entry["name"] = display.name
        entry["underscan"] = round(float(amount), 4)
        self._save(data)
