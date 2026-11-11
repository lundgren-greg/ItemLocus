"""Paths. Defaults are photos/ and data/ in the current directory."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    photos_dir: Path
    data_dir: Path

    @classmethod
    def resolve(cls, photos_dir=None, data_dir=None) -> "Config":
        return cls(
            Path(photos_dir or os.environ.get("ITEMLOCUS_PHOTOS") or "photos"),
            Path(data_dir or os.environ.get("ITEMLOCUS_DATA") or "data"),
        )

    @property
    def indexed_dir(self) -> Path:
        return self.data_dir / "indexed"

    @property
    def crops_dir(self) -> Path:
        return self.data_dir / "crops"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "itemlocus.db"

    def ensure(self) -> None:
        self.indexed_dir.mkdir(parents=True, exist_ok=True)
        self.crops_dir.mkdir(parents=True, exist_ok=True)
