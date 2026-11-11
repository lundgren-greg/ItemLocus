"""SQLite store: photos, enrolled items with reference embeddings, last seen."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS photos(
  id TEXT PRIMARY KEY, room TEXT, width INTEGER, height INTEGER,
  added_at REAL, masks TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS items(
  name TEXT PRIMARY KEY COLLATE NOCASE, query TEXT NOT NULL, created_at REAL);
CREATE TABLE IF NOT EXISTS item_refs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item TEXT NOT NULL COLLATE NOCASE REFERENCES items(name) ON DELETE CASCADE,
  model TEXT NOT NULL, dim INTEGER NOT NULL, embedding BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS last_seen(
  item TEXT PRIMARY KEY COLLATE NOCASE REFERENCES items(name) ON DELETE CASCADE,
  photo_id TEXT, room TEXT, box TEXT, confidence REAL, crop TEXT, seen_at REAL);
"""


@dataclass(frozen=True)
class PhotoRecord:
    id: str
    room: str | None
    width: int
    height: int
    masks: list = field(default_factory=list)  # person boxes, geometry only
    added_at: float = 0.0


@dataclass(frozen=True)
class Item:
    name: str
    query: str
    refs: np.ndarray  # (n, d); n == 0 for text-only enrollment
    models: frozenset = frozenset()


class Store:
    def __init__(self, path: Path | str):
        self.db = sqlite3.connect(str(path))
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    # photos
    def add_photo(self, p: PhotoRecord) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO photos VALUES(?,?,?,?,?,?)",
                (p.id, p.room, p.width, p.height, p.added_at or time.time(), json.dumps(p.masks)),
            )

    def list_photos(self) -> list[PhotoRecord]:
        rows = self.db.execute(
            "SELECT id, room, width, height, masks, added_at FROM photos ORDER BY added_at, id"
        )
        return [PhotoRecord(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5]) for r in rows]

    # items
    def add_item(self, name: str, query: str, refs=None, model: str = "") -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO items VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET query=excluded.query",
                (name, query, time.time()),
            )
            for v in [] if refs is None else np.asarray(refs, dtype=np.float32):
                self.db.execute(
                    "INSERT INTO item_refs(item, model, dim, embedding) VALUES(?,?,?,?)",
                    (name, model, int(v.shape[0]), v.tobytes()),
                )

    def get_item(self, name: str) -> Item | None:
        row = self.db.execute("SELECT name, query FROM items WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        refs = self.db.execute("SELECT model, embedding FROM item_refs WHERE item = ?", (name,)).fetchall()
        vecs = [np.frombuffer(b, dtype=np.float32) for _, b in refs]
        mat = np.stack(vecs) if vecs else np.zeros((0, 0), dtype=np.float32)
        return Item(row[0], row[1], mat, frozenset(m for m, _ in refs))

    def list_items(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT name FROM items ORDER BY name")]

    def delete_item(self, name: str) -> bool:
        with self.db:
            return self.db.execute("DELETE FROM items WHERE name = ?", (name,)).rowcount > 0

    # last seen
    def set_last_seen(self, item: str, photo_id: str, room, box, confidence: float, crop: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO last_seen VALUES(?,?,?,?,?,?,?)",
                (item, photo_id, room, json.dumps(list(box)), confidence, crop, time.time()),
            )

    def get_last_seen(self, item: str) -> dict | None:
        r = self.db.execute(
            "SELECT photo_id, room, box, confidence, crop, seen_at FROM last_seen WHERE item = ?", (item,)
        ).fetchone()
        if r is None:
            return None
        return dict(photo_id=r[0], room=r[1], box=json.loads(r[2]), confidence=r[3], crop=r[4], seen_at=r[5])
