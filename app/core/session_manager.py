"""Zapamiętywanie postępu pracy.

* SessionManager — stan konkretnej biblioteki (w jej bazie SQLite): bieżący
  folder, bieżący plik, pozycja, sortowanie, filtry, stan paska miniatur,
  przewinięcie, ostatnio użyty folder docelowy.
* AppSettings — ustawienia programu (%APPDATA%/PhotoSort/settings.json):
  ostatnie biblioteki, motyw, rozmiar okna.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.constants import UNSORTED_FOLDER
from app.database.database import Database
from app.utils.paths import app_data_dir


@dataclass
class SessionState:
    scope: str = UNSORTED_FOLDER
    current_id: int | None = None
    current_index: int = 0
    sort: str = "date"
    ascending: bool = True
    filters: dict = field(default_factory=dict)
    last_target: str = ""
    strip_expanded: bool = False
    scroll: int = 0
    # pozycja w każdym folderze osobno: {folder: media_id}
    positions: dict = field(default_factory=dict)


class SessionManager:
    KEY = "session"

    def __init__(self, db: Database):
        self.db = db

    def load(self) -> SessionState:
        raw = self.db.get_state(self.KEY)
        state = SessionState()
        if raw:
            try:
                data = json.loads(raw)
                for k, v in data.items():
                    if hasattr(state, k):
                        setattr(state, k, v)
            except ValueError:
                pass
        return state

    def save(self, state: SessionState) -> None:
        self.db.set_state(self.KEY, json.dumps(asdict(state), ensure_ascii=False))
        self.db.set_state("saved_at", str(time.time()))


class AppSettings:
    def __init__(self, path: Path | None = None):
        self.path = path or (app_data_dir() / "settings.json")
        self.data: dict = {"recent": [], "theme": "light", "window": None}
        try:
            self.data.update(json.loads(self.path.read_text("utf-8")))
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ostatnie biblioteki
    def recent(self) -> list[str]:
        return [p for p in self.data.get("recent", []) if isinstance(p, str)]

    def add_recent(self, path: Path) -> None:
        p = str(Path(path))
        items = [x for x in self.recent() if os.path.normcase(x) != os.path.normcase(p)]
        items.insert(0, p)
        self.data["recent"] = items[:10]
        self.save()

    def remove_recent(self, path: str) -> None:
        self.data["recent"] = [x for x in self.recent() if os.path.normcase(x) != os.path.normcase(path)]
        self.save()

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value
        self.save()
