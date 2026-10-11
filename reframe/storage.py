"""SQLite storage for ideas and their real-world outcomes."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Idea

DEFAULT_HOME = Path(os.environ.get("REFRAME_HOME", Path.home() / ".reframe"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS market_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id INTEGER NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
    scanned_at TEXT NOT NULL,
    data TEXT NOT NULL,
    applied INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id INTEGER NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
    at TEXT NOT NULL,
    score REAL NOT NULL,
    total_profit REAL NOT NULL,
    pulse REAL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS outcomes (
    idea_id INTEGER PRIMARY KEY REFERENCES ideas(id) ON DELETE CASCADE,
    success INTEGER NOT NULL,
    actual_profit REAL,
    notes TEXT,
    recorded_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, home: Path | None = None):
        self.home = Path(home or DEFAULT_HOME)
        self.home.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the web server runs requests one at a time on its own thread
        self.db = sqlite3.connect(self.home / "reframe.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    @property
    def model_path(self) -> Path:
        return self.home / "model.json"

    # -- settings ---------------------------------------------------------------
    @property
    def config_path(self) -> Path:
        return self.home / "config.json"

    def load_config(self) -> dict:
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_config(self, **changes) -> dict:
        config = self.load_config() | changes
        self.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return config

    @property
    def api_key_path(self) -> Path:
        return self.home / "anthropic_api_key"

    def load_api_key(self) -> str | None:
        """The Anthropic API key saved with ``reframe set-key``, if any."""
        try:
            return self.api_key_path.read_text(encoding="utf-8").strip() or None
        except FileNotFoundError:
            return None

    def save_api_key(self, key: str | None) -> None:
        """Save the key on this computer only (readable by your user only); None removes it."""
        if not key:
            self.api_key_path.unlink(missing_ok=True)
            return
        self.api_key_path.write_text(key.strip(), encoding="utf-8")
        try:
            os.chmod(self.api_key_path, 0o600)
        except OSError:  # pragma: no cover - e.g. some Windows file systems
            pass

    def add_idea(self, idea: Idea) -> Idea:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data = idea.to_dict()
        data.pop("id", None)
        data.pop("created_at", None)
        cur = self.db.execute("INSERT INTO ideas (data, created_at) VALUES (?, ?)",
                              (json.dumps(data), now))
        self.db.commit()
        idea.id, idea.created_at = cur.lastrowid, now
        return idea

    def update_idea(self, idea: Idea) -> None:
        data = idea.to_dict()
        data.pop("id", None)
        data.pop("created_at", None)
        self.db.execute("UPDATE ideas SET data = ? WHERE id = ?", (json.dumps(data), idea.id))
        self.db.commit()

    def _row_to_idea(self, row: sqlite3.Row) -> Idea:
        data = json.loads(row["data"])
        data["id"], data["created_at"] = row["id"], row["created_at"]
        return Idea.from_dict(data)

    def get_idea(self, idea_id: int) -> Idea:
        row = self.db.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        if row is None:
            raise KeyError(f"No idea with id {idea_id}")
        return self._row_to_idea(row)

    def list_ideas(self) -> list[Idea]:
        rows = self.db.execute("SELECT * FROM ideas ORDER BY id").fetchall()
        return [self._row_to_idea(r) for r in rows]

    def delete_idea(self, idea_id: int) -> None:
        self.db.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
        self.db.commit()

    def record_outcome(self, idea_id: int, success: bool, actual_profit: float | None = None,
                       notes: str = "") -> None:
        self.get_idea(idea_id)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.db.execute(
            "INSERT OR REPLACE INTO outcomes (idea_id, success, actual_profit, notes, recorded_at) "
            "VALUES (?, ?, ?, ?, ?)", (idea_id, int(success), actual_profit, notes, now))
        self.db.commit()

    def outcomes(self) -> list[tuple[Idea, dict]]:
        rows = self.db.execute(
            "SELECT i.id, i.data, i.created_at, o.success, o.actual_profit, o.notes "
            "FROM outcomes o JOIN ideas i ON i.id = o.idea_id ORDER BY i.id").fetchall()
        return [(self._row_to_idea(r), {"success": bool(r["success"]),
                                        "actual_profit": r["actual_profit"], "notes": r["notes"]})
                for r in rows]

    # -- live market data -------------------------------------------------------
    def add_scan(self, idea_id: int, data: dict, applied: bool) -> None:
        self.db.execute("INSERT INTO market_scans (idea_id, scanned_at, data, applied) VALUES (?, ?, ?, ?)",
                        (idea_id, data["fetched_at"], json.dumps(data), int(applied)))
        self.db.commit()

    def latest_scan(self, idea_id: int) -> dict | None:
        r = self.db.execute("SELECT data, applied FROM market_scans WHERE idea_id = ? ORDER BY id DESC LIMIT 1",
                            (idea_id,)).fetchone()
        return None if r is None else json.loads(r["data"]) | {"applied": bool(r["applied"])}

    def add_score(self, idea_id: int, score: float, total_profit: float, pulse: float | None,
                  note: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.db.execute("INSERT INTO score_history (idea_id, at, score, total_profit, pulse, note) "
                        "VALUES (?, ?, ?, ?, ?, ?)", (idea_id, now, score, total_profit, pulse, note))
        self.db.commit()

    def score_history(self, idea_id: int) -> list[dict]:
        rows = self.db.execute("SELECT at, score, total_profit, pulse, note FROM score_history "
                               "WHERE idea_id = ? ORDER BY id", (idea_id,)).fetchall()
        return [dict(r) for r in rows]

    def outcome_for(self, idea_id: int) -> dict | None:
        r = self.db.execute("SELECT * FROM outcomes WHERE idea_id = ?", (idea_id,)).fetchone()
        return dict(r) if r else None
