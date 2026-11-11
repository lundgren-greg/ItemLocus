"""Confidence scoring and the "not sure" rule. Pure logic, no ML imports.

All numbers are starting guesses, not calibrated values (see docs/PHOTO-TEST.md).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

DET_FULL = 0.3          # detector score that counts as full detector confidence
TEXT_ONLY_CAP = 0.75    # a name alone cannot separate look-alikes
MIN_DET = 0.1           # candidates below this detector score are ignored
DEFAULT_THRESHOLD = 0.60
DEFAULT_MARGIN = 0.10


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def confidence(det_score: float, sim: float | None, lo: float, hi: float) -> float:
    """sim is the best cosine to a reference, or None for text-only enrollment."""
    det_conf = clamp01(det_score / DET_FULL)
    if sim is None:
        return min(det_conf, TEXT_ONLY_CAP)
    match = clamp01((sim - lo) / (hi - lo))
    return math.sqrt(det_conf * match)


@dataclass(frozen=True)
class Scored:
    photo_id: str
    room: str | None
    box: tuple
    det_score: float
    sim: float | None
    confidence: float


@dataclass(frozen=True)
class Decision:
    status: str  # "found" or "not_sure"
    reason: str  # "ok", "no_candidates", "below_threshold", "ambiguous"
    best: Scored | None
    ranked: tuple


def decide(scored, threshold: float = DEFAULT_THRESHOLD, margin: float = DEFAULT_MARGIN) -> Decision:
    ranked = tuple(sorted(scored, key=lambda s: s.confidence, reverse=True))
    if not ranked:
        return Decision("not_sure", "no_candidates", None, ranked)
    best = ranked[0]
    if best.confidence < threshold:
        return Decision("not_sure", "below_threshold", best, ranked)
    if len(ranked) > 1 and best.confidence - ranked[1].confidence < margin:
        return Decision("not_sure", "ambiguous", best, ranked)
    return Decision("found", "ok", best, ranked)
