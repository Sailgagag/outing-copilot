"""Tiny JSON-file store so the assistant remembers places and preferences across sessions."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(os.environ.get("OUTING_STATE_FILE", Path.home() / ".outing-copilot" / "state.json"))


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_PATH
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"places": {}, "prefs": {"sensitive_to_air": False, "default_activity": "walk"}}
        return json.loads(self.path.read_text())

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)

    def save_place(self, nickname: str, place: dict[str, Any]) -> None:
        with self._lock:
            d = self._load()
            d["places"][nickname.strip().lower()] = place
            self._save(d)

    def get_place(self, nickname: str) -> dict[str, Any] | None:
        return self._load()["places"].get(nickname.strip().lower())

    def places(self) -> dict[str, Any]:
        return self._load()["places"]

    def prefs(self) -> dict[str, Any]:
        return self._load()["prefs"]

    def set_prefs(self, **kw: Any) -> dict[str, Any]:
        with self._lock:
            d = self._load()
            d["prefs"].update({k: v for k, v in kw.items() if v is not None})
            self._save(d)
            return d["prefs"]
