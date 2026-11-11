"""Small interfaces the core logic depends on. No ML imports here."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in pixels

# Queries sent to the detector so people and faces can be skipped.
PERSON_QUERIES = ("person", "human face")
PERSON_LABELS = frozenset({"person", "people", "human", "face", "human face"})


def is_person(label: str) -> bool:
    return label.strip().lower() in PERSON_LABELS


@dataclass(frozen=True)
class Detection:
    label: str  # the query string that matched
    box: Box
    score: float


class Detector(Protocol):
    def detect(self, image, queries: Sequence[str]) -> list[Detection]:
        """Find regions for each text query in a PIL image."""


class Embedder(Protocol):
    name: str
    sim_lo: float  # cosine at or below this maps to match 0
    sim_hi: float  # cosine at or above this maps to match 1

    def embed(self, images: Sequence):
        """Return an (n, d) float32 numpy array of L2-normalised vectors."""
