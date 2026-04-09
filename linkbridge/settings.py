"""Persistent settings store backed by a JSON file under ~/Library/Application Support/LinkBridge/."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_SETTINGS_PATH = (
    Path.home() / "Library" / "Application Support" / "LinkBridge" / "settings.json"
)


@dataclass
class Settings:
    last_device: str | None = None
    start_stop_enabled: bool = False

    @classmethod
    def load(cls, path: Path = DEFAULT_SETTINGS_PATH) -> "Settings":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                last_device=data.get("last_device"),
                start_stop_enabled=bool(data.get("start_stop_enabled", False)),
            )
        except (json.JSONDecodeError, OSError) as e:
            corrupt_path = path.with_suffix(path.suffix + f".corrupt-{int(time.time())}")
            try:
                path.rename(corrupt_path)
                log.warning("settings file corrupt, renamed to %s: %s", corrupt_path, e)
            except OSError as rename_err:
                log.error("settings file corrupt and rename failed: %s", rename_err)
            return cls()

    def save(self, path: Path = DEFAULT_SETTINGS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_device": self.last_device,
            "start_stop_enabled": self.start_stop_enabled,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
